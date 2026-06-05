#!/usr/bin/env python
"""mate_line — 投了局面から詰みまで指し継ぐ。

この対局は投了で終わる (盤上はまだ詰んでいない)。本ツールは終局図から、両者最善
(やねうら王の go movetime) で詰みまで指し継ぎ、「実戦 + 寄せの継続」を 1 本の手列として
書き出す。これで「投げた将棋が実際どう詰むのか」を毎度残せる。

- 出力 <out>.moves は実戦手 + 継続手をまとめた手列。viewer は ?player=<out名>&game=<game>
  でそのまま実戦から詰みまで再生できる (board.py / server.py と同じ再生規約)。
- mate_line.md に継続譜 (各手の評価値・王手) と、どこから指し継ぎかを残す。

go mate は使わない (このビルドで movetime を無視して暴走するため)。go movetime のみで、
勝勢の側が寄せ、負け側は最善で最長に粘る ── これが投了後の「本来の決着」になる。

engine_suggest / review_points の純粋ヘルパーを再利用し、エンジンだけ詰将棋向けに
Threads を増やして持つ (engine_suggest の MultiPV 探索とは別インスタンス)。
"""
import argparse
import subprocess
import sys
from pathlib import Path

import shogi
from engine_suggest import usi_to_ja, board_from_moves, ENGINE_DIR, ENGINE_BIN
from review_points import resolve_record, load_record


class MateEngine:
    """やねうら王を bestmove + score で叩く薄いラッパー (詰みまでの指し継ぎ用)。"""

    def __init__(self, threads):
        self.proc = subprocess.Popen(
            [str(ENGINE_BIN)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, cwd=str(ENGINE_DIR), bufsize=1,
        )
        self._send("usi"); self._wait("usiok")
        self._send("setoption name EvalDir value .")
        self._send("setoption name USI_Hash value 128")
        self._send(f"setoption name Threads value {threads}")
        self._send("isready"); self._wait("readyok")

    def _send(self, c):
        self.proc.stdin.write(c + "\n"); self.proc.stdin.flush()

    def _wait(self, tok):
        while True:
            line = self.proc.stdout.readline()
            if not line or tok in line:
                return

    def bestmove(self, all_moves, movetime):
        self._send("position startpos moves " + " ".join(all_moves))
        self._send(f"go movetime {movetime}")
        kind, score = None, None
        while True:
            line = self.proc.stdout.readline()
            if not line:
                return None, None, None
            toks = line.split()
            if "score" in toks:
                i = toks.index("score")
                kind, score = toks[i + 1], toks[i + 2]
            if line.startswith("bestmove"):
                return toks[1], kind, score

    def quit(self):
        try:
            self._send("quit"); self.proc.wait(timeout=3)
        except Exception:
            self.proc.kill()


def play_to_mate(moves, movetime, maxply, threads):
    """終局図から両者最善で詰みまで指し継ぐ。継続手列と各手の記録、到達可否を返す。"""
    eng = MateEngine(threads)
    board = board_from_moves(moves)
    cont, rows = [], []
    stop = None
    try:
        while not board.is_checkmate() and not board.is_game_over() and len(cont) < maxply:
            bm, kind, score = eng.bestmove(moves + cont, movetime)
            if bm in (None, "resign", "win", "(none)"):
                stop = f"bestmove={bm}"
                break
            mv = shogi.Move.from_usi(bm)
            if mv not in board.legal_moves:
                stop = f"非合法 {bm}"
                break
            ja = usi_to_ja(board, bm)
            board.push(mv)
            cont.append(bm)
            rows.append({
                "ply": len(moves) + len(cont), "usi": bm, "ja": ja,
                "kind": kind, "score": score, "check": board.is_check(),
            })
    finally:
        eng.quit()
    return cont, rows, board.is_checkmate(), stop


def to_markdown(src_len, cont, rows, mated, stop):
    out = ["# 指し継ぎ — 投了局面から詰みまで", "",
           f"実戦 {src_len} 手で投了。以下、両者最善 (やねうら王) で指し継いだ寄せ。", ""]
    if mated:
        out.append(f"**{src_len + len(cont)} 手目で詰み。** 寄せは {len(cont)} 手。")
    elif stop:
        out.append(f"指し継ぎは {len(cont)} 手で打ち切り（{stop}）。詰みには未到達。")
    out.append("")
    out.append("| 手数 | 指し手 | 評価 | 王手 |")
    out.append("|---|---|---|---|")
    for r in rows:
        sc = f"{r['kind']} {r['score']}" if r["kind"] else ""
        out.append(f"| {r['ply']} | {r['ja']} ({r['usi']}) | {sc} | {'王手' if r['check'] else ''} |")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description="投了局面から詰みまで指し継ぐ")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--game", default="", help="対局 ID。state を自動解決して棋譜を読む")
    src.add_argument("--record", help="手列ファイル (.moves) を直接指定")
    ap.add_argument("--out", help="出力する手列ファイル (.moves)。既定は元ディレクトリ/mate.moves")
    ap.add_argument("--movetime", type=int, default=1200, help="1 手あたりの思考 ms")
    ap.add_argument("--max", type=int, default=90, help="指し継ぐ最大手数 (安全弁)")
    ap.add_argument("--threads", type=int, default=4, help="エンジンのスレッド数")
    args = ap.parse_args()

    src_path = Path(args.record) if args.record else resolve_record(args.game)
    moves = load_record(src_path)
    out_path = Path(args.out) if args.out else (src_path.parent / "mate.moves")
    md_path = out_path.parent / "mate_line.md"

    print(f"実戦 {len(moves)} 手 ({src_path})。終局図から詰みまで指し継ぎ中…", file=sys.stderr)
    cont, rows, mated, stop = play_to_mate(moves, args.movetime, args.max, args.threads)
    for r in rows:
        sc = f"[{r['kind']} {r['score']}]" if r["kind"] else ""
        print(f"  {r['ply']}手目 {r['ja']:<10} ({r['usi']}) {sc}"
              f"{'  ** 王手 **' if r['check'] else ''}", file=sys.stderr)

    full = moves + cont
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(u + "\n" for u in full))
    md_path.write_text(to_markdown(len(moves), cont, rows, mated, stop))

    tail = f"{len(full)}手目で詰み" if mated else f"{len(cont)}手で打ち切り（{stop}）"
    print(f"\n指し継ぎ: 寄せ {len(cont)}手 → {tail}", file=sys.stderr)
    print(f"書き出し: {out_path}  ({len(full)}手) / {md_path}", file=sys.stderr)
    print(f"観戦: http://localhost:8011/?player={out_path.stem}&game={args.game}", file=sys.stderr)


if __name__ == "__main__":
    main()
