#!/usr/bin/env bash
set -euo pipefail
# agmsg-shogi の対局用ラッパー。対局 ID (AGMSG_GAME) と役割 (AGMSG_ROLE) を環境変数から
# 取り、agmsg の name を <role><game> に固定して send / inbox / join を team=shogi で叩く。
# 役割名や team をエージェントが直に書かないことで、並行対局どうしの取り違えを防ぐ。
# エージェントが引数を打ち間違えても、name と宛先は環境変数から決まるので別対局には届かない。
#
# 必要な環境変数:
#   AGMSG_ROLE  自分の役割 (sente | gote)。必須。
#   AGMSG_GAME  対局 ID (例 2)。空ならデフォルト対局 (name は素の sente / gote)。
#   AGMSG_TYPE  エージェント種別 (claude-code | codex | gemini)。join に使う。既定 claude-code。
#
# Usage:
#   gmsg.sh send "<USI と任意コメント>"   相手へ 1 手送る (from=自分, to=相手)
#   gmsg.sh inbox [--quiet]               自分宛の未読を読む (読んだら既読化)
#   gmsg.sh join                          team shogi に自分の name で参加する
#   gmsg.sh whoami                        解決された name / opp / team を表示 (デバッグ用)

AGMSG_SK="$HOME/.agents/skills/agmsg/scripts"
PROJECT="$HOME/Developer/agmsg-shogi"
TEAM="shogi"

ROLE="${AGMSG_ROLE:?AGMSG_ROLE が未設定です (sente か gote を環境変数で渡してください)}"
GAME="${AGMSG_GAME:-}"
TYPE="${AGMSG_TYPE:-claude-code}"

case "$ROLE" in
  sente) OPP_ROLE="gote" ;;
  gote)  OPP_ROLE="sente" ;;
  *) echo "AGMSG_ROLE は sente か gote のどちらかです (現在: '$ROLE')" >&2; exit 1 ;;
esac

NAME="${ROLE}${GAME}"      # 例: sente / sente2
OPP="${OPP_ROLE}${GAME}"   # 例: gote  / gote2

CMD="${1:-}"
[ -n "$CMD" ] || { echo "Usage: gmsg.sh <send|inbox|join|whoami> [args]" >&2; exit 1; }
shift || true

case "$CMD" in
  send)
    BODY="${1:?Usage: gmsg.sh send \"<USI と任意コメント>\"}"
    exec "$AGMSG_SK/send.sh" "$TEAM" "$NAME" "$OPP" "$BODY"
    ;;
  inbox)
    exec "$AGMSG_SK/inbox.sh" "$TEAM" "$NAME" "$@"
    ;;
  join)
    exec "$AGMSG_SK/join.sh" "$TEAM" "$NAME" "$TYPE" "$PROJECT"
    ;;
  whoami)
    echo "team=$TEAM name=$NAME opp=$OPP type=$TYPE game=${GAME:-<none>}"
    ;;
  *)
    echo "unknown command: '$CMD' (send|inbox|join|whoami)" >&2; exit 1
    ;;
esac
