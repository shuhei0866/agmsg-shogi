#!/usr/bin/env python
"""agmsg-shogi web viewer のバックエンド。

対局本体 (main の working tree) の state/<player>.moves を読み、python-shogi で
初手から再生して各局面の SFEN リストを配信する。盤面描画はフロント側 (shogiground)
が SFEN から行う。このサーバーは棋譜を SFEN に変換して渡すだけで、対局には一切
書き込まない (読み取り専用)。
"""
import os

import shogi
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

# 対局が走っているのは main の working tree。worktree からそこの state を読む。
GAME_ROOT = os.path.expanduser("~/Developer/agmsg-shogi")
STATE_DIR = os.path.join(GAME_ROOT, "state")
WEB_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()


def _read_moves(player):
    path = os.path.join(STATE_DIR, f"{player}.moves")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [ln.strip() for ln in f if ln.strip()]


@app.get("/api/game")
def game(player: str = "sente"):
    """棋譜を再生して各局面の SFEN を返す。sfens[0] は初期局面、sfens[i] は i 手目後。"""
    moves = _read_moves(player)
    board = shogi.Board()
    sfens = [board.sfen()]
    applied = []
    for usi in moves:
        try:
            board.push_usi(usi)
        except Exception:
            break  # 不正手 / 盤面ずれが起きたらそこで止める
        sfens.append(board.sfen())
        applied.append(usi)
    return JSONResponse(
        {
            "player": player,
            "count": len(applied),
            "moves": applied,
            "sfens": sfens,
            "last": applied[-1] if applied else None,
            "checkmate": board.is_checkmate(),
            "game_over": board.is_game_over(),
        }
    )


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(WEB_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()
