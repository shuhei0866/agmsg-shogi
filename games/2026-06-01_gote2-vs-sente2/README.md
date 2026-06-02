# gote2 vs sente2 — 2026-06-01

agmsg 経由で 2 体の claude-code が指した1局と、その感想戦のアーカイブ。

- **後手 gote2**: 手厚い持久戦党（[persona](../../players/persona_holder.md)）
- **先手 sente2**: 攻め将棋党（[persona](../../players/persona_attacker.md)）
- **結果**: 後手 gote2 の勝ち（先手が58手目を見て投了）
- **指し手の強さ**: やねうら王の上位手（margin 200cp 帯内）から各 persona が選択

## 中身

| ファイル | 内容 |
|----------|------|
| [game.md](game.md) | 実戦58手の棋譜（USI＋日本語＋評価値） |
| [banter.md](banter.md) | 対局中の掛け合い全文（agmsg ログから抽出、61通） |
| [analysis.md](analysis.md) | 感想戦・解析（寄せ筋・▲４九玉の詰み・形勢推移・戦略考察） |
| [mate_line.md](mate_line.md) | 58手目以降を詰みまで再生（59〜130手） |
| [mate_line.moves](mate_line.moves) | 上記の手列（viewer 用） |
| [analyze_mate.py](analyze_mate.py) | 寄せを詰みまで再生した解析スクリプト |

## viewer で見る

```
cd web && ../.venv/bin/python -m uvicorn server:app --port 8011
# 実戦:   http://localhost:8011/?player=gote2
# 詰みまで: http://localhost:8011/?player=gote2_mate   ※ mate_line.moves を state/ に置く必要あり
```

※ viewer は `state/<player>.moves` を読む。`mate_line.moves` を見るには `state/gote2_mate.moves` として置く（`state/` は gitignore 対象なので、この games/ ディレクトリが恒久版）。
