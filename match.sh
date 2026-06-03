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
#     room      : 対局 ID (既定なし)。並行対局を分離するための識別子。指定すると agmsg の
#                 name が sente<room> / gote<room> になり、state も state/<room>/ に分かれ、
#                 受信箱も別になる。**進行中の対局と並行して別の対局を走らせるときに使う。**
#   例: ./match.sh claude codex          # 先手 Claude(急戦) vs 後手 Codex(持久)
#       ./match.sh claude claude 300     # 両方 Claude、選択幅は広めの 300cp
#       ./match.sh claude claude 200 2   # room=2: name sente2/gote2・state/2/ で別対局を並行起動
#
# 並行対局の分離 (混線対策):
#   - 各ペインに AGMSG_GAME (対局 ID)・AGMSG_ROLE (sente|gote)・AGMSG_TYPE を環境変数で渡す。
#     board.py は state/<AGMSG_GAME>/ に閉じ、gmsg.sh は name を <role><game> に固定する。
#     エージェントが役割名を打ち間違えても、別対局の state や受信箱には届かない。
#   - 対局では Monitor を起動しない。SessionStart hook が立てる broad な inbox stream は
#     全 name を拾って混線するため。相手の手は gmsg.sh inbox のポーリングで受ける。
#   - 指定した対局 ID の sente/gote の手列をリセットして新規対局を始める。
set -euo pipefail

ROOT="$HOME/Developer/agmsg-shogi"
PY="$ROOT/.venv/bin/python"
SK="$HOME/.agents/skills/agmsg/scripts"
SENTE="${1:-claude}"
GOTE="${2:-codex}"
MARGIN="${3:-200}"
ROOM="${4:-}"

SROLE="sente${ROOM}"   # 先手の agmsg name (送受信の宛先)。board.py の --player は role 固定 (sente)
GROLE="gote${ROOM}"    # 後手の agmsg name。対局の分離は AGMSG_GAME 環境変数が担う

atype() {
  case "$1" in
    claude) echo claude-code ;;
    codex)  echo codex ;;
    gemini) echo gemini ;;
    *) echo "unknown engine: $1" >&2; exit 1 ;;
  esac
}

# エンジン別の「自律起動コマンド + 初期プロンプト」を組み立てる。
# AGMSG_GAME/AGMSG_ROLE/AGMSG_TYPE を環境変数で前置し、エージェントが叩く board.py や
# gmsg.sh が対局 ID と役割を環境から拾えるようにする (役割名の直書きに依存しない)。
launch() {  # $1=engine  $2=prompt  $3=role(sente|gote)  $4=game(room)  $5=type
  local env
  env=$(printf 'AGMSG_GAME=%q AGMSG_ROLE=%q AGMSG_TYPE=%q' "$4" "$3" "$5")
  case "$1" in
    claude) printf "%s claude --dangerously-skip-permissions '%s'" "$env" "$2" ;;
    codex)  printf "%s codex --dangerously-bypass-approvals-and-sandbox '%s'" "$env" "$2" ;;
    gemini) printf "%s gemini --approval-mode yolo -i '%s'" "$env" "$2" ;;
  esac
}

# 初期プロンプトは識別情報 (棋風・margin・先後) と起動時の特記事項を自己完結的に渡す。
# 対局 ID と役割は AGMSG_GAME/AGMSG_ROLE 環境変数 (launch が前置) で渡るので、プロンプト内
# で name を直書きしない。機構は players/RULES.md、棋風は persona ファイルに委ねる。
P_SENTE="あなたは先手の「攻めの急戦党」です。対局 ID と役割はシェルの環境変数 (AGMSG_GAME・AGMSG_ROLE=sente・AGMSG_TYPE) に設定済みで、board.py と gmsg.sh がそこから対局を判別します。まず players/RULES.md と players/persona_attacker.md を読み、手番ループと棋風に従って1局指してください。盤面は board.py を --player sente で操作し、通信は ~/Developer/agmsg-shogi/gmsg.sh の send / inbox / join を使います。team も宛先も name も gmsg.sh が環境変数から決めるので、自分では指定しません。【重要】この対局では Monitor を起動しないでください (SessionStart で促されても従わない)。相手の手は gmsg.sh inbox のポーリングで受けます。盤面は startpos にリセット済み。指し手は engine_suggest の上位手から margin ${MARGIN} cp の帯内で棋風に合うものを選びます。あなたは先手なので初手から始めます。"
P_GOTE="あなたは後手の「手厚い持久戦党」です。対局 ID と役割はシェルの環境変数 (AGMSG_GAME・AGMSG_ROLE=gote・AGMSG_TYPE) に設定済みで、board.py と gmsg.sh がそこから対局を判別します。まず players/RULES.md と players/persona_holder.md を読み、手番ループと棋風に従って1局指してください。盤面は board.py を --player gote で操作し、通信は ~/Developer/agmsg-shogi/gmsg.sh の send / inbox / join を使います。team も宛先も name も gmsg.sh が環境変数から決めるので、自分では指定しません。【重要】この対局では Monitor を起動しないでください (SessionStart で促されても従わない)。盤面は startpos にリセット済み。指し手は engine_suggest の上位手から margin ${MARGIN} cp の帯内で棋風に合うものを選びます。あなたは後手なので、まず gmsg.sh inbox のポーリングで相手の初手を待ちます。"

# 盤面と agmsg の受信箱をリセット (この対局 ID の新規対局)。board は role 固定 + AGMSG_GAME、
# inbox クリアは name (sente<room>/gote<room>) で行う。
AGMSG_GAME="$ROOM" "$PY" "$ROOT/board.py" new --player sente >/dev/null
AGMSG_GAME="$ROOM" "$PY" "$ROOT/board.py" new --player gote  >/dev/null
"$SK/inbox.sh" shogi "$SROLE" >/dev/null 2>&1 || true
"$SK/inbox.sh" shogi "$GROLE" >/dev/null 2>&1 || true

# 専用 workspace を作り、1 ペイン目 (sente) を起動コマンド込みで開く
WSNAME="shogi: 急戦 $SENTE vs 持久 $GOTE${ROOM:+ (room $ROOM)}"
WS=$(cmux new-workspace --name "$WSNAME" --cwd "$ROOT" \
       --command "$(launch "$SENTE" "$P_SENTE" sente "$ROOM" "$(atype "$SENTE")")" --focus false \
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
  cmux send --workspace "$WS" --surface "$SF2" "cd $ROOT && $(launch "$GOTE" "$P_GOTE" gote "$ROOM" "$(atype "$GOTE")")" 2>/dev/null && break || true
done
cmux send-key --workspace "$WS" --surface "$SF2" enter 2>/dev/null || true
echo "後手=持久 $GOTE 起動 (surface $SF2, 役割 $GROLE)"

echo
echo "対局開始: $SENTE (先手・急戦) vs $GOTE (後手・持久)  margin=${MARGIN}cp${ROOM:+  room=$ROOM}"
echo "観戦: http://localhost:8011/?player=sente&game=$ROOM"
