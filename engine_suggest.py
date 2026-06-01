#!/usr/bin/env python
"""engine_suggest — 現局面でやねうら王に上位手を出させる、プレイヤー補助ツール。

agmsg-shogi の新方式 (棋風対局) で使う。指し手の強さはエンジンに任せ、LLM は
ここで返ってきた候補手の中から「自分の棋風」で 1 手を選ぶことに専念する。

- MultiPV で上位 N 手を取り、各手の評価値 (センチポーン) と読み筋 (PV) を返す。
- 評価値は **手番側 (= これから指す自分) 視点**。+ が大きいほど自分が良い。
  (engine_suggest は常に自分の手番で呼ぶので、符号反転は要らない。web/server.py の
  評価グラフが先手視点へ反転しているのとは役割が違う。)
- 「最善手から -X センチポーン以内」を --margin で渡すと、その帯に入る手に ✓ を付ける。
  棋風で選ぶのはこの ✓ の中から、というのが既定の運用 (players/*.md 参照)。

board.py の対局ロジック (apply/legal/status/盤面再生) には一切触らない別ツール。
盤面の真実はあくまで board.py / state/<player>.moves 側にある。ここは「候補手の提案」だけを担う。

使い方:
    engine_suggest.py --player sente                 # state/sente.moves の現局面で上位手
    engine_suggest.py --moves "7g7f 3c3d"            # 手列を直接渡す (テスト用)
    engine_suggest.py --player gote --multipv 5 --movetime 800 --margin 200
    engine_suggest.py --player sente --json          # 機械可読 (JSON)
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import shogi

# web/server.py と同じ絶対パス。どの worktree / どの cwd から呼ばれても
# メインツリーの engine/ ・ state/ を解決する。
GAME_ROOT = Path(os.path.expanduser("~/Developer/agmsg-shogi"))
STATE_DIR = GAME_ROOT / "state"
ENGINE_DIR = GAME_ROOT / "engine"
ENGINE_BIN = ENGINE_DIR / "NNUE_halfkp_256x2_32_32/YaneuraOu_NNUE_halfkp_256x2_32_32-V900Git_APPLEM1"

MATE_CP = 30000  # mate を cp に押し込むときの絶対値

# python-shogi の piece_type → 日本語駒名。掛け合いコメントを書きやすくするための装飾。
PIECE_JA = {
    shogi.PAWN: "歩", shogi.LANCE: "香", shogi.KNIGHT: "桂", shogi.SILVER: "銀",
    shogi.GOLD: "金", shogi.BISHOP: "角", shogi.ROOK: "飛", shogi.KING: "玉",
    shogi.PROM_PAWN: "と", shogi.PROM_LANCE: "成香", shogi.PROM_KNIGHT: "成桂",
    shogi.PROM_SILVER: "成銀", shogi.PROM_BISHOP: "馬", shogi.PROM_ROOK: "龍",
}
ZEN_FILE = "１２３４５６７８９"
KAN_RANK = "一二三四五六七八九"


def read_moves(player):
    path = STATE_DIR / f"{player}.moves"
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]


def board_from_moves(moves):
    """USI 手列を startpos から再生して board を返す。不正手があればそこで例外。"""
    board = shogi.Board()
    for usi in moves:
        board.push_usi(usi)
    return board


def usi_to_ja(board, usi):
    """USI を ▲７六歩 / △２二角成 / ▲５五歩打 のような日本語表記に。失敗したら USI のまま。"""
    try:
        mark = "▲" if board.turn == shogi.BLACK else "△"
        move = shogi.Move.from_usi(usi)
        to_sq = usi[2:4]
        dest = ZEN_FILE[int(to_sq[0]) - 1] + KAN_RANK[ord(to_sq[1]) - ord("a")]
        if move.drop_piece_type:
            return f"{mark}{dest}{PIECE_JA[move.drop_piece_type]}打"
        pt = board.piece_at(move.from_square).piece_type
        suffix = "成" if move.promotion else ""
        return f"{mark}{dest}{PIECE_JA[pt]}{suffix}"
    except Exception:
        return usi


class Engine:
    """やねうら王 (USI) の薄いラッパー。web/server.py の起動シーケンスを踏襲。"""

    def __init__(self):
        self.proc = subprocess.Popen(
            [str(ENGINE_BIN)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, cwd=str(ENGINE_DIR), bufsize=1,
        )
        self._send("usi")
        self._wait("usiok")
        self._send("setoption name EvalDir value .")
        self._send("setoption name USI_Hash value 128")
        self._send("isready")
        self._wait("readyok")

    def _send(self, c):
        self.proc.stdin.write(c + "\n")
        self.proc.stdin.flush()

    def _wait(self, token):
        while True:
            line = self.proc.stdout.readline()
            if not line or token in line:
                return

    def multipv(self, moves, n, movetime):
        """startpos + moves の局面で上位 n 手を取り、(usi, score_cp, is_mate, mate_n, pv) を返す。

        score は手番側視点 (これから指す自分にとって + が良い)。
        """
        self._send(f"setoption name MultiPV value {n}")
        self._send("position startpos" + (" moves " + " ".join(moves) if moves else ""))
        self._send(f"go movetime {movetime}")
        rows = {}  # multipv idx -> dict
        while True:
            line = self.proc.stdout.readline()
            if not line:
                break
            toks = line.split()
            if line.startswith("bestmove"):
                break
            if "multipv" not in toks or "pv" not in toks or "score" not in toks:
                continue
            idx = int(toks[toks.index("multipv") + 1])
            si = toks.index("score")
            kind, val = toks[si + 1], toks[si + 2]
            is_mate = kind == "mate"
            if is_mate:
                signed = int(val.lstrip("+"))
                score = MATE_CP if signed >= 0 else -MATE_CP
                mate_n = signed
            else:
                score = int(val)
                mate_n = None
            pv = toks[toks.index("pv") + 1:]
            rows[idx] = {"usi": pv[0], "score": score, "is_mate": is_mate,
                         "mate_n": mate_n, "pv": pv}
        return [rows[i] for i in sorted(rows)]

    def quit(self):
        try:
            self._send("quit")
            self.proc.wait(timeout=3)
        except Exception:
            self.proc.kill()


def suggest(moves, multipv, movetime, margin):
    """候補手リストを作る。各候補に delta (最善手との差) と within (帯に入るか) を付ける。"""
    board = board_from_moves(moves)
    side = "sente" if board.turn == shogi.BLACK else "gote"
    legal = list(board.legal_moves)
    if not legal:
        return {"side": side, "ply": len(moves), "game_over": True,
                "checkmate": board.is_checkmate(), "candidates": []}

    eng = Engine()
    try:
        rows = eng.multipv(moves, multipv, movetime)
    finally:
        eng.quit()

    rows.sort(key=lambda r: r["score"], reverse=True)
    best = rows[0]["score"] if rows else 0
    cands = []
    for rank, r in enumerate(rows, 1):
        delta = best - r["score"]
        # PV を局面を進めながら日本語化 (先頭数手だけ)。python-shogi の Board に
        # copy が無いので、その都度 startpos から再生した盤面を使う。
        pv_ja, b2 = [], board_from_moves(moves)
        for u in r["pv"][:6]:
            pv_ja.append(usi_to_ja(b2, u))
            try:
                b2.push_usi(u)
            except Exception:
                break
        cands.append({
            "rank": rank, "usi": r["usi"], "ja": usi_to_ja(board, r["usi"]),
            "score": r["score"], "is_mate": r["is_mate"], "mate_n": r["mate_n"],
            "delta": delta, "within": delta <= margin,
            "pv": r["pv"], "pv_ja": pv_ja,
        })
    return {"side": side, "ply": len(moves), "game_over": False,
            "checkmate": False, "margin": margin, "best": best, "candidates": cands}


def score_str(c):
    if c["is_mate"]:
        return f"mate {c['mate_n']:+d}"
    return f"{c['score']:+d}"


def render_text(res):
    if res["game_over"]:
        why = "詰み (合法手なし)" if res["checkmate"] else "合法手なし"
        return f"side={res['side']} ply={res['ply']}: {why}。候補手はありません。"
    lines = [
        f"side={res['side']}  ply={res['ply']}  margin={res['margin']}cp  "
        f"(score は自分視点 / +が自分有利、Δ=最善手との差、✓=帯内)",
        "  #  手        score    Δ    読み筋",
    ]
    for c in res["candidates"]:
        mark = "✓" if c["within"] else " "
        pv = " ".join(c["pv_ja"][:5])
        lines.append(
            f" {mark}{c['rank']}  {c['ja']:<8} {score_str(c):>6}  {c['delta']:>4}  {pv}"
        )
    eligible = [str(c["rank"]) for c in res["candidates"] if c["within"]]
    lines.append(f"帯内 (最善手から{res['margin']}cp 以内): {', '.join(eligible) or 'なし'}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="現局面でやねうら王に上位手を出させる")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--player",
                     help="state/<player>.moves の現局面を使う (役割名。sente / gote のほか "
                          "room 付きの sente2 / gote2 等も可)")
    src.add_argument("--moves", help="USI 手列を直接渡す (空白区切り、テスト用)")
    ap.add_argument("--multipv", type=int, default=5, help="上位何手まで (既定 5)")
    ap.add_argument("--movetime", type=int, default=800, help="思考時間 ms (既定 800)")
    ap.add_argument("--margin", type=int, default=200,
                    help="最善手から何 cp 以内を帯に入れるか (既定 200)")
    ap.add_argument("--json", action="store_true", help="JSON で出力")
    args = ap.parse_args()

    if args.moves is not None:
        moves = args.moves.split()
    elif args.player:
        moves = read_moves(args.player)
    else:
        moves = []  # 何も指定なければ初期局面

    try:
        res = suggest(moves, args.multipv, args.movetime, args.margin)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(render_text(res))


if __name__ == "__main__":
    main()
