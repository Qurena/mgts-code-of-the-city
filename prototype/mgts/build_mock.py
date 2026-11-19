"""Собирает макет дашборда (dashboard-prototype.html) из настоящего расчёта прототипа на двух таблицах Excel.
Запуск из папки prototype:  python mgts/build_mock.py   (пишет site/dashboard-prototype.html и publish/docs/dashboard-prototype.html)
Перед запуском: python mgts/make_data.py и python import_data.py mgts/mapping.json --reset (с переменными окружения mgts, см. README)."""
import json, os, re, sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
os.environ.setdefault("SURVEY_CONFIG", str(HERE / "survey.json"))
os.environ.setdefault("PULSE_DB", str(HERE / "pulse.db"))
sys.path.insert(0, str(HERE.parent))
import core, pandas as pd  # noqa: E402

mp = json.loads((HERE / "mapping.json").read_text(encoding="utf-8"))
cfg = core.CFG
con = core.connect()
df, p, an = core.load_answers(con), core.participants(con), core.load_analysis(con)
ids = {int(r.intern_id): (r["name"], r.mentor_name) for _, r in p.iterrows()}

dims = {}
for src in mp["sources"]:
    side = "i" if src["side"] == "intern" else "m"
    for s in src["scores"]:
        dims[s["dimension"]] = {"label": cfg["dimensions"][s["dimension"]], "side": side, "max": (s.get("scale") or cfg["scale"])[1]}

raw = {}
for src in mp["sources"]:
    t = pd.read_excel(HERE / src["file"])
    pid = src["columns"]["person"]
    t["_p"] = pd.to_datetime(t[src["columns"]["timestamp"]]).dt.month - 5  # июнь = 1
    raw[src["side"]] = t

people = []
for iid, (name, mentor) in sorted(ids.items()):
    rec = {"id": name, "mentor": mentor, "i": {}, "m": {}}
    for src in mp["sources"]:
        side = "i" if src["side"] == "intern" else "m"
        t = raw[src["side"]]
        who = name if side == "i" else mentor
        sub = t[t[src["columns"]["person"]] == who]
        for s in src["scores"]:
            arr = [None] * len(cfg["periods"])
            for _, r in sub.iterrows():
                v = r[s["column"]]
                if pd.notna(v):
                    arr[int(r["_p"]) - 1] = int(v)
            rec[side][s["dimension"]] = arr
    people.append(rec)

comments = []
for _, r in df[df["comment"].notna()].iterrows():
    a = an.get((r["source"], r["response_id"]), {})
    topics = [t for t in a.get("topics", ["other"]) if t != "other"]
    comments.append({"id": r["response_id"], "u": ids[int(r.intern_id)][0], "w": int(r.period) - 1, "side": "i" if r["source"] == "intern" else "m",
                     "text": r["comment"], "topic": topics[0] if topics else "other", "quote": a.get("evidence_quote"), "action": a.get("suggested_action")})

sigs = core.compute_signals(df, p, an)
signals = [{"key": s["key"], "type": s["type"], "u": s["intern"], "w": int(s["period"]) - 1, "dim": s.get("dim"), "pr": s["priority"], "title": s["title"], "why": s["why"]} for s in sigs]
signals.sort(key=lambda s: (-s["pr"], -s["w"]))

def sample(side, n=6):
    t = raw[side].drop(columns=["_p"]).head(n)
    return {"head": list(t.columns), "rows": [[None if pd.isna(v) else str(v)[:10] if k == "Дата ответа" else (int(v) if isinstance(v, float) and v == int(v) else v) for k, v in r.items()] for _, r in t.iterrows()]}

DATA = {"waves": [x[:3] for x in cfg["periods"]], "dims": dims, "items": [{"id": i["id"], "label": i["label"], "i": i["intern"], "m": i["mentor"]} for i in core.ITEMS],
        "people": people, "comments": comments, "signals": signals, "info": list(core.SIGNAL_INFO.values()),
        "thr": core.get_thresholds(con), "sample": {"i": sample("intern"), "m": sample("mentor")}}
html = (HERE / "mock_head.html").read_text(encoding="utf-8") + "\n<script>\nconst DATA=" + json.dumps(DATA, ensure_ascii=False, default=str) + ";\n" + (HERE / "mock_script.js").read_text(encoding="utf-8") + "</script>\n"
WRAP = '<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><style>html{-webkit-text-size-adjust:100%}body{margin:0}[hidden]{display:none!important}img{max-width:100%}</style>'
for out, pre in [(ROOT / "site/dashboard-prototype.html", ""), (ROOT / "publish/docs/dashboard-prototype.html", WRAP)]:
    out.write_text(pre + html, encoding="utf-8", newline="")
    print("записано", out, len(html))
json.dump(DATA, open(HERE / "site_data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
