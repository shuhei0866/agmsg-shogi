#!/usr/bin/env bash
# agmsg-shogi の棋風対戦ランチャー。
#
# 2 つの CLI エージェント (claude / codex / gemini) を cmux の別ペインで起動し、
# それぞれ先手 (攻めの急戦党) / 後手 (手厚い持久戦党) として agmsg 経由で 1 局指させる。
# 盤面は board.py、通信は agmsg スクリプト直叩き、指し手の強さは将棋エンジン
# (engine_suggest) が出す上位手に任せ、各エージェントはそこから自分の棋風で 1 手を
# 選んで掛け合う。
#
# Usage:
#   ./match.sh [sente-engine] [gote-engine] [margin-cp] [room]
#     engine    : claude (default sente) | codex (default gote) | gemini
#     margin-cp : 最善手から何 cp 以内を選択候補にするか (既定 200)。広いほど棋風が
#                 立ちやすいが弱くなる。棋風が立つか・どれだけ弱くなるかを見る実験用パラメータ。
#     room      : 対局を分離するための部屋名 (既定なし)。指定すると役割名が
#                 sente<room> / gote<room> になり、state ファイルも agmsg の受信箱も
#                 別々になる。**進行中の対局と並行して別の対局を走らせるときに使う。**
#   例: ./match.sh claude codex          # 先手 Claude(急戦) vs 後手 Codex(持久)
#       ./match.sh claude claude 300     # 両方 Claude、選択幅は広めの 300cp
#       ./match.sh claude claude 200 2   # room=2: 役割 sente2/gote2 で別対局を並行起動
#
# 注意: 指定した room の sente/gote の手列をリセットして新規対局を始める。既定 (room なし)
# は sente/gote を使うので、別の対局が sente/gote で進行中なら room を分けること。
# agmsg の受信箱は (team, 宛先役割) で分離されるので、team は shogi のまま役割名だけ
# 変えれば別対局どうしは混線しない。
set -euo pipefail

ROOT="$HOME/Developer/agmsg-shogi"
PY="$ROOT/.venv/bin/python"
SK="$HOME/.agents/skills/agmsg/scripts"
SENTE="${1:-claude}"
GOTE="${2:-codex}"
MARGIN="${3:-200}"
ROOM="${4:-}"

SROLE="sente${ROOM}"   # 先手の役割名 (board.py --player と agmsg の自分の役割名)
GROLE="gote${ROOM}"    # 後手の役割名

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

# 初期プロンプトは識別情報 (役割名・相手・棋風・team・margin・先後) を自己完結的に渡す。
# 機構は players/RULES.md、棋風は persona ファイルに委ねる。役割名を引数化しているので
# sente.md / gote.md のハードコード ("sente"/"gote") には依存しない。
P_SENTE="あなたは先手の「攻めの急戦党」です。あなたの役割名は ${SROLE}、相手は ${GROLE}。まず players/RULES.md と players/persona_attacker.md を読み、その手番ループと棋風に従って1局指してください。RULES.md の役割名は role=${SROLE}, opp=${GROLE} と読み替えます。board.py の --player と agmsg の自分の役割名には ${SROLE} を、agmsg の team は shogi、相手への送信先には ${GROLE} を使います。対局開始時の盤面は startpos にリセット済みです。指し手は engine_suggest の上位手から margin ${MARGIN} cp の帯内で自分の棋風に合うものを選びます。あなたは先手なので初手から始めます。agent_type は $(atype "$SENTE") です。"
P_GOTE="あなたは後手の「手厚い持久戦党」です。あなたの役割名は ${GROLE}、相手は ${SROLE}。まず players/RULES.md と players/persona_holder.md を読み、その手番ループと棋風に従って1局指してください。RULES.md の役割名は role=${GROLE}, opp=${SROLE} と読み替えます。board.py の --player と agmsg の自分の役割名には ${GROLE} を、agmsg の team は shogi、相手への送信先には ${SROLE} を使います。対局開始時の盤面は startpos にリセット済みです。指し手は engine_suggest の上位手から margin ${MARGIN} cp の帯内で自分の棋風に合うものを選びます。あなたは後手なので相手の初手を待つところから始めます(inbox.sh をポーリング)。agent_type は $(atype "$GOTE") です。"

# 盤面と agmsg の受信箱をリセット (この room の新規対局)
"$PY" "$ROOT/board.py" new --player "$SROLE" >/dev/null
"$PY" "$ROOT/board.py" new --player "$GROLE" >/dev/null
"$SK/inbox.sh" shogi "$SROLE" >/dev/null 2>&1 || true
"$SK/inbox.sh" shogi "$GROLE" >/dev/null 2>&1 || true

# 専用 workspace を作り、1 ペイン目 (sente) を起動コマンド込みで開く
WSNAME="shogi: 急戦 $SENTE vs 持久 $GOTE${ROOM:+ (room $ROOM)}"
WS=$(cmux new-workspace --name "$WSNAME" --cwd "$ROOT" \
       --command "$(launch "$SENTE" "$P_SENTE")" --focus false \
     | grep -oE 'workspace:[0-9]+' | head -1)
SF1=$(cmux list-pane-surfaces --workspace "$WS" | grep -oE 'surface:[0-9]+' | head -1)
echo "workspace: $WS  (先手=急戦 $SENTE 起動, 役割 $SROLE, surface $SF1)"

# 2 ペイン目 (gote) を split で作る。surface は new-split 自身の出力 ("OK surface:N
# workspace:M") から取る。list-pane-surfaces は split 直後の 2 ペイン目を出さないことが
# あり、それを誤ると後手の起動コマンドが先手ペインに送られて両者が同居してしまう。
SF2=$(cmux new-split right --workspace "$WS" --focus false 2>/dev/null | grep -oE 'surface:[0-9]+' | head -1)
if [ -z "$SF2" ]; then
  echo "warning: 後手ペインの surface を取得できませんでした (new-split の出力なし)" >&2
  exit 1
fi
# 起動コマンドを送る (ソケット混雑にリトライで耐える)
for _ in 1 2 3 4 5; do
  cmux send --workspace "$WS" --surface "$SF2" "cd $ROOT && $(launch "$GOTE" "$P_GOTE")" 2>/dev/null && break || true
done
cmux send-key --workspace "$WS" --surface "$SF2" enter 2>/dev/null || true
echo "後手=持久 $GOTE 起動 (surface $SF2, 役割 $GROLE)"

echo
echo "対局開始: $SENTE (先手・急戦) vs $GOTE (後手・持久)  margin=${MARGIN}cp${ROOM:+  room=$ROOM}"
echo "観戦: http://localhost:8011/?player=$SROLE"
