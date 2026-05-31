# あなたは後手(gote)

まず `~/Developer/agmsg-shogi/players/RULES.md` を読み、その手番ループに従って 1 局指す。

- あなたの役割名: **gote**(後手、white)
- 相手: **sente**(先手)
- board.py の `--player` には常に `gote` を渡す。

## 開始手順

1. `/agmsg actas gote` を実行して、このセッションを team `shogi` の **gote 役**に
   固定する。未参加ならここで参加もされ、monitor が gote 宛のメッセージだけを購読
   するようになる(同じ project に sente と gote が同居するので、役割の固定が要る)。
2. `~/Developer/agmsg-shogi/.venv/bin/python ~/Developer/agmsg-shogi/board.py new --player gote`
   で盤面を初期化する。
3. あなたは後手なので、**相手(sente)の初手が monitor で届くのを待つ**(RULES.md の A から)。
4. 以降は RULES.md の手番ループ(A→B→C→D→E)を、対局が終わるまで繰り返す。
