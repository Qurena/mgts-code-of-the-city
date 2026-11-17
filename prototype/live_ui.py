"""Панели интерфейса для живого показа: загрузка файла или ссылки, автоподтягивание источников, ручное заполнение ответа
в формате источника (колонки берутся из mapping.json, поэтому форма повторяет настоящую таблицу или анкету)."""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import streamlit as st

import core
import ingest_tools as it

RECEIVER_URL = os.environ.get("RECEIVER_URL", "http://127.0.0.1:8765")
INCOMING = Path(__file__).with_name("incoming")


def _summary(rep: dict) -> str:
    s = rep["status"]
    extra = f", предупреждений: {len(set(rep['warnings']))}" if rep.get("warnings") else ""
    return f"новых {s['new']}, повторов {s['duplicate']}, отклонено {s['rejected']}{extra}"


def sync_sources(con, mapping: dict, base: Path) -> None:
    """Перечитывает все источники из mapping.json (файлы и ссылки на таблицы). Повторы отсекаются, исправленные строки заменяют прежние ответы."""
    try:
        rep = it.import_mapping(con, mapping, base)
        st.session_state["sync_msg"] = (dt.datetime.now().strftime("%H:%M:%S"), _summary(rep), False)
    except Exception as e:  # файл занят, таблица недоступна, сеть пропала: показ продолжается на уже загруженных данных
        st.session_state["sync_msg"] = (dt.datetime.now().strftime("%H:%M:%S"), f"ошибка: {str(e)[:120]}", True)


def render_panels(con, mapping: dict, base: Path, people) -> None:
    sources = mapping.get("sources", [])
    if not sources:
        st.caption("Файла mapping.json нет: загрузка по формату источника недоступна.")
        return
    names = [s["name"] for s in sources]
    label = lambda n: f"{n} ({core.SIDE_NAME[next(s['side'] for s in sources if s['name'] == n)].lower()})"

    # 1. файл или ссылка
    with st.expander("Загрузить файл или ссылку"):
        src = st.selectbox("Источник", names, format_func=label, key="up_src")
        up = st.file_uploader("Файл: xlsx, csv, docx, json", type=["xlsx", "xls", "csv", "tsv", "docx", "json"], key="up_file")
        url = st.text_input("или ссылка на Google Таблицу", key="up_url", placeholder="https://docs.google.com/spreadsheets/d/…")
        if st.button("Загрузить", key="up_go", width="stretch") and (up or url):
            try:
                if up:
                    INCOMING.mkdir(exist_ok=True)
                    path = INCOMING / f"{src}_{dt.datetime.now():%H%M%S}_{Path(up.name).name}"
                    path.write_bytes(up.getvalue())
                    rep = it.import_one(con, mapping, src, file_path=path, base=base)
                else:
                    rep = it.import_one(con, mapping, src, url=url.strip(), base=base)
                st.session_state["load_msg"] = ("success", f"Загружено: {_summary(rep)}")
            except Exception as e:
                st.session_state["load_msg"] = ("error", f"Не удалось загрузить: {str(e)[:200]}")
            st.rerun()
        if "load_msg" in st.session_state:
            kind, msg = st.session_state.pop("load_msg")
            getattr(st, kind)(msg)

    # 2. автоподтягивание
    with st.expander("Подтягивать источники сами"):
        st.caption("Каждые 5 секунд перечитывает файлы и ссылки из mapping.json. Новая строка в таблице появляется на дашборде без кнопок.")
        for s in sources:
            st.caption(f"• {s['name']}: {s.get('url') or s.get('file')}")
        st.toggle("Подтягивать каждые 5 с", key="autosync")
        if st.button("Подтянуть сейчас", key="sync_now", width="stretch"):
            sync_sources(con, mapping, base)
            st.rerun()
        if "sync_msg" in st.session_state:
            t, m, bad = st.session_state["sync_msg"]
            (st.error if bad else st.caption)(f"{t}: {m}")

    # 3. ручное заполнение в формате источника
    with st.expander("Заполнить ответ вручную"):
        st.caption("Поля повторяют колонки источника. Ответ проходит тот же путь, что и строка из таблицы или формы.")
        src = st.selectbox("Источник", names, format_func=label, key="lv_src")
        spec = next(s for s in sources if s["name"] == src)
        cols = spec.get("columns", {})
        row: dict = {}
        interns = list(people.name)
        mentors = sorted({m for m in people.mentor_name if m and m != "—"})
        mine, theirs = (interns, mentors) if spec["side"] == "intern" else (mentors, interns)

        def pick(title: str, options: list[str], key: str):
            return st.selectbox(title, options, key=key) if options else st.text_input(title, key=key)

        if cols.get("person"):
            row[cols["person"]] = pick(cols["person"], mine, f"lv_p_{src}")
        if cols.get("other"):
            row[cols["other"]] = pick(cols["other"], theirs, f"lv_o_{src}")
        p = spec.get("period") or {}
        if p.get("column") and "from_date" not in p:
            row[p["column"]] = st.selectbox(p["column"], core.PERIODS, index=core.N_PERIODS - 1, key=f"lv_m_{src}")
        seen = set()
        for f in spec.get("scores", []):
            if f["column"] in seen:
                continue
            seen.add(f["column"])
            if f.get("map"):
                row[f["column"]] = st.selectbox(f["column"], list(f["map"]), key=f"lv_s_{src}_{f['column']}")
            else:
                a, b = f.get("scale") or (core.SCALE_MIN, core.SCALE_MAX)
                a, b = int(a), int(b)
                row[f["column"]] = st.slider(f["column"], a, b, min((a + b) // 2 + 1, b), key=f"lv_s_{src}_{f['column']}")
        for c in spec.get("comments", []):
            row[c] = st.text_area(c, key=f"lv_c_{src}_{c}")
        via_http = st.checkbox("Отправить через приёмник (HTTP)", value=True, key="lv_http", help="Так делала бы настоящая форма. Если приёмник не запущен, ответ принимается напрямую")
        if st.button("Отправить ответ", type="primary", key="lv_go", width="stretch"):
            if cols.get("timestamp"):
                row[cols["timestamp"]] = dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            delivery = f"ui-{uuid.uuid4().hex[:12]}"
            row = {k: (v if v != "" else None) for k, v in row.items()}
            msg = None
            if via_http:
                try:
                    req = urllib.request.Request(f"{RECEIVER_URL}/form/{src}", data=json.dumps({"values": row}, ensure_ascii=False).encode(),
                                                 headers={"Content-Type": "application/json", "x-delivery-id": delivery,
                                                          **({"x-token": os.environ["WEBHOOK_TOKEN"]} if os.environ.get("WEBHOOK_TOKEN") else {})})
                    with urllib.request.urlopen(req, timeout=5) as r:
                        msg = ("success", f"Приёмник ответил: {json.load(r)['status']}")
                except urllib.error.HTTPError as e:
                    msg = ("error", "Приёмник отклонил ответ: " + json.load(e).get("reason", str(e)))
                except (urllib.error.URLError, OSError):
                    res = it.ingest_row(con, spec, row, mapping, delivery)
                    msg = ("warning", f"Приёмник не запущен, ответ принят напрямую ({res['status']}). Для живого показа запустите receiver.py.")
            else:
                res = it.ingest_row(con, spec, row, mapping, delivery)
                msg = ("success" if res["status"] != "rejected" else "error", f"Ответ принят: {res['status']}" + (f" ({res.get('reason')})" if res.get("reason") else ""))
            st.session_state["lv_msg"] = msg
            st.rerun()
        if "lv_msg" in st.session_state:
            kind, text = st.session_state.pop("lv_msg")
            getattr(st, kind)(text)
