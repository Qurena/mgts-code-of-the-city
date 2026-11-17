"""Интерфейс «Пульс стажёров»: обзор программы, очередь внимания, карточка стажёра.
Запуск: streamlit run app.py   (приёмник ответов: python receiver.py)
Данные в базе демонстрационные (seed.py). Формат анкет МГТС будет известен на финале."""
import datetime as dt
import json
import os
import urllib.error
import urllib.request

import altair as alt
import pandas as pd
import streamlit as st

import core
import seed

st.set_page_config(page_title="Пульс стажёров", page_icon="📈", layout="wide")
RECEIVER_URL = os.environ.get("RECEIVER_URL", "http://127.0.0.1:8765")
BLUE, GRAPHITE = "#5CC0FF", "#C9D2E3"  # стажёр: голубая сплошная линия, наставник: светлая пунктирная (тёмная тема)
SCREENS = ["Обзор программы", "Очередь внимания", "Карточка стажёра"]
BADGE = {"content": ("red", "Комментарий"), "change": ("orange", "Изменение"), "divergence": ("blue", "Расхождение"), "data": ("gray", "Нет данных")}

st.markdown("""<style>
.stApp{background-image:radial-gradient(900px 500px at 85% -10%,rgba(123,97,255,.20),transparent 60%),radial-gradient(800px 500px at 10% 0%,rgba(0,138,224,.22),transparent 60%);background-attachment:fixed}
.block-container{padding-top:2rem;max-width:1200px}
h1,h2,h3{letter-spacing:0}
/* стеклянные карточки, как на референсах */
[data-testid="stVerticalBlockBorderWrapper"]{background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.10);border-radius:22px;backdrop-filter:blur(14px)}
[data-testid="stMetric"]{background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.10);border-radius:22px;padding:18px 20px}
[data-testid="stColumn"]:first-child [data-testid="stMetric"]{background:linear-gradient(135deg,#008AE0,#7B61FF);border-color:transparent}
button[kind="primary"]{background:linear-gradient(135deg,#008AE0,#7B61FF);border:0}
[data-testid="stSidebar"]{background:rgba(255,255,255,.03);border-right:1px solid rgba(255,255,255,.08)}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def get_con():
    con = core.connect(shared=True)
    if con.execute("SELECT COUNT(*) FROM participants").fetchone()[0] == 0:
        seed.seed(con)
    return con


def snapshot(con):
    core.analyze_pending(con)  # разбор текста после приёма: приёмник отвечает сразу
    df, people = core.load_answers(con), core.participants(con)
    ana = core.load_analysis(con)
    return df, people, ana, core.compute_signals(df, people, ana)


con = get_con()
df, people, ana, sigs = snapshot(con)
by_id = people.set_index("intern_id")
open_sigs = [s for s in sigs if core.get_status(con, s["key"]) != "Закрыт"]

# ───────────────────────── боковая панель ─────────────────────────
st.session_state.setdefault("screen", SCREENS[0])
st.session_state.setdefault("intern", int(people.intern_id.iloc[0]))
with st.sidebar:
    st.title("Пульс стажёров")
    st.caption("Рабочее название. Данные выдуманы для демонстрации.")
    role = st.radio("Роль", ["HR", "Наставник"], horizontal=True)
    if role == "Наставник":
        mentor_intern = st.selectbox("Чей наставник", people.intern_id, format_func=lambda i: f"{by_id.loc[i, 'mentor_name']} (стажёр {by_id.loc[i, 'name']})")
    st.divider()
    if st.button("Обновить данные", width="stretch"):
        st.rerun()
    st.caption(f"Анализ комментариев: {os.environ.get('ANALYZER', 'keywords')}")

    if role == "HR":
        with st.expander("Имитация внешней формы"):
            st.caption("Отправляет ответ на приёмник (POST /response), как это сделала бы настоящая форма.")
            missing = [(int(i), s) for i in people.intern_id for s in core.SIDES if df[(df.source == s) & (df.intern_id == i) & (df.period == core.N_PERIODS)].empty]
            f_intern = st.selectbox("Стажёр", people.intern_id, index=list(people.intern_id).index(missing[0][0]) if missing else 0, format_func=lambda i: by_id.loc[i, "name"])
            f_side = st.radio("Кто отвечает", core.SIDES, format_func=core.SIDE_NAME.get, horizontal=True, index=core.SIDES.index(missing[0][1]) if missing else 0)
            f_period = st.selectbox("Месяц", range(1, core.N_PERIODS + 1), index=core.N_PERIODS - 1, format_func=lambda p: core.PERIODS[p - 1])
            f_scores = {k: st.slider(v, core.SCALE_MIN, core.SCALE_MAX, 7, key=f"sl_{k}") for k, v in core.DIMS.items()}
            f_comment = st.text_area("Комментарий", placeholder="Например: Нет доступа к нужной системе.")
            f_id = st.text_input("Номер ответа (response_id)", value=f"form-{dt.datetime.now():%H%M%S}")
            if st.button("Отправить ответ", type="primary", width="stretch"):
                payload = {"response_id": f_id, "source": f_side, "intern_id": int(f_intern), "period": int(f_period), "scores": f_scores, "comment": f_comment or None}
                try:
                    req = urllib.request.Request(RECEIVER_URL + "/response", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "x-delivery-id": f_id, **({"x-token": os.environ["WEBHOOK_TOKEN"]} if os.environ.get("WEBHOOK_TOKEN") else {})})
                    with urllib.request.urlopen(req, timeout=5) as r:
                        res = json.load(r)
                    st.session_state["form_msg"] = ("success", f"Приёмник ответил: {res['status']}")
                except urllib.error.HTTPError as e:
                    st.session_state["form_msg"] = ("error", "Приёмник отклонил ответ: " + json.load(e).get("reason", str(e)))
                except (urllib.error.URLError, OSError):
                    res = core.ingest(payload, con=con)
                    st.session_state["form_msg"] = ("warning", f"Приёмник не запущен, ответ принят напрямую ({res['status']}). Для живого показа запустите receiver.py.")
                st.rerun()  # после перезапуска сообщение показывается ниже: иначе оно исчезло бы сразу
            if "form_msg" in st.session_state:
                kind, msg = st.session_state.pop("form_msg")
                getattr(st, kind)(msg)


def go(screen, intern=None):
    st.session_state["screen"] = screen
    if intern is not None:
        st.session_state["intern"] = int(intern)


def line_chart(sub: pd.DataFrame, value: str, height=300):
    """Две стороны: стажёр сплошной синей линией, наставник пунктирной графитовой. Пропуск разрывает линию."""
    d = sub.copy()
    d["Сторона"] = d.source.map(core.SIDE_NAME)
    d["Месяц"] = d.period.map(lambda p: core.PERIODS[p - 1])
    base = alt.Chart(d).encode(
        x=alt.X("Месяц:N", sort=core.PERIODS, axis=alt.Axis(labelAngle=0, title=None)),
        y=alt.Y(f"{value}:Q", scale=alt.Scale(domain=[core.SCALE_MIN, core.SCALE_MAX]), axis=alt.Axis(title=None, tickMinStep=1)),
        color=alt.Color("Сторона:N", scale=alt.Scale(domain=["Стажёр", "Наставник"], range=[BLUE, GRAPHITE]), legend=alt.Legend(orient="top", title=None)),
        strokeDash=alt.StrokeDash("Сторона:N", scale=alt.Scale(domain=["Стажёр", "Наставник"], range=[[1, 0], [6, 4]]), legend=None),
        tooltip=["Сторона", "Месяц", alt.Tooltip(f"{value}:Q", title="Оценка")],
    )
    return (base.mark_line(strokeWidth=2.5, invalid=None) + base.mark_point(filled=True, size=70)).properties(height=height)


def render_card(iid: int, mentor_view: bool):
    p = by_id.loc[iid]
    st.subheader(p["name"])
    st.caption(f"Наставник: {p['mentor_name']} · {core.N_PERIODS} месяцев")
    c1, c2 = st.columns([3, 2], gap="large")
    mine = df[df.intern_id == iid]
    with c1:
        dim = st.selectbox("Вопрос", list(core.DIMS), format_func=core.DIMS.get, key=f"dim_card_{iid}")
        st.altair_chart(line_chart(mine, dim), width="stretch")
        rows = []
        for k, label in core.DIMS.items():
            row = {"Вопрос (стажёр / наставник)": label}
            for pn in range(1, core.N_PERIODS + 1):
                a = mine[(mine.source == "intern") & (mine.period == pn)][k]
                b = mine[(mine.source == "mentor") & (mine.period == pn)][k]
                fa = "нет" if a.empty or pd.isna(a.iloc[0]) else f"{a.iloc[0]:.0f}"
                fb = "нет" if b.empty or pd.isna(b.iloc[0]) else f"{b.iloc[0]:.0f}"
                row[core.PERIODS[pn - 1]] = f"{fa} / {fb}"
            rows.append(row)
        st.dataframe(pd.DataFrame(rows).set_index("Вопрос (стажёр / наставник)"), width="stretch")
    with c2:
        st.markdown("##### Сигналы")
        mine_sigs = [s for s in sigs if s["intern_id"] == iid]
        if not mine_sigs:
            st.write("Сигналов нет.")
        for s in mine_sigs:
            color, label = BADGE[s["type"]]
            with st.container(border=True):
                st.markdown(f":{color}-badge[{label}] **{s['title']}**")
                st.caption(s["why"])
        st.markdown("##### Комментарии")
        if mentor_view:
            st.info("Тексты стажёра скрыты политикой доступа. Показывать ли их наставнику, решает HR (открытый вопрос).")
        else:
            cm = mine[mine.comment.notna()].sort_values("period")
            if cm.empty:
                st.write("Комментариев нет.")
            for r in cm.itertuples():
                a = ana.get((r.source, r.response_id), {})
                text = r.comment
                if a.get("evidence_quote"):
                    text = text.replace(a["evidence_quote"], f":orange-background[{a['evidence_quote']}]")
                with st.container(border=True):
                    st.caption(f"{core.SIDE_NAME[r.source]} · {core.PERIODS[r.period - 1]}")
                    st.markdown(text)
                    tags = " ".join(f":gray-badge[Тема: {core.TOPICS[t]}]" for t in a.get("topics", []))
                    if a.get("validation_status") == "ok" and a.get("evidence_quote"):
                        tags += " :green-badge[цитата найдена в источнике]"
                    elif a.get("validation_status") == "manual":
                        tags += " :orange-badge[нужен ручной разбор]"
                    st.markdown(tags)
        if not mentor_view:
            st.markdown("##### Действие HR")
            for a in core.list_actions(con, iid):
                st.markdown(f"**{a['owner']}**, до {a['due']}: {a['note']}")
            with st.form(f"act_{iid}", clear_on_submit=True):
                owner = st.text_input("Ответственный")
                due = st.date_input("Срок", dt.date.today() + dt.timedelta(days=7))
                note = st.text_area("Что делаем и почему")
                if st.form_submit_button("Записать действие"):
                    if owner.strip() and note.strip():
                        core.add_action(con, iid, owner.strip(), due.isoformat(), note.strip())
                        st.rerun()
                    else:
                        st.warning("Заполните ответственного и описание действия.")


# ───────────────────────── экраны ─────────────────────────
if role == "Наставник":
    st.header("Мой стажёр")
    render_card(int(mentor_intern), mentor_view=True)
    st.stop()

screen = st.radio("Экран", SCREENS, horizontal=True, key="screen", label_visibility="collapsed",
                  format_func=lambda s: s if s != SCREENS[1] else f"{s} ({len(open_sigs)})")

if screen == SCREENS[0]:
    cov = core.coverage(df, people)
    c = st.columns(3)
    c[0].metric(f"Ответили в волне «{core.PERIODS[-1]}»", f"{cov['intern'] + cov['mentor']} из {cov['total'] * 2}")
    c[0].caption(f"стажёры {cov['intern']}/{cov['total']} · наставники {cov['mentor']}/{cov['total']}")
    c[1].metric("Требуют внимания", len(open_sigs))
    c[1].caption(f"{sum(s['type'] == 'content' for s in open_sigs)} комментариев · {sum(s['type'] in ('change', 'divergence') for s in open_sigs)} по динамике · {sum(s['type'] == 'data' for s in open_sigs)} по данным")
    last = df.received_at.max() if len(df) else None
    c[2].metric("Последний ответ получен", str(last)[5:16].replace("T", " ") if last else "нет данных")
    c[2].caption("время UTC, из формы или демо-набора")
    left, right = st.columns([3, 2], gap="large")
    with left:
        dim = st.selectbox("Вопрос", list(core.DIMS), format_func=core.DIMS.get, index=2)
        m = core.medians(df, dim)
        st.altair_chart(line_chart(m, "Медиана", 320), width="stretch")
        st.caption("Медиана по ответившим. В демо 5 человек, поэтому число ответов n показано ниже. Две линии, общего среднего нет. Медиана не показывает отдельные случаи, их находят сигналы.")
        piv = m.pivot(index="Сторона", columns="Месяц", values="n").reindex(columns=core.PERIODS).fillna(0).astype(int)
        st.dataframe(piv.rename_axis("n ответов"), width="stretch")
    with right:
        st.markdown("##### Темы в комментариях")
        cnt = pd.Series([t for a in ana.values() if a["validation_status"] == "ok" for t in a["topics"] if t != "other"]).value_counts() if ana else pd.Series(dtype=int)
        if cnt.empty:
            st.write("Тем пока нет.")
        else:
            cdf = pd.DataFrame({"Тема": [core.TOPICS[t] for t in cnt.index], "Комментариев": cnt.values})
            st.altair_chart(alt.Chart(cdf).mark_bar(color=BLUE).encode(y=alt.Y("Тема:N", sort="-x", title=None), x=alt.X("Комментариев:Q", axis=alt.Axis(tickMinStep=1, title=None))).properties(height=180), width="stretch")
        st.info("Тему и цитату определяет разборщик, цитату проверяет код. Единичные случаи не превращаем в процент недовольных.")

elif screen == SCREENS[1]:
    st.subheader("Очередь внимания")
    st.caption("Приоритет: серьёзность барьера, повтор, срок без реакции. Сигнал — повод проверить, а не вердикт о человеке.")
    if not sigs:
        st.write("Сигналов нет.")
    for s in sigs:
        color, label = BADGE[s["type"]]
        with st.container(border=True):
            a, b, c3 = st.columns([6, 2, 2], vertical_alignment="center")
            a.markdown(f":{color}-badge[{label}] **{s['intern']}** · {core.PERIODS[s['period'] - 1]}  \n{s['title']}")
            a.caption(s["why"])
            cur = core.get_status(con, s["key"])
            new = b.selectbox("Статус", core.STATUSES, index=core.STATUSES.index(cur), key="st_" + s["key"], label_visibility="collapsed")
            if new != cur:
                core.set_status(con, s["key"], new)
                st.rerun()
            c3.button("Карточка", key="op_" + s["key"], on_click=go, args=(SCREENS[2], s["intern_id"]), width="stretch")

else:
    c0, _ = st.columns([2, 5])
    pick = c0.selectbox("Стажёр", list(people.intern_id), index=list(people.intern_id).index(st.session_state["intern"]), format_func=lambda i: by_id.loc[i, "name"])
    st.session_state["intern"] = int(pick)
    render_card(int(pick), mentor_view=False)
