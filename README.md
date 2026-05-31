# agmsg-shogi

Two CLI coding agents playing a game of shogi against each other — autonomously,
over [agmsg](https://github.com/fujibee/agmsg). Either side can be **Claude Code,
Codex, or Gemini CLI**, so cross-engine matches (e.g. Claude vs Codex) work too.

No human in the loop after kickoff. Each side is a separate CLI agent session;
they exchange moves through agmsg's shared SQLite mailbox, while
[python-shogi](https://github.com/gunyarakun/python-shogi) keeps each board legal.
It is the shogi cousin of agmsg's tic-tac-toe demo.

## How it works

Three layers, cleanly separated:

| Layer | Role | Thinks? |
|-------|------|---------|
| `board.py` | Board state, legal-move generation, checkmate detection (python-shogi wrapper) | no |
| agmsg | Carries USI moves between the two agents (shared SQLite mailbox) | no |
| CLI agent (Claude Code / Codex / Gemini) | Picks the move | **yes** |

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

# (optional) web viewer + evaluation graph
.venv/bin/python -m pip install fastapi uvicorn py7zr

# (optional, macOS/Apple Silicon) YaneuraOu engine + Suisho5 eval for the graph
mkdir -p engine && cd engine
gh release download V9.00   --repo yaneurao/YaneuraOu --pattern "*mac-all*"
gh release download suisho5 --repo yaneurao/YaneuraOu --pattern "Suisho5.7z"
../.venv/bin/python -c "import py7zr,glob; [py7zr.SevenZipFile(f).extractall() for f in glob.glob('*.7z')]"
cd ..
```

## Run a match

`match.sh` launches both players in separate cmux panes and assigns sente/gote.
Either side can be **Claude Code, Codex, or Gemini CLI** — the board and protocol
stay identical, only the player changes:

```bash
./match.sh claude codex      # sente: Claude Code,  gote: Codex
./match.sh gemini claude      # sente: Gemini CLI,   gote: Claude Code
./match.sh claude claude      # both Claude Code (the original demo)
```

Each engine starts with autonomy enabled (`--dangerously-skip-permissions` /
`--dangerously-bypass-approvals-and-sandbox` / `--approval-mode yolo`) and an
initial prompt pointing at `players/<role>.md`. From there the two agents trade
moves over agmsg (`send.sh`/`inbox.sh`, polled between turns) until checkmate or
resignation. `match.sh` resets the move lists, so finish any running game first.

To launch by hand instead, open two panes, start your agent in each
(`claude` / `codex` / `gemini`), and tell it to read `players/sente.md`
(or `gote.md`) and play.

## Watch in a browser (board + evaluation graph)

A small FastAPI server reads the live `state/*.moves` and serves each position as
SFEN; the frontend renders the board (Japanese pieces, coordinate axes, last-move
highlight), lets you scrub the game with a slider, and follows the live game. With
the YaneuraOu engine set up (see Setup), it also plots an **evaluation graph** from
Black's perspective (above 0 = sente better, below 0 = gote better).

```bash
cd web && ../.venv/bin/python -m uvicorn server:app --port 8011
# open http://localhost:8011/?player=sente
```

The server is read-only — it never writes to the game. Evaluation runs in the
background and is cached per position, so the page loads immediately and the graph
fills in as positions are scored. Tune search time via `MOVETIME_MS` in `web/server.py`.

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
match.sh            cross-engine match launcher (claude/codex/gemini → sente/gote)
players/
  RULES.md          shared turn-loop spec both players read
  sente.md          first-player kickoff
  gote.md           second-player kickoff
state/              per-player move lists (gitignored)
web/
  server.py         FastAPI: SFEN feed (/api/game) + eval feed (/api/eval, YaneuraOu)
  index.html        board viewer + Chart.js evaluation graph
engine/             YaneuraOu binary + Suisho5 eval (gitignored, see Setup)
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
