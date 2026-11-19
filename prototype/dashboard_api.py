"""Данные для живого дашборда (docs/dashboard-prototype.html): то, что страница получает по GET /api/dashboard.
Всё считается из базы тем же кодом, что и в Streamlit-интерфейсе (core.py): оценки, сигналы, разбор комментариев, статусы, действия HR.
Страница при открытии на сервере сама запрашивает этот адрес каждые 5 секунд; на GitHub Pages адреса нет, и она показывает встроенный пример."""
from __future__ import annotations

import math

import core

STATUS_NAMES = list(core.STATUSES)


def _num(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    v = float(v)
    return int(v) if v == int(v) else round(v, 1)


def build(con) -> dict:
    core.analyze_pending(con)  # новые комментарии разбираются при обновлении экрана, как и в Streamlit
    df, people, analysis = core.load_answers(con), core.participants(con), core.load_analysis(con)
    ids = {int(r.intern_id): (r["name"], r.mentor_name) for _, r in people.iterrows()}
    mx = core.CFG["scale"][1]
    dims = {k: {"label": v, "max": mx} for k, v in core.DIMS.items()}

    plist = []
    for iid, (name, mentor) in sorted(ids.items()):
        rec = {"id": name, "mentor": mentor, "i": {}, "m": {}}
        for side, key in (("intern", "i"), ("mentor", "m")):
            sub = df[(df.source == side) & (df.intern_id == iid)]
            for d in core.SIDE_DIMS[side]:
                arr = [None] * core.N_PERIODS
                for _, r in sub.iterrows():
                    arr[int(r.period) - 1] = _num(r[d])
                rec[key][d] = arr
        plist.append(rec)

    comments = []
    for _, r in df[df["comment"].notna()].iterrows():
        a = analysis.get((r["source"], r["response_id"]), {})
        topics = [t for t in a.get("topics", ["other"]) if t != "other"]
        comments.append({"id": r["response_id"], "u": ids[int(r.intern_id)][0], "w": int(r.period) - 1, "side": "i" if r["source"] == "intern" else "m",
                         "text": r["comment"], "topic": topics[0] if topics else "other", "quote": a.get("evidence_quote"), "action": a.get("suggested_action")})

    signals = [{"key": s["key"], "type": s["type"], "u": s["intern"], "w": int(s["period"]) - 1, "dim": s.get("dim"), "pr": s["priority"],
                "title": s["title"], "why": s["why"]} for s in core.compute_signals(df, people, analysis)]
    signals.sort(key=lambda s: (-s["pr"], -s["w"]))

    statuses = {s["key"]: core.get_status(con, s["key"]) for s in signals}
    actions = {name: [{"owner": a["owner"], "due": a["due"], "note": a["note"]} for a in core.list_actions(con, iid)] for iid, (name, _) in ids.items()}
    last = con.execute("SELECT MAX(received_at) FROM responses_raw").fetchone()[0]
    return {"live": True, "waves": [x[:3] for x in core.PERIODS], "dims": dims,
            "items": [{"id": i["id"], "label": i["label"], "i": i["intern"], "m": i["mentor"]} for i in core.ITEMS],
            "people": plist, "comments": comments, "signals": signals, "info": list(core.SIGNAL_INFO.values()), "thr": core.get_thresholds(con),
            "statuses": statuses, "actions": actions, "updated": (last or "")[5:16].replace("T", " "), "sample": None}


def set_status(con, payload: dict) -> dict:
    key, status = str(payload.get("key", "")), payload.get("status")
    if status not in STATUS_NAMES or not key:
        return {"status": "rejected", "reason": "неизвестный статус или пустой ключ сигнала"}
    core.set_status(con, key, status)
    return {"status": "ok"}


def add_action(con, payload: dict) -> dict:
    name = str(payload.get("intern", ""))
    iid = next((int(r.intern_id) for _, r in core.participants(con).iterrows() if r["name"] == name), None)
    owner, due, note = (str(payload.get(k, "")).strip()[:500] for k in ("owner", "due", "note"))
    if iid is None or not (owner and due and note):
        return {"status": "rejected", "reason": "нужны стажёр, ответственный, срок и описание"}
    core.add_action(con, iid, owner, due, note)
    return {"status": "ok"}
