# agmsg-shogi

Two CLI coding agents playing shogi against each other — autonomously, over
[agmsg](https://github.com/fujibee/agmsg) — each with a distinct **playing-style
persona**. A shogi engine (YaneuraOu) supplies the candidate strong moves; the
agents don't try to out-search the engine, they **pick among its top moves in
character and banter with each other** as they go. Either side can be **Claude
Code, Codex, or Gemini CLI**, so cross-engine matches (e.g. Claude vs Codex) work too.

The split is deliberate: an LLM's edge here isn't search depth — an engine crushes
it at that — but natural-language banter and stylistic choice. So strength is the
engine's job and style is the agent's. `sente` plays an aggressive rapid-attacker,
`gote` a solid slow-game player; handed the same engine shortlist, they reach for
different moves.

No human in the loop after kickoff. Each side is a separate CLI agent session;
they exchange moves through agmsg's shared SQLite mailbox, while
[python-shogi](https://github.com/gunyarakun/python-shogi) keeps each board legal.
It is the shogi cousin of agmsg's tic-tac-toe demo.

## How it works

Cleanly separated layers:

| Layer | Role |
|-------|------|
| `board.py` | Board state, legal-move generation, checkmate detection (python-shogi wrapper) |
| `engine_suggest.py` | Runs YaneuraOu (MultiPV) on the position → top-N moves, each with an eval (centipawns) and principal variation |
| agmsg | Carries the USI move (+ a banter comment) between the two agents (shared SQLite mailbox) |
| CLI agent (Claude Code / Codex / Gemini) | **Picks one of the engine's top moves in its persona's style, and writes the banter** |

The key design choice: **only the USI move travels over agmsg — never the board.**
Both sides replay the same move sequence through python-shogi deterministically, so
the boards stay in sync from the moves alone. SFEN snapshots are never sent. An
illegal move from the opponent is caught by the receiver's `apply` (which rejects
it), so no referee process is needed.

One turn:

1. Receive the opponent's move (USI) over agmsg.
2. `board.py apply` it — this also validates it.
3. `engine_suggest.py` → the engine's top moves; pick one **within a centipawn
   margin of the best** that fits your persona (an aggressive vs a solid choice
   often diverge here).
4. `board.py apply` your own move.
5. Send it back over agmsg, with a comment in character.

## Architecture

```
   sente — aggressive rapid-attacker        gote — solid slow-game player
        │                                        │
        │  engine_suggest → top moves (+eval)    │  engine_suggest → top moves (+eval)
        │  board.py apply / show                 │  board.py apply / show
        ▼                                        ▼
   state/sente.moves                        state/gote.moves
        │                                        │
        └──────────────── agmsg ─────────────────┘
              USI move + banter comment,
              over a shared SQLite mailbox
```

## Personas & the margin knob

Strength comes from the engine, so the agents are free to differ on *style*. Two
personas ship in `players/`:

- **`persona_attacker.md` — aggressive rapid-attacker** (`sente`): pushes the rook
  pawn, favours captures and forcing moves, races for the opponent's king.
- **`persona_holder.md` — solid slow-game player** (`gote`): castles first, keeps
  good shape, invites the opponent to overextend and defends before counter-attacking.

Each persona is a selection policy over `engine_suggest`'s shortlist, not a free
hand: a move is only eligible if its eval is **within `--margin` centipawns of the
engine's best**. Inside that band the agent picks the move that best fits its style,
even if it isn't the top-rated one. Widen the margin and personalities show through
more (and play gets weaker); narrow it and both sides converge on the engine line.
The default is `200` (≈ two pawns) — wide enough to let style show, deliberately set
as a knob to experiment with (`./match.sh <sente> <gote> <margin>`).

## Setup

```bash
# python-shogi in a local venv
python3 -m venv .venv
.venv/bin/python -m pip install python-shogi

# agmsg (shared agent messaging)
bash <(curl -fsSL https://raw.githubusercontent.com/fujibee/agmsg/main/setup.sh)

# YaneuraOu engine + Suisho5 eval (macOS/Apple Silicon). Powers move selection
# (engine_suggest) and the eval graph. py7zr unpacks the release archives.
# Without it, agents fall back to choosing from board.py's legal moves unaided.
.venv/bin/python -m pip install py7zr
mkdir -p engine && cd engine
gh release download V9.00   --repo yaneurao/YaneuraOu --pattern "*mac-all*"
gh release download suisho5 --repo yaneurao/YaneuraOu --pattern "Suisho5.7z"
../.venv/bin/python -c "import py7zr,glob; [py7zr.SevenZipFile(f).extractall() for f in glob.glob('*.7z')]"
cd ..

# (optional) web viewer
.venv/bin/python -m pip install fastapi uvicorn
```

## Run a match

`match.sh` launches both players in separate cmux panes. `sente` is the aggressive
rapid-attacker, `gote` the solid slow-game player; either role can be **Claude Code,
Codex, or Gemini CLI** — the board, engine and protocol stay identical, only the
player changes:

```bash
./match.sh claude codex          # sente: Claude (attacker)  vs  gote: Codex (holder)
./match.sh gemini claude          # sente: Gemini (attacker)  vs  gote: Claude (holder)
./match.sh claude claude          # both Claude — same engine shortlist, two styles
./match.sh claude claude 300      # widen the style margin to 300cp
./match.sh claude claude 200 2    # room "2" — runs alongside another game
```

The third argument is the centipawn margin (default `200`, see **Personas & the
margin knob** above). The fourth is an optional **room** name for running games
**concurrently**: it suffixes the roles (`sente2` / `gote2`), so each game gets its
own `state/<role>.moves` and its own agmsg mailbox. agmsg routes by `(team, recipient)`,
so a distinct role name is enough to keep two games on the same `shogi` team from
crossing wires. Watch the second game at `/?player=sente2` (same server). Without a
room, a launch resets `sente` / `gote`, so use a room to avoid clobbering a game in
progress.

Each engine starts with autonomy enabled (`--dangerously-skip-permissions` /
`--dangerously-bypass-approvals-and-sandbox` / `--approval-mode yolo`) and an
initial prompt pointing at `players/<role>.md` and its persona. From there the two
agents trade moves over agmsg (`send.sh`/`inbox.sh`, polled between turns) until
checkmate or resignation. `match.sh` resets the move lists, so finish any running
game first.

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

## Post-game review (感想戦)

When a game ends, the two personas hold a **kansōsen** — the shogi ritual where the
players, now collaborators, replay the critical moments and discuss them. It is the
same split as the game itself, applied to analysis: a cheap deterministic oracle
decides **what to discuss** and grounds it in truth, and the LLMs supply the
**in-character reflection**.

```bash
# one command: extract turning points, then have the personas review them
./review.sh <game> players/persona_attacker.md players/persona_holder.md
# → state/<game>/kansousen.{md,json}; the viewer shows it at ?game=<game>
```

Two stages:

1. **`review_points.py`** evaluates every position with YaneuraOu, finds the moves
   with the largest eval swings (clamped so a winning→losing flip outranks shuffles
   deep in a decided game), and attaches the engine's best move + PV and each
   player's original comment. This is the **agenda** — the LLM never has to hunt for
   the critical moments (and so never bloats its context or misses them).
2. **`kansousen.py`** walks the agenda one turning point at a time. For each, the
   player who made the move reflects first, the opponent responds — each line
   generated by `claude -p` in that persona's voice, grounded by the engine truth in
   the prompt. Output is `kansousen.md` (to read) and `kansousen.json` (for the viewer).

In the browser the review appears as a panel under the board: the eval graph marks
each turning point, clicking a comment jumps the board to that position, and scrubbing
to a turning point highlights its discussion. The honest result is that a persona
will own its characteristic blind spot — the rapid-attacker confessing it "kept
watching its own attack and walked the king into trouble," with the engine's better
move shown right beside it.

## Playing out the mate (指し継ぎ)

Games end in **resignation**, so the board is never actually checkmated — the loser
gives up once the position is clearly lost. `mate_line.py` plays the game out from the
resignation position: YaneuraOu moves **both sides at best play** (the winner converts,
the loser resists as long as possible) until real checkmate, and writes the whole thing
— actual game **plus** the finishing sequence — as one move list.

```bash
.venv/bin/python mate_line.py --game <game>   # → state/<game>/mate.moves (+ mate_line.md)
# watch the resignation play out to mate:
#   http://localhost:8011/?player=mate&game=<game>
```

It reuses the SFEN replay convention, so the viewer shows it like any game — you scrub
straight from the real moves into the mate that never happened on the board. `review.sh`
runs this as its last step, so every post-game review leaves both the kansōsen and the
played-out mate. (`go mate` is avoided — this build ignores its time limit; the line is
found with plain `go movetime` self-play.)

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
board.py              python-shogi wrapper CLI (board only, no thinking)
engine_suggest.py     YaneuraOu MultiPV → top-N moves + eval + PV (move strength)
review_points.py      終局譜 → turning-point agenda (eval swings + engine truth + banter)
kansousen.py          感想戦 driver: walks the agenda, voices each side via claude -p
mate_line.py          plays the resignation position out to real checkmate (both sides best)
match.sh              match launcher (claude/codex/gemini → attacker/holder roles)
review.sh             one-command post-game review (review_points → kansousen → mate_line)
players/
  RULES.md            shared turn-loop spec both players read
  sente.md            first-player (attacker) kickoff
  gote.md             second-player (holder) kickoff
  persona_attacker.md aggressive rapid-attacker — selection policy + voice
  persona_holder.md   solid slow-game player — selection policy + voice
state/                per-player move lists (gitignored)
web/
  server.py           FastAPI: /api/game + /api/eval (YaneuraOu) + /api/review (感想戦)
  index.html          board viewer + Chart.js eval graph + post-game review panel
games/                permanent archives (kifu, banter, analysis, kansousen)
engine/               YaneuraOu binary + Suisho5 eval (gitignored, see Setup)
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

2 つの CLI コーディングエージェント(Claude Code / Codex / Gemini CLI のいずれか)が
[agmsg](https://github.com/fujibee/agmsg)(エージェント間メッセージング)経由で将棋を
1 局指す、人間不在の自律対局デモ。役割を 3 つに分けている。盤面の管理と反則判定は
python-shogi が担い、指し手の強さは将棋エンジン(やねうら王)が出す上位手に任せ、各
エージェントは**その上位手の中から自分の棋風で 1 手を選び、掛け合いのコメントを作る**
ことに専念する。LLM の比較優位は探索の深さではなく棋風の表現と自然言語の掛け合いに
あるので、強さはエンジンに預け、棋風と語りに集中させる狙いである。

棋風は 2 つ用意した。先手は早い仕掛けで主導権を取る「攻めの急戦党」、後手は玉を堅く
囲って受け切る「手厚い持久戦党」。どちらも engine_suggest が出す候補手のうち「最善手
から `--margin` センチポーン以内」の帯に入る手の中から、自分の棋風に合う 1 手を選ぶ。
帯を広げるほど棋風は立つが弱くなるので、この幅をパラメータとして動かし、棋風が立つか・
どれだけ弱くなるかを観察する。

設計の肝は「**盤面を送らず、指し手だけを送る**」こと。両者が同じ手順を python-shogi
で決定論的に再生するので、指し手の同期だけで盤面が一致する。相手の反則手は受信側の
`apply` が弾くため、審判プロセスを置く必要がない。
