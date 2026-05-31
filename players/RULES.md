# 対局ルール — agmsg-shogi プレイヤー手番ループ

あなたは 2 つの CLI エージェント(Claude Code / Codex / Gemini CLI のいずれか)の
一方で、もう一方のエージェントと将棋を 1 局指す。盤面の管理とルール判定は
`board.py`(python-shogi のラッパー)に任せ、あなたは**指し手を考えることだけ**に
集中する。手のやり取りは agmsg(エージェント間メッセージング)の共有 SQLite を介して
行う。どのエージェントでも同じ手順で指せるよう、agmsg は**スキルではなくスクリプトを
直接叩く**。

## 前提

- あなたの役割(先手 sente / 後手 gote)・相手・エージェント種別は、起動時に読む
  `sente.md` か `gote.md` で指定される。以下、自分を `<role>`、相手を `<opp>`、
  自分のエージェント種別(claude-code / codex / gemini)を `<type>` と書く。
- 盤面エンジン。どのディレクトリからでも動く。以下これを `BOARD` と呼ぶ:

  ```
  ~/Developer/agmsg-shogi/.venv/bin/python ~/Developer/agmsg-shogi/board.py
  ```

  **重要**: `python3 board.py` では動かない(python-shogi はこの venv にだけ入っている)。
  必ず上記の `BOARD`(venv の python のフルパス)を使う。サブコマンドは
  `new` / `show` / `legal` / `apply` / `status` の 5 つだけ。

- agmsg は次のスクリプトを直接叩く(team 名は `shogi`)。`/agmsg` や `$agmsg` の
  スキルは使わない(エージェントによって有無が違うため):

  ```
  join : ~/.agents/skills/agmsg/scripts/join.sh shogi <role> <type> ~/Developer/agmsg-shogi
  送信 : ~/.agents/skills/agmsg/scripts/send.sh  shogi <role> <opp> "<メッセージ>"
  受信 : ~/.agents/skills/agmsg/scripts/inbox.sh shogi <role>
  ```

## 通信フォーマット

1 メッセージ = `<USI> <任意コメント>`。

- 先頭の空白までが**指し手の USI**。例: 通常の手 `7g7f`、駒を打つ手 `P*5e`、
  成る手 `8h2b+`。
- 残りは自由コメント(読み筋・方針・挨拶、日本語でよい)。観賞用で盤面には影響しない。

受け取ったメッセージからは、先頭トークンだけを USI として取り出して使う。

## 1 手の流れ

### A. 相手の手を受け取る(先手の初手だけはこの A を飛ばす)

- `inbox.sh shogi <role>` を実行して相手のメッセージを読む。
- まだ届いていなければ(空なら)数秒おきに `inbox.sh` を繰り返し、相手の手が来るまで待つ。
- 届いたメッセージの先頭トークンを相手の USI として、盤面に適用する:
  `BOARD apply --player <role> <相手の USI>`
- `ILLEGAL` が返ったら、相手が反則したか盤面がずれている。相手に伝えて対局を止め、
  ユーザーに報告する。

### B. 局面を確認する

- `BOARD show --player <role>` で盤面、`BOARD status --player <role>` で手番・王手・詰み。
- `checkmate=True` で**手番が自分**なら詰まされている。投了する:
  `send.sh shogi <role> <opp> "投了 — お見事でした"` を送り、対局を終えて報告する。

### C. 自分の手を選ぶ

- `BOARD legal --player <role>` で合法手(USI)を一覧する。
- **必ずこの一覧の中から** 1 手を選ぶ。将棋の棋理(駒得・玉の安全・手得・好形)に従う。
- 短いコメント(読み筋や方針)を用意してよい(任意)。

### D. 自分の手を適用して送信する

- `BOARD apply --player <role> <自分の USI>` で自分の盤面にも適用する。
- 適用後の status で相手を詰ませた(`checkmate=True`)なら、あなたの勝ち。勝利の言葉を添える。
- `send.sh shogi <role> <opp> "<自分の USI> <コメント>"` で相手に送る。

### E. 相手の番

- A に戻り、`inbox.sh` のポーリングで相手の手を待つ。

## 終局の扱い

- どちらかが詰み → 投了するか勝ちを宣言して終了する。
- 反則(`ILLEGAL`)→ その場で止めて、ユーザーに報告する。
- 明らかな劣勢で続ける意味が無いと判断したら、無理に指さず投了してよい。

## 心構え

- あなたは対局者である。1 手ずつ丁寧に読み、相手の手の意図も汲む。
- コメントで棋風や感情を出してよい。これは観賞物でもある。
- 盤面の真実は常に board.py にある。自分の記憶があやしいときは board.py の出力を信じる。
