#!/usr/bin/env bash
# agmsg-shogi の棋風対戦ランチャー。
#
# 2 つの CLI エージェント (claude / codex / gemini) を cmux の別ペインで起動し、
# それぞれ先手 (sente=攻めの急戦党) / 後手 (gote=手厚い持久戦党) として agmsg 経由で
# 1 局指させる。盤面は board.py、通信は agmsg スクリプト直叩き、指し手の強さは
# 将棋エンジン (engine_suggest) が出す上位手に任せ、各エージェントはそこから自分の
# 棋風で 1 手を選んで掛け合う。
#
# Usage:
#   ./match.sh [sente-engine] [gote-engine] [margin-cp]
#     engine    : claude (default sente) | codex (default gote) | gemini
#     margin-cp : 最善手から何 cp 以内を選択候補にするか (既定 200)。広いほど棋風が
#                 立ちやすいが弱くなる。棋風が立つか・どれだけ弱くなるかを見る実験用パラメータ。
#   例: ./match.sh claude codex        # 先手 Claude(急戦) vs 後手 Codex(持久)
#       ./match.sh claude claude 300   # 両方 Claude、選択幅は広めの 300cp
#
# 注意: 既存の sente/gote の手列をリセットして新規対局を始める。進行中の対局が
# あれば先に終えること。
set -euo pipefail

ROOT="$HOME/Developer/agmsg-shogi"
PY="$ROOT/.venv/bin/python"
SK="$HOME/.agents/skills/agmsg/scripts"
SENTE="${1:-claude}"
GOTE="${2:-codex}"
MARGIN="${3:-200}"

atype() {
  case "$1" in
    claude) echo claude-code ;;
    codex)  echo codex ;;
    gemini) echo gemini ;;
    *) echo "unknown engine: $1" >&2; exit 1 ;;
  esac
}

# エンジン別の「自律起動コマンド + 初期プロンプト」を組み立てる
launch() {  # $1=engine  $2=prompt
  case "$1" in
    claude) printf "claude --dangerously-skip-permissions '%s'" "$2" ;;
    codex)  printf "codex --dangerously-bypass-approvals-and-sandbox '%s'" "$2" ;;
    gemini) printf "gemini --approval-mode yolo -i '%s'" "$2" ;;
  esac
}

P_SENTE="あなたは先手・攻めの急戦党です。players/sente.md と players/persona_attacker.md と players/RULES.md を読み、エンジン(engine_suggest)の上位手から自分の棋風で手を選んで後手と1局指してください。SUGGEST には --margin ${MARGIN} を使います。あなたの agent_type は $(atype "$SENTE") です。"
P_GOTE="あなたは後手・手厚い持久戦党です。players/gote.md と players/persona_holder.md と players/RULES.md を読み、エンジン(engine_suggest)の上位手から自分の棋風で手を選んで先手と1局指してください。SUGGEST には --margin ${MARGIN} を使います。あなたの agent_type は $(atype "$GOTE") です。"

# 盤面と agmsg のメッセージをリセット (新規対局)
"$PY" "$ROOT/board.py" new --player sente >/dev/null
"$PY" "$ROOT/board.py" new --player gote  >/dev/null
"$SK/inbox.sh" shogi sente >/dev/null 2>&1 || true
"$SK/inbox.sh" shogi gote  >/dev/null 2>&1 || true

# 専用 workspace を作り、1 ペイン目 (sente) を起動コマンド込みで開く
WS=$(cmux new-workspace --name "shogi: 急戦 $SENTE vs 持久 $GOTE" --cwd "$ROOT" \
       --command "$(launch "$SENTE" "$P_SENTE")" --focus false \
     | grep -oE 'workspace:[0-9]+' | head -1)
echo "workspace: $WS  (先手=急戦 $SENTE 起動)"

# 2 ペイン目 (gote) を split で作り、起動コマンドを送る (ソケット混雑にリトライで耐える)
cmux new-split right --workspace "$WS" --focus false >/dev/null
SF2=$(cmux list-pane-surfaces --workspace "$WS" | grep -oE 'surface:[0-9]+' | tail -1)
for _ in 1 2 3 4 5; do
  cmux send --workspace "$WS" --surface "$SF2" "cd $ROOT && $(launch "$GOTE" "$P_GOTE")" 2>/dev/null && break || true
done
cmux send-key --workspace "$WS" --surface "$SF2" enter 2>/dev/null || true
echo "後手=持久 $GOTE 起動 (surface $SF2)"

echo
echo "対局開始: $SENTE (先手・急戦) vs $GOTE (後手・持久)  選択幅 margin=${MARGIN}cp"
echo "観戦: http://localhost:8011/?player=sente"
