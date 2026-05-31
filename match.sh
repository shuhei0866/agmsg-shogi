#!/usr/bin/env bash
# agmsg-shogi の異種エンジン対戦ランチャー。
#
# 2 つの CLI エージェント (claude / codex / gemini) を cmux の別ペインで起動し、
# それぞれ先手 (sente) / 後手 (gote) として agmsg 経由で 1 局指させる。盤面は
# board.py、通信は agmsg スクリプト直叩き、思考は各エージェント自身が担う。
#
# Usage:
#   ./match.sh [sente-engine] [gote-engine]
#     engine: claude (default sente) | codex (default gote) | gemini
#   例: ./match.sh claude codex     # 先手 Claude Code vs 後手 Codex
#       ./match.sh gemini claude    # 先手 Gemini  vs 後手 Claude Code
#
# 注意: 既存の sente/gote の手列をリセットして新規対局を始める。進行中の対局が
# あれば先に終えること。
set -euo pipefail

ROOT="$HOME/Developer/agmsg-shogi"
PY="$ROOT/.venv/bin/python"
SK="$HOME/.agents/skills/agmsg/scripts"
SENTE="${1:-claude}"
GOTE="${2:-codex}"

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

P_SENTE="players/sente.md を読み、RULES.md に従って後手と1局指してください。あなたの agent_type は $(atype "$SENTE") です。"
P_GOTE="players/gote.md を読み、RULES.md に従って先手と1局指してください。あなたの agent_type は $(atype "$GOTE") です。"

# 盤面と agmsg のメッセージをリセット (新規対局)
"$PY" "$ROOT/board.py" new --player sente >/dev/null
"$PY" "$ROOT/board.py" new --player gote  >/dev/null
"$SK/inbox.sh" shogi sente >/dev/null 2>&1 || true
"$SK/inbox.sh" shogi gote  >/dev/null 2>&1 || true

# 専用 workspace を作り、1 ペイン目 (sente) を起動コマンド込みで開く
WS=$(cmux new-workspace --name "shogi: $SENTE vs $GOTE" --cwd "$ROOT" \
       --command "$(launch "$SENTE" "$P_SENTE")" --focus false \
     | grep -oE 'workspace:[0-9]+' | head -1)
echo "workspace: $WS  (先手 $SENTE 起動)"

# 2 ペイン目 (gote) を split で作り、起動コマンドを送る (ソケット混雑にリトライで耐える)
cmux new-split right --workspace "$WS" --focus false >/dev/null
SF2=$(cmux list-pane-surfaces --workspace "$WS" | grep -oE 'surface:[0-9]+' | tail -1)
for _ in 1 2 3 4 5; do
  cmux send --workspace "$WS" --surface "$SF2" "cd $ROOT && $(launch "$GOTE" "$P_GOTE")" 2>/dev/null && break || true
done
cmux send-key --workspace "$WS" --surface "$SF2" enter 2>/dev/null || true
echo "後手 $GOTE 起動 (surface $SF2)"

echo
echo "対局開始: $SENTE (先手) vs $GOTE (後手)"
echo "観戦: http://localhost:8011/?player=sente"
