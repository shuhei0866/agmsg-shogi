#!/usr/bin/env bash
# 終局した対局の感想戦 (両 AI による振り返り) を 1 コマンドで作る。
#
# review_points.py で評価値の転換点を抽出し (決定論)、kansousen.py が各転換点を
# persona の声で語らせる (claude -p)。出力は state/<game>/kansousen.{md,json} に置くので、
# ビューアは http://localhost:8011/?player=sente&game=<game> でそのまま感想戦を表示する。
#
# Usage:
#   ./review.sh <game> <sente-persona> <gote-persona> [points] [model]
#     game          : 対局 ID (match.sh の room と同じ)。空文字なら既定対局 (state/)。
#     sente-persona : 先手が使った persona ファイル (例 players/persona_attacker.md)
#     gote-persona  : 後手が使った persona ファイル (例 players/persona_holder.md)
#     points        : 振り返る転換点の数 (既定 6)
#     model         : claude -p のモデル (既定 haiku。声の生成に強い読みは要らない)
#   例: ./review.sh 3 players/persona_attacker.md players/persona_holder.md
#
# 注意: AGMSG_GAME で state/<game>/ に分離して指した対局が対象 (現行の match.sh の規約)。
set -euo pipefail

ROOT="$HOME/Developer/agmsg-shogi"
PY="$ROOT/.venv/bin/python"
GAME="${1:-}"
SP="${2:?先手の persona ファイルを渡してください}"
GP="${3:?後手の persona ファイルを渡してください}"
K="${4:-6}"
MODEL="${5:-claude-haiku-4-5-20251001}"

OUT="$ROOT/state/${GAME}"
mkdir -p "$OUT"

echo "[1/3] 転換点を抽出中 (やねうら王)…"
AGMSG_GAME="$GAME" "$PY" "$ROOT/review_points.py" \
  --game "$GAME" --sente-name "sente${GAME}" --gote-name "gote${GAME}" \
  -k "$K" --json > "$OUT/agenda.json"

echo "[2/3] 感想戦を生成中 (persona の声)…"
"$PY" "$ROOT/kansousen.py" \
  --agenda "$OUT/agenda.json" --sente-persona "$SP" --gote-persona "$GP" \
  -k "$K" --model "$MODEL" \
  --out-md "$OUT/kansousen.md" --out-json "$OUT/kansousen.json"

echo "[3/3] 投了局面から詰みまで指し継ぎ中 (やねうら王)…"
"$PY" "$ROOT/mate_line.py" --game "$GAME" --out "$OUT/mate.moves"

echo
echo "感想戦:       $OUT/kansousen.md"
echo "指し継ぎ:     $OUT/mate.moves  (投了 → 詰み)"
echo "観戦:         http://localhost:8011/?player=sente&game=$GAME"
echo "指し継ぎ観戦: http://localhost:8011/?player=mate&game=$GAME"
