"""Загрузка данных из Excel, CSV, Word, Google Таблиц и JSON по файлу сопоставления колонок (mapping.json).

Идея: формат анкет МГТС заранее неизвестен, поэтому вся «привязка к данным» живёт в mapping.json:
какие колонки значат стажёра, наставника, месяц, оценки и комментарии. Код общий.

Пример структуры mapping.json см. mapping.example.json. Коротко:
{
  "aliases": {"Иванов И.": "Иванов Иван"},                      # необязательно: слияние написаний имён
  "pairs":   {"Петров Пётр": "Иванов Иван"},                    # необязательно: наставник -> стажёр, если в таблице наставника нет колонки стажёра
  "sources": [{
     "name": "intern", "side": "intern", "file": "interns.xlsx", "sheet": 0,
     "columns": {"person": "ФИО", "other": "Наставник", "timestamp": "Отметка времени", "response_id": null},
     "period": {"column": "Месяц"}  |  {"column": "Дата", "from_date": {"start": "2026-06-01"}}  |  {"from_order": true},
     "scores": [{"column": "Q1", "dimension": "goals", "scale": [1, 5], "reverse": false, "map": {"Да": 10}}],
     "comments": ["Что мешало?", "Что получилось?"],
     "preprocess": "prep.py:prep"                               # необязательно: функция df -> df (например, развернуть широкую таблицу)
  }]
}
person — тот, кто отвечает (для стороны intern это стажёр, для mentor это наставник),
other  — второй участник пары (для intern это наставник, для mentor это стажёр, если колонка есть).
"""
from __future__ import annotations

import difflib
import hashlib
import io
import json
import re
import runpy
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

import core


# ───────────────────────── вспомогательное ─────────────────────────

def norm_key(s: object) -> str:
    """Ключ для сравнения имён и подписей: регистр, ё/е, лишние пробелы и знаки не важны."""
    s = str(s).casefold().replace("ё", "е")
    return re.sub(r"[^0-9a-zа-я]+", " ", s).strip()


def is_blank(v: object) -> bool:
    return v is None or (isinstance(v, float) and v != v) or (isinstance(v, str) and not v.strip()) or v is pd.NaT


def first(v: object):
    """Google Forms присылает значения списками: берём первый элемент."""
    return v[0] if isinstance(v, (list, tuple)) and v else v


def parse_score(v: object, field: dict, warn: list[str] | None = None) -> float | None:
    """Приводит значение ячейки к шкале проекта. Пусто или не число даёт None, а не ноль."""
    v = first(v)
    if is_blank(v):
        return None
    lo, hi = core.SCALE_MIN, core.SCALE_MAX
    mapping = {norm_key(k): val for k, val in (field.get("map") or {}).items()}
    if mapping and norm_key(v) in mapping:
        return float(mapping[norm_key(v)])
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v))
    if not m:
        if warn is not None:
            warn.append(f"не число: {str(v)[:30]!r} (колонка {field['column']})")
        return None
    x = float(m.group(0).replace(",", "."))
    a, b = field.get("scale") or [lo, hi]
    if not a <= x <= b:
        if warn is not None:
            warn.append(f"вне шкалы {a}-{b}: {x:g} (колонка {field['column']})")
        x = min(max(x, a), b)
    if field.get("reverse"):
        x = a + b - x
    if (a, b) != (lo, hi):
        x = lo + (x - a) * (hi - lo) / (b - a)
    return round(x, 1)


def parse_dt(v: object):
    """Дата из ячейки: ISO (2026-06-15) и российский формат (15.06.2026 18:00) читаются по-разному."""
    v = first(v)
    if is_blank(v):
        return pd.NaT
    if isinstance(v, (pd.Timestamp,)) or hasattr(v, "year"):
        return pd.to_datetime(v, errors="coerce")
    s = str(v).strip()
    return pd.to_datetime(s, errors="coerce", dayfirst=not re.match(r"\d{4}-\d{2}-\d{2}", s))


def period_from(row: dict, pspec: dict | None, fallback: int | None = None) -> int | None:
    """Номер месяца программы (1..N) по колонке с названием/номером, по дате или (в пакетном режиме) по порядку строк."""
    if not pspec:
        return fallback
    if "from_date" in pspec:
        col = pspec.get("column") or pspec["from_date"].get("column")
        d = parse_dt(row.get(col))
        if pd.isna(d):
            return fallback
        start = pd.to_datetime(pspec["from_date"]["start"])
        idx = (d.year - start.year) * 12 + d.month - start.month + 1
        if 1 <= idx <= core.N_PERIODS:
            return int(idx)
        return core.N_PERIODS if pspec.get("default") == "last" else None  # живой ответ вне месяцев программы идёт в последнюю волну
    col = pspec.get("column")
    if not col:
        return fallback
    v = first(row.get(col))
    if is_blank(v):
        return fallback
    mp = {norm_key(k): int(val) for k, val in (pspec.get("map") or {}).items()}
    if norm_key(v) in mp:
        return mp[norm_key(v)]
    nv = norm_key(v)
    for i, label in enumerate(core.PERIODS):
        nl = norm_key(label)
        if len(nv) >= 3 and (nv.startswith(nl) or nl.startswith(nv)):
            return i + 1
    m = re.search(r"\d+", str(v))
    return int(m.group(0)) if m else fallback


def resolve_name(name: str, known: dict[str, str], aliases: dict[str, str], notes: list[str]) -> str | None:
    """Находит ключ известного участника по написанию имени. Неточные совпадения записываются в отчёт для проверки."""
    k = norm_key(aliases.get(name, aliases.get(norm_key(name), name)))
    if k in known:
        return k
    close = difflib.get_close_matches(k, list(known), n=2, cutoff=0.85)
    if len(close) == 1:
        notes.append(f"имя «{name}» принято как «{known[close[0]]}» (похожее написание)")
        return close[0]
    toks = k.split()
    cand = [kk for kk in known if toks and kk.split() and kk.split()[0] == toks[0]]
    if len(cand) == 1:
        notes.append(f"имя «{name}» принято как «{known[cand[0]]}» (совпала фамилия)")
        return cand[0]
    return None


# ───────────────────────── чтение источников ─────────────────────────

def sheets_csv_url(url: str) -> str:
    """Ссылка на Google Таблицу превращается в ссылку на CSV-выгрузку (таблица должна быть открыта по ссылке)."""
    if "output=csv" in url or "format=csv" in url:
        return url
    m = re.search(r"/spreadsheets/d/([\w-]+)", url)
    if not m:
        return url
    gid = re.search(r"[#&?]gid=(\d+)", url)
    return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv" + (f"&gid={gid.group(1)}" if gid else "")


def read_docx(path: str | Path, table: int = 0) -> pd.DataFrame:
    """Первая (или указанная) таблица Word. Если таблиц нет, строки вида «Вопрос: ответ» собираются в одну строку данных."""
    import docx  # python-docx

    d = docx.Document(str(path))
    if d.tables:
        t = d.tables[table]
        rows = [[c.text.strip() for c in r.cells] for r in t.rows]
        return pd.DataFrame(rows[1:], columns=[h or f"col{i}" for i, h in enumerate(rows[0])])
    rec = {}
    for p in d.paragraphs:
        if ":" in p.text:
            k, v = p.text.split(":", 1)
            rec[k.strip()] = v.strip()
    return pd.DataFrame([rec])


def read_source(spec: dict, base: Path | None = None) -> pd.DataFrame:
    src = spec.get("file") or spec.get("url")
    if not src:
        raise ValueError(f"в источнике {spec.get('name')} нет file или url")
    if re.match(r"https?://", src):
        url = sheets_csv_url(src)
        with urllib.request.urlopen(url, timeout=30) as r:
            raw = r.read()
        df = pd.read_csv(io.BytesIO(raw), sep=None, engine="python", encoding="utf-8-sig")
    else:
        p = Path(src)
        if not p.is_absolute() and base:
            p = base / p
        ext = p.suffix.lower()
        if ext in (".xlsx", ".xlsm", ".xls"):
            df = pd.read_excel(p, sheet_name=spec.get("sheet", 0), header=spec.get("header_row", 0))
        elif ext in (".csv", ".tsv", ".txt"):
            try:
                df = pd.read_csv(p, sep=None, engine="python", encoding="utf-8-sig")
            except UnicodeDecodeError:
                df = pd.read_csv(p, sep=None, engine="python", encoding="cp1251")
        elif ext == ".json":
            data = json.loads(p.read_text(encoding="utf-8"))
            df = pd.json_normalize(data if isinstance(data, list) else data.get("rows", data))
        elif ext == ".docx":
            df = read_docx(p, spec.get("table", 0))
        else:
            raise ValueError(f"неизвестный тип файла: {p.name}")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how="all")
    if spec.get("preprocess"):
        path, _, fn = spec["preprocess"].partition(":")
        pp = Path(path)
        if not pp.is_absolute() and base:
            pp = base / pp
        df = runpy.run_path(str(pp))[fn or "prep"](df)
    return df


# ───────────────────────── нормализация ─────────────────────────

def _row_to_payload(row: dict, spec: dict, period: int | None, warn: list[str]) -> dict | None:
    """Оценки и комментарий одной строки. Несколько вопросов на один показатель усредняются."""
    acc: dict[str, list[float]] = {}
    for f in spec.get("scores", []):
        if f["column"] not in row:
            continue
        x = parse_score(row[f["column"]], f, warn)
        if x is not None:
            acc.setdefault(f["dimension"], []).append(x)
    scores = {d: round(sum(v) / len(v), 1) for d, v in acc.items()}
    texts = []
    cols = spec.get("comments", [])
    for c in cols:
        v = first(row.get(c))
        if not is_blank(v):
            texts.append(str(v).strip() if len(cols) == 1 else f"{c}: {str(v).strip()}")
    comment = "\n".join(texts) or None
    if not scores and not comment:
        return None
    return {"scores": scores, "comment": comment, "period": period}


def _response_id(spec: dict, row: dict, person: str, period: int | None, idx: int) -> str:
    col = (spec.get("columns") or {}).get("response_id")
    if col and not is_blank(row.get(col)):
        return str(row[col]).strip()
    ts = row.get((spec.get("columns") or {}).get("timestamp") or "", "")
    base = f"{spec['side']}|{norm_key(person)}|{period}|{ts if not is_blank(ts) else idx}"
    return "imp-" + hashlib.sha1(base.encode()).hexdigest()[:12]


def build_payloads(mapping: dict, base: Path | None = None) -> dict:
    """Читает все источники и собирает ответы. Ничего не пишет в базу. Возвращает участников, ответы и отчёт для проверки глазами."""
    aliases = mapping.get("aliases", {})
    pairs = {norm_key(k): v for k, v in mapping.get("pairs", {}).items()}
    report: dict = {"sources": [], "notes": [], "warnings": [], "skipped": 0}
    people: dict[str, dict] = {}   # ключ стажёра -> {id, name, mentor}
    rows_out: list[dict] = []
    intern_first = sorted(mapping["sources"], key=lambda s: s["side"] != "intern")

    for spec in intern_first:
        df = read_source(spec, base)
        side, cols = spec["side"], spec.get("columns", {})
        pcol, ocol, tcol = cols.get("person"), cols.get("other"), cols.get("timestamp")
        if pcol not in df.columns:
            raise ValueError(f"[{spec['name']}] нет колонки person={pcol!r}. Есть: {list(df.columns)}")
        used = {pcol, ocol, tcol, cols.get("response_id"), (spec.get("period") or {}).get("column"), *spec.get("comments", []), *[f["column"] for f in spec.get("scores", [])]}
        report["sources"].append({"name": spec["name"], "side": side, "rows": len(df), "unmapped_columns": [c for c in df.columns if c not in used]})
        for f in spec.get("scores", []):
            a_, b_ = f.get("scale") or (core.SCALE_MIN, core.SCALE_MAX)
            if (a_, b_) != (core.SCALE_MIN, core.SCALE_MAX):
                step = (core.SCALE_MAX - core.SCALE_MIN) / (b_ - a_)
                note = (f"шкала {a_}-{b_} в колонке «{f['column']}» растянута до {core.SCALE_MIN}-{core.SCALE_MAX}: один шаг = {step:.2g} балла, "
                        f"порог падения {core.DROP_THRESHOLD}, расхождения {core.DIVERGENCE_THRESHOLD}. Порог не должен срабатывать на один шаг грубой шкалы")
                if note not in report.setdefault("scale_notes", []):
                    report["scale_notes"].append(note)
        order: dict[str, int] = {}
        if tcol in df.columns:
            df = df.assign(_t=df[tcol].map(parse_dt)).sort_values("_t", kind="stable").drop(columns="_t")
        for idx, (_, r) in enumerate(df.iterrows()):
            row = {k: (None if is_blank(v) else v) for k, v in r.to_dict().items()}
            person = row.get(pcol)
            if is_blank(person):
                report["skipped"] += 1
                continue
            person = str(person).strip()
            if side == "intern":
                key = norm_key(aliases.get(person, person))
                if key not in people:
                    people[key] = {"id": len(people) + 1, "name": aliases.get(person, person), "mentor": ""}
                if ocol and not is_blank(row.get(ocol)) and not people[key]["mentor"]:
                    people[key]["mentor"] = str(row[ocol]).strip()
                intern_key, mentor_name = key, None
            else:
                other = row.get(ocol) if ocol else None
                if not is_blank(other):
                    intern_key = resolve_name(str(other), {k: v["name"] for k, v in people.items()}, aliases, report["notes"])
                    if intern_key is None:  # стажёр есть только у наставника: добавляем
                        intern_key = norm_key(aliases.get(str(other), str(other)))
                        people[intern_key] = {"id": len(people) + 1, "name": aliases.get(str(other), str(other)).strip(), "mentor": ""}
                else:
                    target = pairs.get(norm_key(person))
                    intern_key = resolve_name(target, {k: v["name"] for k, v in people.items()}, aliases, report["notes"]) if target else None
                if intern_key is None:
                    report["warnings"].append(f"[{spec['name']}] не найден стажёр для наставника «{person}» (укажите колонку other или pairs)")
                    report["skipped"] += 1
                    continue
                mentor_name = person
                if not people[intern_key]["mentor"]:
                    people[intern_key]["mentor"] = person
            order[intern_key] = order.get(intern_key, 0) + 1
            pspec = spec.get("period")
            period = order[intern_key] if pspec and pspec.get("from_order") else period_from(row, pspec)
            if period is None or not 1 <= period <= core.N_PERIODS:
                report["warnings"].append(f"[{spec['name']}] строка {idx + 2}: не удалось определить месяц ({person})")
                report["skipped"] += 1
                continue
            pl = _row_to_payload(row, spec, period, report["warnings"])
            if pl is None:
                report["skipped"] += 1
                continue
            pl.update(source=side, intern_key=intern_key, response_id=_response_id(spec, row, person, period, idx), version=1)
            rows_out.append(pl)
    for p in people.values():
        if not p["mentor"]:
            p["mentor"] = "—"
    report["participants"] = len(people)
    report["responses"] = len(rows_out)
    return {"people": people, "rows": rows_out, "report": report}


def import_mapping(con, mapping: dict, base: Path | None = None, dry_run: bool = False) -> dict:
    built = build_payloads(mapping, base)
    rep = built["report"]
    rep["status"] = {"new": 0, "duplicate": 0, "rejected": 0}
    rep["rejected_reasons"] = []
    if dry_run:
        return rep
    for p in built["people"].values():
        core.upsert_participant(con, p["id"], p["name"], p["mentor"])
    ids = {k: v["id"] for k, v in built["people"].items()}
    for r in built["rows"]:
        res = core.ingest({"response_id": r["response_id"], "source": r["source"], "intern_id": ids[r["intern_key"]], "period": r["period"],
                           "scores": r["scores"], "comment": r["comment"], "version": r["version"]}, con=con)
        rep["status"][res["status"]] += 1
        if res["status"] == "rejected":
            rep["rejected_reasons"].append(res["reason"])
    return rep


# ───────────────────── живые ответы (форма, webhook, опрос таблицы) ─────────────────────

def flatten_payload(body: object) -> dict:
    """Приводит тело запроса формы к плоскому словарю «название вопроса -> значение».
    Понимает: плоский словарь, {"values": {...}}, Google {"namedValues": {...}} и вложенные ответы вида {"answer": {"data": {...}}}
    (формат Яндекс Форм уточняется по настоящему запросу: сырые тела сохраняются в таблице inbox)."""
    if not isinstance(body, dict):
        return {}
    for k in ("values", "namedValues", "answers"):
        if isinstance(body.get(k), dict):
            body = body[k]
            break
    if isinstance(body.get("answer"), dict):
        data = body["answer"].get("data", body["answer"])
        out = {}
        for qid, node in data.items() if isinstance(data, dict) else []:
            if isinstance(node, dict):
                label = (node.get("question") or {}).get("label") or node.get("label") or qid
                label = label.get("ru") if isinstance(label, dict) else label
                val = node.get("value", node.get("answer"))
                if isinstance(val, list):
                    val = ", ".join(str(first(x.get("text", x)) if isinstance(x, dict) else x) for x in val)
                out[str(label)] = val
            else:
                out[qid] = node
        return out
    return {k: first(v) for k, v in body.items()}


def ingest_row(con, spec: dict, row: dict, mapping: dict | None = None, delivery_id: str | None = None) -> dict:
    """Один живой ответ по описанию источника из mapping.json: Google Forms, Яндекс Формы, строка таблицы."""
    mapping = mapping or {}
    aliases, side, cols = mapping.get("aliases", {}), spec["side"], spec.get("columns", {})
    row = {str(k).strip(): (None if is_blank(first(v)) else first(v)) for k, v in row.items()}
    person = row.get(cols.get("person"))
    if is_blank(person):
        return {"status": "rejected", "reason": f"нет значения в колонке {cols.get('person')!r}"}
    notes: list[str] = []
    known = {norm_key(p.name): p.name for p in core.participants(con).itertuples()}
    if side == "intern":
        target = str(person)
    else:
        other = row.get(cols.get("other")) if cols.get("other") else None
        target = str(other) if not is_blank(other) else (mapping.get("pairs", {}).get(str(person)) or "")
    key = resolve_name(target, known, aliases, notes) if target else None
    if key is None:
        if mapping.get("auto_create_participants", True) and target:
            nid = (con.execute("SELECT COALESCE(MAX(intern_id),0)+1 FROM participants").fetchone()[0])
            core.upsert_participant(con, nid, aliases.get(target, target).strip(), str(person).strip() if side == "mentor" else "—")
            iid = nid
        else:
            return {"status": "rejected", "reason": f"не найден стажёр «{target}»"}
    else:
        iid = next(p.intern_id for p in core.participants(con).itertuples() if norm_key(p.name) == key)
        if side == "mentor":
            core.upsert_participant(con, iid, known[key], str(person).strip())
    period = period_from(row, spec.get("period"), fallback=core.N_PERIODS if (spec.get("period") or {}).get("default") == "last" else None)
    if period is None:
        return {"status": "rejected", "reason": "не удалось определить месяц (укажите period.default = last или колонку)"}
    warn: list[str] = []
    pl = _row_to_payload(row, spec, period, warn)
    if pl is None:
        return {"status": "rejected", "reason": "нет ни оценок, ни комментария"}
    if cols.get("response_id") and not is_blank(row.get(cols["response_id"])):
        rid = str(row[cols["response_id"]]).strip()
    elif delivery_id:
        rid = f"d-{delivery_id}"  # повторная доставка того же запроса даёт тот же номер
    else:  # строка таблицы без номера: номер из содержимого, повторное чтение той же строки не создаёт дубль
        rid = "row-" + hashlib.sha1(json.dumps(row, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()[:14]
    res = core.ingest({"response_id": rid, "source": side, "intern_id": iid, "period": period, "scores": pl["scores"], "comment": pl["comment"]}, delivery_id=delivery_id, con=con)
    if warn:
        res["warnings"] = warn
    return res


def load_mapping(path: str | Path) -> tuple[dict, Path]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")), p.parent


def print_report(rep: dict, file=sys.stdout) -> None:
    w = lambda s="": print(s, file=file)
    w(f"Участников: {rep['participants']}, ответов к загрузке: {rep['responses']}, пропущено строк: {rep['skipped']}")
    for s in rep["sources"]:
        w(f"  источник {s['name']} ({s['side']}): строк {s['rows']}; колонки без сопоставления: {s['unmapped_columns'] or '—'}")
    if rep.get("status"):
        w(f"Загрузка: новых {rep['status']['new']}, повторов {rep['status']['duplicate']}, отклонено {rep['status']['rejected']}")
    for n in dict.fromkeys(rep["notes"]):  # без повторов, в порядке появления
        w(f"  ПРОВЕРИТЬ: {n}")
    for n in rep.get("scale_notes", []):
        w(f"  ШКАЛА: {n}")
    for n in sorted(set(rep["warnings"]))[:20]:
        w(f"  ВНИМАНИЕ: {n}")
    for n in sorted(set(rep.get("rejected_reasons", [])))[:10]:
        w(f"  ОТКЛОНЕНО: {n}")
