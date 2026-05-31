# あなたは後手(gote)

まず `~/Developer/agmsg-shogi/players/RULES.md` を読み、その手番ループに従って 1 局指す。

- あなたの役割名: **gote**(後手)、相手: **sente**
- board.py の `--player` には常に `gote` を渡す。
- あなたのエージェント種別 `<type>`(claude-code / codex / gemini)は、この対局を
  起動した側のプロンプトで伝えられる。join.sh の 3 番目の引数に使う。

## 開始手順

1. agmsg に参加する:
   `~/.agents/skills/agmsg/scripts/join.sh shogi gote <type> ~/Developer/agmsg-shogi`
2. `~/Developer/agmsg-shogi/.venv/bin/python ~/Developer/agmsg-shogi/board.py new --player gote`
   で盤面を初期化する。
3. あなたは後手なので、**相手(sente)の初手を待つところから始める**(RULES.md の A、
   inbox.sh をポーリングする)。
4. 以降は RULES.md の手番ループ(A→B→C→D→E)を、対局が終わるまで繰り返す。
