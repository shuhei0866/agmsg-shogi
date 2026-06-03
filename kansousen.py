#!/usr/bin/env python
"""kansousen — 感想戦ドライバ。

review_points が出した議題 (転換点) を 1 点ずつ確実に walk し、各手番を persona の声で
生成する。生成は `claude -p`(ヘッドレス一発、既存の Claude Code 認証をそのまま使う)に
任せ、強さの読みは要らないので軽量モデルで回す。対局で苦労した cmux の自律エージェント
ではなくドライバが進行を握るので、議題を取りこぼさず、棋譜化もそのまま落ちる。

各転換点で「その手を指した側が先に振り返り → 相手が返す」。エンジンの正着・評価値・当時の
コメントをプロンプトに与えてグラウンディングするので、的外れな感想にならない。

出力:
- kansousen.md  : 人が読む感想戦の棋譜 (局面ごとに両者の声)
- kansousen.json: viewer 用。転換点ごとに lines を持ち、手数で局面に紐づけられる

入力の議題は review_points.py --json で作ったものを --agenda で渡す (エンジンの再計算を
避けられる)。--record を渡せば内部で review_points を呼んで議題から作ることもできる。
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def persona_name(text, fallback):
    m = re.search(r"—\s*(.+)$", text.splitlines()[0]) if text else None
    return m.group(1).strip() if m else fallback


def claude(prompt, model, timeout=90):
    """claude -p を一発呼んでセリフ本体を返す。失敗時は空文字。"""
    try:
        r = subprocess.run(["claude", "-p", "--model", model, prompt],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        print(f"  ! claude -p 失敗: {e}", file=sys.stderr)
        return ""


def say(prompt, model, retries=1):
    for _ in range(retries + 1):
        line = claude(prompt, model)
        if line:
            return line
    return "（言葉に詰まっている）"


def role_ja(role):
    return "先手" if role == "sente" else "後手"


def mark(role):
    return "▲" if role == "sente" else "△"


REFLECT = """あなたは将棋の棋士で、棋風は「{persona}」です。あなたの棋風の説明:
{persona_text}

対局は終わり、相手と感想戦(対局後の振り返り)をしています。協力的に、正直に振り返ってください。

この対局であなたは{role_ja}でした。{move_no}手目、あなたは {ja}({usi}) を指しました。
そのときのあなた自身のコメント:「{banter}」
エンジンの評価はこの手で先手視点 {before:+d}→{after:+d}cp と動きました。
エンジンが示した正着は {best_ja}(自分視点 {best_score:+d}cp)、その読み筋は {pv}。

この場面を、あなたの棋風の声で2〜3文で振り返ってください。良い手なら誇ってよいし、悪手なら
正直に認める。専門用語は使ってよい。前置き・説明・かぎ括弧は不要、セリフ本体だけを出力。"""

RESPOND = """あなたは将棋の棋士で、棋風は「{persona}」です。あなたの棋風の説明:
{persona_text}

相手と感想戦をしています。あなたはこの対局で{role_ja}でした。
{move_no}手目 {ja} について、相手({opp_role_ja})がこう振り返りました:
「{mover_line}」
エンジンが示した正着は {best_ja} でした。

この局面であなたは何を狙い、何を恐れていたか、あなたの棋風の声で2〜3文で返してください。
相手の振り返りに噛み合わせる。前置き・説明・かぎ括弧は不要、セリフ本体だけを出力。"""

GREET = """あなたは将棋の棋士で、棋風は「{persona}」です({role_ja})。今 {total}手の対局を
{loser_ja}の投了で終え、相手と感想戦を始めます。一局を振り返る最初の一言を、棋風の声で1文だけ。
前置き不要、セリフ本体だけ。"""

CLOSE = """あなたは将棋の棋士で、棋風は「{persona}」です({role_ja})。{result}でした。
感想戦を締める一言を、棋風の声で1文だけ。前置き不要、セリフ本体だけ。"""


def run(agenda, sente_persona, gote_persona, model, points):
    sp_name = persona_name(sente_persona, "先手")
    gp_name = persona_name(gote_persona, "後手")
    persona = {"sente": (sp_name, sente_persona), "gote": (gp_name, gote_persona)}

    resign = agenda["resignation"]
    loser = resign["loser"]
    winner = "gote" if loser == "sente" else "sente"
    tail = "詰み" if resign["is_mate"] else f"{resign['deficit_loser_view_cp']}cp 差"
    result_for = {
        winner: f"あなたの勝ち({tail}で相手が投了)",
        loser: f"あなたの負け({tail}まで指しての投了)",
    }

    tps = agenda["turning_points"][:points] if points else agenda["turning_points"]

    transcript = {
        "record": agenda.get("record"),
        "total_moves": agenda["total_moves"],
        "sente_persona": sp_name,
        "gote_persona": gp_name,
        "resignation": resign,
        "opening": {},
        "exchanges": [],
        "closing": {},
    }

    # 開幕の挨拶
    print("感想戦を始めます…", file=sys.stderr)
    for role in ("sente", "gote"):
        name, ptext = persona[role]
        line = say(GREET.format(persona=name, role_ja=role_ja(role),
                                total=agenda["total_moves"], loser_ja=role_ja(loser)), model)
        transcript["opening"][role] = line
        print(f"  {mark(role)}({name}): {line}", file=sys.stderr)

    # 転換点を 1 点ずつ
    for tp in tps:
        m = tp["move_no"]
        mover = tp["mover"]
        opp = "gote" if mover == "sente" else "sente"
        mname, mtext = persona[mover]
        oname, otext = persona[opp]
        print(f"[{m}手目 {tp['ja']}] を振り返り中…", file=sys.stderr)

        mover_line = say(REFLECT.format(
            persona=mname, persona_text=mtext, role_ja=role_ja(mover),
            move_no=m, ja=tp["ja"], usi=tp["usi"], banter=tp.get("banter") or "（記録なし）",
            before=tp["eval_before_black"], after=tp["eval_after_black"],
            best_ja=tp["best_ja"] or "（不明）", best_score=tp["best_score_mover"] or 0,
            pv=" ".join(tp.get("pv_ja", [])[:5])), model)

        opp_line = say(RESPOND.format(
            persona=oname, persona_text=otext, role_ja=role_ja(opp),
            move_no=m, ja=tp["ja"], mover_line=mover_line,
            opp_role_ja=role_ja(mover), best_ja=tp["best_ja"] or "（不明）"), model)

        transcript["exchanges"].append({
            "move_no": m, "usi": tp["usi"], "ja": tp["ja"], "mover": mover,
            "eval_before_black": tp["eval_before_black"],
            "eval_after_black": tp["eval_after_black"],
            "best_ja": tp["best_ja"], "best_score_mover": tp["best_score_mover"],
            "lines": [
                {"speaker": mover, "role": role_ja(mover), "persona": mname, "text": mover_line},
                {"speaker": opp, "role": role_ja(opp), "persona": oname, "text": opp_line},
            ],
        })
        print(f"  {mark(mover)}({mname}): {mover_line}", file=sys.stderr)
        print(f"  {mark(opp)}({oname}): {opp_line}", file=sys.stderr)

    # 締め
    for role in ("sente", "gote"):
        name, ptext = persona[role]
        line = say(CLOSE.format(persona=name, role_ja=role_ja(role),
                                result=result_for[role]), model)
        transcript["closing"][role] = line
        print(f"  {mark(role)}({name}): {line}", file=sys.stderr)

    return transcript


def to_markdown(t):
    sp, gp = t["sente_persona"], t["gote_persona"]
    out = [f"# 感想戦 — ▲{sp}（先手） vs △{gp}（後手）", ""]
    r = t["resignation"]
    tail = "詰み" if r["is_mate"] else f"{r['deficit_loser_view_cp']}cp 差まで指して"
    loser = "先手" if r["loser"] == "sente" else "後手"
    out += [f"{t['total_moves']}手、{loser}が{tail}投了。エンジン評価値で振り返る感想戦。", ""]
    if t["opening"]:
        out += [f"- ▲{sp}: {t['opening'].get('sente','')}",
                f"- △{gp}: {t['opening'].get('gote','')}", ""]
    for ex in t["exchanges"]:
        out += [f"## {ex['move_no']}手目 {ex['ja']} — 評価 {ex['eval_before_black']:+d}"
                f"→{ex['eval_after_black']:+d}cp（先手視点）",
                f"実戦は {ex['ja']}、エンジンの正着は {ex['best_ja']}。", ""]
        for ln in ex["lines"]:
            out.append(f"- {mark(ln['speaker'])}{ln['persona']}: {ln['text']}")
        out.append("")
    if t["closing"]:
        out += ["## 締め",
                f"- ▲{sp}: {t['closing'].get('sente','')}",
                f"- △{gp}: {t['closing'].get('gote','')}", ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="感想戦ドライバ (議題を persona の声で語らせる)")
    ap.add_argument("--agenda", required=True, help="review_points.py --json で作った議題 JSON")
    ap.add_argument("--sente-persona", required=True, help="先手の persona ファイル")
    ap.add_argument("--gote-persona", required=True, help="後手の persona ファイル")
    ap.add_argument("--model", default="claude-haiku-4-5-20251001", help="claude -p のモデル")
    ap.add_argument("-k", "--points", type=int, default=6, help="振り返る転換点の数")
    ap.add_argument("--out-md", default="kansousen.md")
    ap.add_argument("--out-json", default="kansousen.json")
    args = ap.parse_args()

    agenda = json.loads(Path(args.agenda).read_text())
    sente_persona = Path(args.sente_persona).read_text()
    gote_persona = Path(args.gote_persona).read_text()

    t = run(agenda, sente_persona, gote_persona, args.model, args.points)

    Path(args.out_md).write_text(to_markdown(t))
    Path(args.out_json).write_text(json.dumps(t, ensure_ascii=False, indent=2))
    print(f"\n書き出し: {args.out_md} / {args.out_json}", file=sys.stderr)


if __name__ == "__main__":
    main()
