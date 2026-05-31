#!/usr/bin/env python
"""agmsg-shogi の盤面管理 CLI。

python-shogi のラッパーに徹し、思考は一切しない。各プレイヤー(別ペインの
Claude)は自分のローカルな手列ファイル state/<player>.moves を真実の源とし、
USI 形式の指し手だけを agmsg で相手に送り合う。両者が同じ初手から同じ手順を
決定論的に再生するので、指し手の同期だけで盤面が一致する。相手が反則手を
送れば apply が弾いて、そこで検出できる。
"""
import argparse
import os
import sys

import shogi

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(ROOT, "state")

PIECE_JP = {
    "P": "歩", "L": "香", "N": "桂", "S": "銀", "G": "金",
    "B": "角", "R": "飛", "K": "玉",
    "+P": "と", "+L": "杏", "+N": "圭", "+S": "全", "+B": "馬", "+R": "龍",
}
KANSUJI = "一二三四五六七八九"


def moves_path(player):
    return os.path.join(STATE_DIR, f"{player}.moves")


def load(player):
    """手列ファイルを再生して board と手列を返す。"""
    board = shogi.Board()
    path = moves_path(player)
    moves = []
    if os.path.exists(path):
        with open(path) as f:
            moves = [ln.strip() for ln in f if ln.strip()]
    for usi in moves:
        board.push_usi(usi)
    return board, moves


def save(player, moves):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(moves_path(player), "w") as f:
        f.write("".join(usi + "\n" for usi in moves))


def hands_str(board):
    """先手・後手の持ち駒を読みやすく整形する。"""
    out = []
    for color, label in ((shogi.BLACK, "先手"), (shogi.WHITE, "後手")):
        pieces = board.pieces_in_hand[color]
        if pieces:
            parts = []
            for ptype, count in sorted(pieces.items()):
                sym = shogi.PIECE_SYMBOLS[ptype].upper()
                jp = PIECE_JP.get(sym, sym)
                parts.append(jp + (f"x{count}" if count > 1 else ""))
            out.append(f"  {label}持駒: {' '.join(parts)}")
        else:
            out.append(f"  {label}持駒: なし")
    return "\n".join(out)


def _usi_to_sq(usi):
    """USI の指し手から到達マス (square) を求める。打ち・成りも to は usi[2:4]。"""
    try:
        to = usi[2:4]
        f = int(to[0])
        r = ord(to[1]) - ord("a") + 1
        if not (1 <= f <= 9 and 1 <= r <= 9):
            return None
        return (r - 1) * 9 + (9 - f)
    except (ValueError, IndexError):
        return None


def _cell(piece):
    """1 マス分 (3 セル幅)。後手は v、先手は半角空白を駒の前に置く。空マスは ' ・'。"""
    if piece is None:
        return " ・"
    sym = piece.symbol()
    key = "+" + sym[1].upper() if sym.startswith("+") else sym.upper()
    jp = PIECE_JP.get(key, "??")
    return ("v" if piece.color == shogi.WHITE else " ") + jp


def render_board(board, last_to_sq=None):
    """筋・段の座標軸つきで盤面を描く。直前手のマスは反転で強調する (端末のみ)。"""
    use_color = sys.stdout.isatty()
    out = ["  ９ ８ ７ ６ ５ ４ ３ ２ １", " +" + "-" * 27 + "+"]
    for rank_idx in range(9):
        row = "|"
        for col in range(9):
            sq = rank_idx * 9 + col
            cell = _cell(board.piece_at(sq))
            if sq == last_to_sq and use_color:
                cell = "\033[7m" + cell + "\033[0m"  # 直前手のマスを反転 (TTY のみ)
            row += cell
        out.append(row + "|" + KANSUJI[rank_idx])
    out.append(" +" + "-" * 27 + "+")
    return "\n".join(out)


def render(board, last=None):
    lines = [render_board(board, _usi_to_sq(last) if last else None), hands_str(board)]
    turn = "▲ 先手番" if board.turn == shogi.BLACK else "△ 後手番"
    lines.append(f"手数 {board.move_number} ・ {turn}")
    if last:
        lines.append(f"直前の手 {last}")
    if board.is_check():
        lines.append("** 王手 **")
    if board.is_checkmate():
        lines.append("** 詰み(手番側の負け)**")
    return "\n".join(lines)


def cmd_new(args):
    save(args.player, [])
    print(f"new game: state cleared for player={args.player}")
    board, _ = load(args.player)
    print(render(board))


def cmd_apply(args):
    board, moves = load(args.player)
    try:
        move = shogi.Move.from_usi(args.usi)
    except Exception as e:
        sys.exit(f"ERROR: bad USI '{args.usi}': {e}")
    if move not in board.legal_moves:
        sys.exit(
            f"ILLEGAL: {args.usi} is not legal in this position "
            f"(player={args.player}, move#{board.move_number}). "
            f"反則手。盤面ずれか不正手の可能性。"
        )
    board.push(move)
    moves.append(args.usi)
    save(args.player, moves)
    print(f"applied: {args.usi}")
    print(render(board, last=args.usi))
    if board.is_game_over():
        print("GAME_OVER")


def cmd_show(args):
    board, moves = load(args.player)
    last = moves[-1] if moves else None
    print(render(board, last=last))


def cmd_legal(args):
    board, _ = load(args.player)
    usis = sorted(m.usi() for m in board.legal_moves)
    print(f"{len(usis)} legal moves:")
    print(" ".join(usis))


def cmd_status(args):
    board, moves = load(args.player)
    turn = "black" if board.turn == shogi.BLACK else "white"
    print(
        f"turn={turn} move_number={board.move_number} "
        f"in_check={board.is_check()} checkmate={board.is_checkmate()} "
        f"game_over={board.is_game_over()} ply={len(moves)} "
        f"last={moves[-1] if moves else 'none'}"
    )


def main():
    p = argparse.ArgumentParser(description="agmsg-shogi board manager")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("new", "show", "legal", "status"):
        sp = sub.add_parser(name)
        sp.add_argument("--player", required=True)
    sa = sub.add_parser("apply")
    sa.add_argument("--player", required=True)
    sa.add_argument("usi")

    args = p.parse_args()
    {
        "new": cmd_new,
        "apply": cmd_apply,
        "show": cmd_show,
        "legal": cmd_legal,
        "status": cmd_status,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
