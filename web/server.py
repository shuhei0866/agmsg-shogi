#!/usr/bin/env python
"""agmsg-shogi web viewer のバックエンド。

対局本体の state/<player>.moves を読み、各局面の SFEN を配信する (/api/game)。
さらにやねうら王 (USI) を常駐させ、各局面の評価値を先手視点で配信する (/api/eval)。
評価値は局面 (SFEN) ごとにキャッシュして同じ局面は再評価せず、未評価ぶんは
バックグラウンドで進める (初回リクエストもブロックしない)。対局には一切書き込まない。
"""
import json
import os
import subprocess
import threading
from pathlib import Path

import shogi
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

GAME_ROOT = os.path.expanduser("~/Developer/agmsg-shogi")
STATE_DIR = os.path.join(GAME_ROOT, "state")
WEB_DIR = os.path.dirname(os.path.abspath(__file__))

# 並行対局の観戦: ?game=<id> で state/<id>/ を読む。クエリが無ければ AGMSG_GAME、
# それも無ければ従来の state/ を見る (後方互換)。board.py / engine_suggest.py と同じ規約。
DEFAULT_GAME = os.environ.get("AGMSG_GAME", "").strip()


def _state_dir(game):
    g = (game or DEFAULT_GAME).strip()
    return os.path.join(STATE_DIR, g) if g else STATE_DIR

ENGINE_DIR = Path(GAME_ROOT) / "engine"
ENGINE_BIN = ENGINE_DIR / "NNUE_halfkp_256x2_32_32/YaneuraOu_NNUE_halfkp_256x2_32_32-V900Git_APPLEM1"
MOVETIME_MS = 250

app = FastAPI()

_engine = None
_lock = threading.Lock()
_cache = {}  # sfen -> 先手視点 score (cp)


def _read_moves(player, game=""):
    path = os.path.join(_state_dir(game), f"{player}.moves")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [ln.strip() for ln in f if ln.strip()]


def _sfens_for(player, game=""):
    """初期局面 + 各手後の SFEN リストを返す。"""
    board = shogi.Board()
    sfens = [board.sfen()]
    moves = []
    for usi in _read_moves(player, game):
        try:
            board.push_usi(usi)
        except Exception:
            break
        sfens.append(board.sfen())
        moves.append(usi)
    return moves, sfens, board


def _engine_send(c):
    _engine.stdin.write(c + "\n")
    _engine.stdin.flush()


def _engine_wait(token):
    while True:
        line = _engine.stdout.readline()
        if not line or token in line:
            return


def _ensure_engine():
    global _engine
    if _engine is not None:
        return
    _engine = subprocess.Popen(
        [str(ENGINE_BIN)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        text=True, cwd=str(ENGINE_DIR), bufsize=1,
    )
    _engine_send("usi")
    _engine_wait("usiok")
    _engine_send("setoption name EvalDir value .")
    _engine_send("setoption name USI_Hash value 128")
    _engine_send("isready")
    _engine_wait("readyok")


def _eval_one(moves, ply):
    """ply 手目の局面を評価し、先手視点の score (cp) を返す。"""
    pos = "position startpos" + (" moves " + " ".join(moves) if moves else "")
    _engine_send(pos)
    _engine_send(f"go movetime {MOVETIME_MS}")
    score = 0
    while True:
        line = _engine.stdout.readline()
        if not line:
            break
        toks = line.split()
        if "score" in toks:
            i = toks.index("score")
            kind = toks[i + 1]
            if kind == "cp":
                score = int(toks[i + 2])
            elif kind == "mate":
                score = 30000 if not toks[i + 2].lstrip("+").startswith("-") else -30000
        if line.startswith("bestmove"):
            break
    # score は手番側視点。先手視点へ: ply 偶数=先手番→そのまま、奇数=後手番→反転
    return score if ply % 2 == 0 else -score


def _eval_pending(player, game=""):
    """未評価の局面を順に評価してキャッシュに入れる (同時に 1 スレッドのみ)。"""
    if not _lock.acquire(blocking=False):
        return
    try:
        _ensure_engine()
        moves, _, _ = _sfens_for(player, game)
        board = shogi.Board()
        prefix = []
        if board.sfen() not in _cache:
            _cache[board.sfen()] = _eval_one(prefix, 0)
        for i, usi in enumerate(moves):
            board.push_usi(usi)
            prefix.append(usi)
            sfen = board.sfen()
            if sfen not in _cache:
                _cache[sfen] = _eval_one(prefix, i + 1)
    finally:
        _lock.release()


@app.get("/api/game")
def api_game(player: str = "sente", game: str = ""):
    moves, sfens, board = _sfens_for(player, game)
    resp = {
        "player": player, "game": (game or DEFAULT_GAME), "count": len(moves), "moves": moves,
        "sfens": sfens, "last": moves[-1] if moves else None,
        "checkmate": board.is_checkmate(), "game_over": board.is_game_over(),
    }
    # 指し継ぎ (mate_line) の sidecar があれば、実戦と寄せの境目を伝える
    side = os.path.join(_state_dir(game), f"{player}.json")
    if os.path.exists(side):
        try:
            with open(side, encoding="utf-8") as f:
                meta = json.load(f)
            if "src_len" in meta:
                resp["resign_at"] = meta["src_len"]
                resp["mate_line"] = True
        except Exception:
            pass
    return JSONResponse(resp)


@app.get("/api/eval")
def api_eval(player: str = "sente", game: str = ""):
    """各局面 (初期+各手) の先手視点 score。キャッシュ済みのみ返し、未評価は null。"""
    moves, sfens, _ = _sfens_for(player, game)
    evals = [_cache.get(s) for s in sfens]
    if any(e is None for e in evals):
        threading.Thread(target=_eval_pending, args=(player, game), daemon=True).start()
    done = sum(1 for e in evals if e is not None)
    return JSONResponse({"player": player, "count": len(moves), "evals": evals, "evaluated": done})


@app.get("/api/review")
def api_review(game: str = "", src: str = ""):
    """対局の感想戦 (kansousen.py の出力) を返す。?game=<id> なら state/<id>/kansousen.json、
    ?src=<相対パス> ならアーカイブ等の任意の kansousen.json (GAME_ROOT 配下のみ)。"""
    if src:
        path = os.path.normpath(os.path.join(GAME_ROOT, src))
        if not path.startswith(GAME_ROOT):   # パストラバーサル防止
            return JSONResponse({"available": False, "exchanges": []})
    else:
        path = os.path.join(_state_dir(game), "kansousen.json")
    if not os.path.exists(path):
        return JSONResponse({"available": False, "exchanges": []})
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["available"] = True
    return JSONResponse(data)


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(WEB_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()
