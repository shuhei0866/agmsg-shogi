#!/usr/bin/env python
"""△６七歩成（実戦58手目）以降を、両者最善で詰みまで再生する解析。

state/gote2.moves（実戦）は読むだけ。結果は state/gote2_mate.moves に
[実戦58手 + 寄せの継続] として書き出し、viewer で ?player=gote2_mate で見る。
go mate は使わない（このビルドで時間制限を守らず暴走したため）。go movetime のみ。
"""
import os
import subprocess
import sys
from pathlib import Path

import shogi

GAME_ROOT = Path(os.path.expanduser("~/Developer/agmsg-shogi"))
STATE_DIR = GAME_ROOT / "state"
ENGINE_DIR = GAME_ROOT / "engine"
ENGINE_BIN = ENGINE_DIR / "NNUE_halfkp_256x2_32_32/YaneuraOu_NNUE_halfkp_256x2_32_32-V900Git_APPLEM1"

PIECE_JA = {
    shogi.PAWN: "歩", shogi.LANCE: "香", shogi.KNIGHT: "桂", shogi.SILVER: "銀",
    shogi.GOLD: "金", shogi.BISHOP: "角", shogi.ROOK: "飛", shogi.KING: "玉",
    shogi.PROM_PAWN: "と", shogi.PROM_LANCE: "成香", shogi.PROM_KNIGHT: "成桂",
    shogi.PROM_SILVER: "成銀", shogi.PROM_BISHOP: "馬", shogi.PROM_ROOK: "龍",
}
ZEN_FILE = "１２３４５６７８９"
KAN_RANK = "一二三四五六七八九"


def usi_to_ja(board, usi):
    try:
        mark = "▲" if board.turn == shogi.BLACK else "△"
        move = shogi.Move.from_usi(usi)
        dest = ZEN_FILE[int(usi[2]) - 1] + KAN_RANK[ord(usi[3]) - ord("a")]
        if move.drop_piece_type:
            return f"{mark}{dest}{PIECE_JA[move.drop_piece_type]}打"
        pt = board.piece_at(move.from_square).piece_type
        return f"{mark}{dest}{PIECE_JA[pt]}{'成' if move.promotion else ''}"
    except Exception:
        return usi


moves = [ln.strip() for ln in (STATE_DIR / "gote2.moves").read_text().splitlines() if ln.strip()]
print(f"実戦手数: {len(moves)}  最終手: {moves[-1]}", flush=True)

proc = subprocess.Popen(
    [str(ENGINE_BIN)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    text=True, cwd=str(ENGINE_DIR), bufsize=1,
)


def send(c):
    proc.stdin.write(c + "\n")
    proc.stdin.flush()


def wait(tok):
    while True:
        line = proc.stdout.readline()
        if not line or tok in line:
            return


send("usi"); wait("usiok")
send("setoption name EvalDir value .")
send("setoption name USI_Hash value 128")
send("setoption name Threads value 4")
send("isready"); wait("readyok")


def best_and_score(all_moves, movetime):
    send("position startpos moves " + " ".join(all_moves))
    send(f"go movetime {movetime}")
    bm, kind, score = None, None, None
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        toks = line.split()
        if "score" in toks:
            i = toks.index("score")
            kind, score = toks[i + 1], toks[i + 2]
        if line.startswith("bestmove"):
            bm = toks[1]
            break
    return bm, kind, score


board = shogi.Board()
for u in moves:
    board.push_usi(u)

cont, rows = [], []
MOVETIME, MAX = 1200, 90
while not board.is_checkmate() and not board.is_game_over() and len(cont) < MAX:
    bm, kind, score = best_and_score(moves + cont, MOVETIME)
    if bm in (None, "resign", "win", "(none)"):
        print(f"\nbestmove={bm} で終了", flush=True)
        break
    mv = shogi.Move.from_usi(bm)
    if mv not in board.legal_moves:
        print(f"\n非合法 {bm} で終了", flush=True)
        break
    ja = usi_to_ja(board, bm)
    board.push(mv)
    cont.append(bm)
    chk = "  ** 王手 **" if board.is_check() else ""
    rows.append((len(moves) + len(cont), bm, ja, kind, score, chk))
    print(f"  {len(moves)+len(cont)}手目  {ja:<10} ({bm})  [{kind} {score}]{chk}", flush=True)

print(f"\ncheckmate に到達: {board.is_checkmate()}   追加手数: {len(cont)}", flush=True)

full = moves + cont
(STATE_DIR / "gote2_mate.moves").write_text("".join(u + "\n" for u in full))
print(f"書き出し: state/gote2_mate.moves  ({len(full)}手)", flush=True)

send("quit")
