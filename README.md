# agmsg-shogi

Two Claude Code agents playing a game of shogi against each other — autonomously,
over [agmsg](https://github.com/fujibee/agmsg).

No human in the loop after kickoff. Each side is a separate Claude Code session;
they exchange moves through agmsg's shared SQLite mailbox, while
[python-shogi](https://github.com/gunyarakun/python-shogi) keeps each board legal.
It is the shogi cousin of agmsg's tic-tac-toe demo.

## How it works

Three layers, cleanly separated:

| Layer | Role | Thinks? |
|-------|------|---------|
| `board.py` | Board state, legal-move generation, checkmate detection (python-shogi wrapper) | no |
| agmsg | Carries USI moves between the two agents (shared SQLite mailbox) | no |
| Claude Code | Picks the move | **yes** |

The key design choice: **only the USI move travels over agmsg — never the board.**
Both sides replay the same move sequence through python-shogi deterministically, so
the boards stay in sync from the moves alone. SFEN snapshots are never sent. An
illegal move from the opponent is caught by the receiver's `apply` (which rejects
it), so no referee process is needed.

One turn:

1. Receive the opponent's move (USI) over agmsg.
2. `board.py apply` it — this also validates it.
3. `board.py legal` → pick a move.
4. `board.py apply` your own move.
5. Send it back over agmsg.

## Architecture

```
   sente (Claude Code)                      gote (Claude Code)
        │                                        │
        │  board.py apply / legal / show         │  board.py apply / legal / show
        ▼                                        ▼
   state/sente.moves                        state/gote.moves
        │                                        │
        └──────────────── agmsg ─────────────────┘
              USI move (+ optional comment),
              over a shared SQLite mailbox
```

## Setup

```bash
# python-shogi in a local venv
python3 -m venv .venv
.venv/bin/python -m pip install python-shogi

# agmsg (shared agent messaging)
bash <(curl -fsSL https://raw.githubusercontent.com/fujibee/agmsg/main/setup.sh)
```

## Run a match

Open two terminal panes. In each:

```bash
cd agmsg-shogi && claude
```

Then give each session its role:

- **Pane 1 (sente / first player):** `players/sente.md を読んで対局して`
- **Pane 2 (gote / second player):** `players/gote.md を読んで対局して`

Sente plays the first move; from there the two agents trade moves over agmsg until
checkmate or resignation. Each session joins agmsg team `shogi` under its role name
and fixes that role with `/agmsg actas <role>` so monitor delivery stays scoped to
one inbox.

## `board.py`

A thin python-shogi CLI — it manages the board and never thinks. State lives in
`state/<player>.moves` (one USI move per line, replayed to reconstruct the board).

| Command | What it does |
|---------|--------------|
| `new --player <p>` | reset the move list |
| `apply --player <p> <usi>` | validate + append a move; rejects illegal moves |
| `show --player <p>` | print the board |
| `legal --player <p>` | list legal moves (USI) |
| `status --player <p>` | turn / check / checkmate / game-over |

Run it with the venv python:

```bash
.venv/bin/python board.py show --player sente
```

## Files

```
board.py            python-shogi wrapper CLI (board only, no thinking)
players/
  RULES.md          shared turn-loop spec both players read
  sente.md          first-player kickoff
  gote.md           second-player kickoff
state/              per-player move lists (gitignored)
```

## Demo

The two agents trade not just moves but **commentary** — they greet each other and
narrate their opening plan as they go:

```
▲7六歩 ─「角道を開けます。よろしくお願いします」
△3四歩 ─「こちらも角道を開けます。よろしくお願いします」
▲2六歩 ─「飛車先を伸ばします。居飛車でいきます」
△8四歩 ─「私も飛車先を伸ばします。相居飛車でいきましょう」
▲2五歩 ─ ...
```

_(Full game record to be filled in once a match plays to its conclusion.)_

---

## 日本語概要

2 つの Claude Code が [agmsg](https://github.com/fujibee/agmsg)(エージェント間
メッセージング)経由で将棋を 1 局指す、人間不在の自律対局デモ。盤面の管理と反則
判定は python-shogi に任せ、agmsg で運ぶのは USI 形式の指し手だけ、手を考えるのは
Claude 自身が担う。agmsg の三目並べデモを将棋に置き換えたもの。

設計の肝は「**盤面を送らず、指し手だけを送る**」こと。両者が同じ手順を python-shogi
で決定論的に再生するので、指し手の同期だけで盤面が一致する。相手の反則手は受信側の
`apply` が弾くため、審判プロセスを置く必要がない。
