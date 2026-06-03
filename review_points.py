#!/usr/bin/env python
"""review_points — 終局した対局から「感想戦の議題」を決定論的に抽出する。

感想戦 (players/kansousen.md) は、ここで出した議題を 1 点ずつ両 AI に配って語らせる。
LLM に「どこを議論すべきか」を探させると文脈が肥大し、肝心の転換点も見落とす。だから
転換点の発見とグラウンディング (正着・評価値) は、この安いオラクル側で確定しておく。

出すもの:
- 転換点: 評価値の振れ幅 (先手視点 cp) が大きい上位 K 手。各手に、実際の手・エンジンの
  正着と読み筋・当時のコメント (agmsg) を添える。すでに決着済みの局面での振れ (詰みに向かう
  -7000→-30000 など) は議論の価値が薄いので、評価値を ±CAP に丸めてから振れ幅を測り、
  「勝勢から敗勢へ引っくり返した一手」を優先して拾う。
- 投了局面: 最終局面の評価値と、投了した側がどれだけ離されてから投げたか。投了の遅速は
  棋風そのもの (持久戦党は大差まで粘る) なので、これも議題に含める。

engine_suggest の Engine をそのまま使う (board.py の対局ロジックには触らない)。
"""
import argparse
import json
import os
import sqlite3
from pathlib import Path

import shogi
from engine_suggest import Engine, usi_to_ja, board_from_moves, GAME_ROOT

DB = os.path.expanduser("~/.agents/skills/agmsg/db/messages.db")
MATE_CP = 30000


def resolve_record(game):
    """対局 ID から手列ファイルを解決する。新方式 state/<game>/sente.moves、旧方式の
    flat state/sente<game>.moves、既定対局 state/sente.moves の順で探す。"""
    base = Path(GAME_ROOT) / "state"
    for p in ([base / game / "sente.moves"] if game else []) + \
             ([base / f"sente{game}.moves"] if game else []) + \
             [base / "sente.moves"]:
        if p.exists():
            return p
    raise FileNotFoundError(f"手列ファイルが見つかりません (game={game!r})")


def load_record(path):
    return [ln.strip() for ln in Path(path).read_text().splitlines() if ln.strip()]


def black_eval(eng, prefix, ply, movetime):
    """prefix を指した局面の評価値を先手 (BLACK) 視点 cp で返す。"""
    rows = eng.multipv(prefix, 1, movetime)
    if not rows:
        # 合法手なし = 手番側が詰み。手番側が負け → 先手視点へ符号化。
        board = board_from_moves(prefix)
        mated_is_black = board.turn == shogi.BLACK
        return -MATE_CP if mated_is_black else MATE_CP
    score = rows[0]["score"]            # 手番側視点
    return score if ply % 2 == 0 else -score  # ply 偶数=先手番→そのまま


def eval_series(eng, moves, movetime):
    return [black_eval(eng, moves[:k], k, movetime) for k in range(len(moves) + 1)]


def banter_map(moves, sente_name, gote_name):
    """各手に当時の agmsg コメントを対応づける。挨拶など指し手以外の発言で番号がずれるので、
    送信者ごとに本文先頭トークン (USI) を順に消費しながら整合させる。"""
    if not os.path.exists(DB):
        return {}
    con = sqlite3.connect(DB)
    streams = {}
    for name in (sente_name, gote_name):
        rows = con.execute(
            "SELECT body FROM messages WHERE team='shogi' AND from_agent=? ORDER BY created_at",
            (name,)).fetchall()
        streams[name] = [(r[0].split(None, 1)[0] if r[0].split() else "", r[0]) for r in rows]
    ptr = {sente_name: 0, gote_name: 0}
    out = {}
    for i, usi in enumerate(moves, 1):
        name = sente_name if i % 2 == 1 else gote_name
        s = streams.get(name, [])
        j = ptr[name]
        while j < len(s) and s[j][0] != usi:
            j += 1
        if j < len(s):
            out[i] = s[j][1]
            ptr[name] = j + 1
    return out


def turning_points(eng, moves, evals, k, cap, movetime):
    """評価値の振れ幅 (±cap に丸めて測る) 上位 k の転換点を、正着つきで返す。"""
    swings = []
    for m in range(1, len(moves) + 1):
        b, a = evals[m - 1], evals[m]
        cb, ca = max(-cap, min(cap, b)), max(-cap, min(cap, a))
        swings.append((abs(ca - cb), m))
    swings.sort(reverse=True)
    chosen = sorted(m for _, m in swings[:k])

    points = []
    for m in chosen:
        usi = moves[m - 1]
        mover = "sente" if m % 2 == 1 else "gote"
        pre = moves[:m - 1]
        board = board_from_moves(pre)
        rows = eng.multipv(pre, 5, movetime)
        best = rows[0] if rows else None
        # 実際に指した手の評価値が候補内にあれば拾う
        played_score = next((r["score"] for r in rows if r["usi"] == usi), None)
        b2 = board_from_moves(pre)
        pv_ja = []
        if best:
            for u in best["pv"][:6]:
                pv_ja.append(usi_to_ja(b2, u))
                try:
                    b2.push_usi(u)
                except Exception:
                    break
        points.append({
            "move_no": m,
            "usi": usi,
            "ja": usi_to_ja(board, usi),
            "mover": mover,
            "eval_before_black": evals[m - 1],
            "eval_after_black": evals[m],
            "delta_black": evals[m] - evals[m - 1],
            "best_usi": best["usi"] if best else None,
            "best_ja": usi_to_ja(board, best["usi"]) if best else None,
            "best_score_mover": best["score"] if best else None,
            "played_score_mover": played_score,
            "loss_vs_best_cp": (best["score"] - played_score)
            if (best and played_score is not None) else None,
            "pv_ja": pv_ja,
        })
    return points


def resignation(moves, evals):
    """最終局面の評価値から、敗者と「どれだけ離されて投げたか」を出す。"""
    final = evals[-1]
    loser = "sente" if final < 0 else "gote"
    return {
        "final_eval_black": final,
        "loser": loser,
        "deficit_loser_view_cp": -abs(final),
        "is_mate": abs(final) >= MATE_CP,
    }


def main():
    ap = argparse.ArgumentParser(description="終局した対局から感想戦の議題を抽出する")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--game", default="", help="対局 ID (例 2)。state を自動解決")
    src.add_argument("--record", help="手列ファイル (.moves) を直接指定")
    ap.add_argument("--sente-name", help="先手の agmsg name (既定 sente<game>)")
    ap.add_argument("--gote-name", help="後手の agmsg name (既定 gote<game>)")
    ap.add_argument("-k", "--points", type=int, default=6, help="転換点をいくつ拾うか")
    ap.add_argument("--cap", type=int, default=2000, help="評価値を丸める上限 cp (決着後の振れを抑える)")
    ap.add_argument("--movetime", type=int, default=300, help="評価系列の 1 手あたり ms")
    ap.add_argument("--tp-movetime", type=int, default=1000, help="転換点の正着読みの ms")
    ap.add_argument("--json", action="store_true", help="JSON 出力")
    args = ap.parse_args()

    path = Path(args.record) if args.record else resolve_record(args.game)
    moves = load_record(path)
    sente_name = args.sente_name or f"sente{args.game}"
    gote_name = args.gote_name or f"gote{args.game}"

    eng = Engine()
    try:
        evals = eval_series(eng, moves, args.movetime)
        tps = turning_points(eng, moves, evals, args.points, args.cap, args.tp_movetime)
    finally:
        eng.quit()

    banter = banter_map(moves, sente_name, gote_name)
    for tp in tps:
        tp["banter"] = banter.get(tp["move_no"])
    resign = resignation(moves, evals)

    agenda = {
        "record": str(path),
        "total_moves": len(moves),
        "sente_name": sente_name,
        "gote_name": gote_name,
        "resignation": resign,
        "turning_points": tps,
    }

    if args.json:
        print(json.dumps(agenda, ensure_ascii=False, indent=2))
        return

    print(f"棋譜: {path}  ({len(moves)}手)")
    r = resign
    side = "先手" if r["loser"] == "sente" else "後手"
    tail = "詰み" if r["is_mate"] else f"{r['deficit_loser_view_cp']}cp"
    print(f"投了: {side}が敗勢で終局 (最終 先手視点 {r['final_eval_black']:+d}cp / 敗者から見て {tail})")
    print(f"\n=== 感想戦の議題 (転換点 上位{len(tps)}) ===")
    for tp in tps:
        mv = "先手" if tp["mover"] == "sente" else "後手"
        print(f"\n[{tp['move_no']}手目 {mv}] 実戦 {tp['ja']} ({tp['usi']})  "
              f"評価 {tp['eval_before_black']:+d}→{tp['eval_after_black']:+d}cp(先手視点)")
        if tp["best_ja"]:
            loss = tp["loss_vs_best_cp"]
            ls = f"  実戦は最善より {loss}cp 損" if loss else ""
            print(f"   正着 {tp['best_ja']} ({tp['best_score_mover']:+d}cp 自分視点){ls}")
            print(f"   読み筋 {' '.join(tp['pv_ja'][:5])}")
        if tp["banter"]:
            print(f"   当時の弁: {tp['banter'][:80]}")


if __name__ == "__main__":
    main()
