# あなたは先手(sente)

まず `~/Developer/agmsg-shogi/players/RULES.md` を読み、その手番ループに従って 1 局指す。

- あなたの役割名: **sente**(先手)、相手: **gote**
- board.py の `--player` には常に `sente` を渡す。
- あなたのエージェント種別 `<type>`(claude-code / codex / gemini)は、この対局を
  起動した側のプロンプトで伝えられる。join.sh の 3 番目の引数に使う。

## 開始手順

1. agmsg に参加する:
   `~/.agents/skills/agmsg/scripts/join.sh shogi sente <type> ~/Developer/agmsg-shogi`
2. `~/Developer/agmsg-shogi/.venv/bin/python ~/Developer/agmsg-shogi/board.py new --player sente`
   で盤面を初期化する。
3. あなたは先手なので、**初手を指すところから始める**(RULES.md の C → D)。
4. 以降は RULES.md の手番ループ(A→B→C→D→E)を、対局が終わるまで繰り返す。

初手は好きに選んでよい。居飛車なら `7g7f` や `2g2f`、振り飛車なら `6g6f` あたり。
