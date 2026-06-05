# sente50 vs gote50 — 2026-06-03(margin 50cp)

agmsg 経由で 2 体の claude-code が指した 1 局と感想戦のアーカイブ。
**前局([gote2 vs sente2](../2026-06-01_gote2-vs-sente2/)、margin 200cp)の「受け勝ち」から、
margin を 50cp に絞っただけで「攻め勝ち」へ逆転した**ことが本局の主題。

- **先手 sente50**: 攻めの急戦党([persona](../../players/persona_attacker.md))
- **後手 gote50**: 手厚い持久戦党([persona](../../players/persona_holder.md))
- **margin**: 50cp(最善手から 50cp 以内の候補から persona が選択)
- **結果**: 先手 sente50 の勝ち(73 手、後手投了)
- **敗着**: 後手 28 手目 △7五歩 ── 受けが本筋 △8八角成 を捨て、目先の評価値に釣られて
  攻め合いに出た楽観(深く読むと −313 の悪手)

## 中身

| ファイル | 内容 |
|----------|------|
| [game.moves](game.moves) | 実戦 73 手の手列(USI、viewer 用) |
| [banter_full.txt](banter_full.txt) | 対局中の掛け合い + 投了後の感想戦(agmsg ログ、78 通) |
| [analysis.md](analysis.md) | 感想戦・解析(margin で勝者逆転 / 藤井聡太モデル / 敗着の構造) |

## 一番の発見

`margin` は「強さ ⇄ 棋風」だけでなく **「攻め有利 ⇄ 受け有利」を決めるツマミ**だった:

| margin | 攻めの振る舞い | 勝者 |
|--------|----------------|------|
| 200cp(広い) | committal な無理攻めで自滅 | **受け** |
| 50cp(狭い) | 最善寄りしか選べず傷が出ない | **攻め** |

受けは「相手のミス」に賭ける戦略なので、最善寄りの世界(低 margin = 藤井聡太型)では
咎めるミスが来ず空振りする。負けた gote50 自身が、敗着 △7五歩で「自分の棋風の本筋
(辛抱)を、目先の評価値に引かれて踏み外した」と自己分析しているのが白眉。
詳細は [analysis.md](analysis.md)。

## viewer で見る

```
cd web && ../.venv/bin/python -m uvicorn server:app --port 8011
# game.moves を state/<name>.moves に置いて http://localhost:8011/?player=<name>
```
