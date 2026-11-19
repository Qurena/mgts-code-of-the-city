"""Переводит лендинг на формат вебинара: раздел «Какие данные мы получаем», пример на парных вопросах разных шкал,
тепловая карта по оценкам наставника, пороги из survey.json. Запуск из папки prototype: python mgts/patch_site.py
Меняет site/index.html и publish/docs/index.html. Повторный запуск ничего не ломает (проверка по id раздела)."""
import json
import re
from html import escape as e
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
d = json.loads((Path(__file__).parent / "site_data.json").read_text(encoding="utf-8"))


def table(side, n=3):
    s = d["sample"][side]
    head = "".join(f"<th>{e(h)}</th>" for h in s["head"])
    rows = "".join("<tr>" + "".join(f"<td>{'' if v is None else e(str(v))}</td>" for v in r) + "</tr>" for r in s["rows"][:n])
    return f'<div class="dtw"><table class="dt"><tr>{head}</tr>{rows}</table></div>'


CSS = """/* данные */
.dtw{overflow-x:auto;margin:6px 0 14px}
table.dt{border-collapse:collapse;font-size:13px;min-width:100%}
table.dt th,table.dt td{border:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top}
table.dt th{background:var(--card-hi);font-family:var(--font-head);font-size:12px;color:var(--muted)}
.two{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:8px 0 14px}
.two h3{font:700 15px var(--font-head);margin:0 0 8px}
.two ul{margin:0;padding-left:18px;font-size:15px}.two li{margin:0 0 7px}
@media (max-width:960px){.two{grid-template-columns:minmax(0,1fr)}}
"""

SECTION = f"""<section id="data" class="card" aria-labelledby="dath">
      <h2 id="dath">Какие данные мы получаем<span class="tag">Со слов организаторов</span></h2>
      <p class="sub">Формат описали на вебинаре 13 ноября. Точные названия колонок и вопросов выдадут на финале. Ниже то, что известно, и то, как программа примет любой вариант.</p>
      <div class="two">
        <div><h3>Что известно</h3><ul>
          <li>Две таблицы Excel (упоминали и Word): ответы стажёров и ответы наставников за один период.</li>
          <li>5 стажёров, 5 наставников, 6 ежемесячных опросов. Один наставник на одного стажёра.</li>
          <li>Данные придуманные. У каждого стажёра и наставника свой уникальный ID, анкеты анонимные.</li>
          <li>Стажёра спрашивают, как проходит стажировка и интересны ли задачи. Наставника спрашивают, как стажёр справляется, насколько оперативно и самостоятельно.</li>
          <li>Вопросы не меняются между месяцами.</li>
          <li>Нужно повторить анкету в Google Формах или похожем сервисе, чтобы ответы попадали в сервис, и сделать место, куда загружаются новые данные.</li>
        </ul></div>
        <div><h3>Что узнаем только на финале</h3><ul>
          <li>Названия колонок и точные формулировки вопросов.</li>
          <li>Шкала оценок: 1–5, 1–10 или другая. Шкалы у сторон могут различаться.</li>
          <li>Есть ли колонка с парой «стажёр и наставник» или пару определяет ID.</li>
          <li>В каком виде указан месяц: дата, номер или название.</li>
          <li>Есть ли текстовые комментарии и у какой стороны.</li>
        </ul></div>
      </div>
      <h3 style="font:700 15px var(--font-head);margin:6px 0 0">Так выглядят две таблицы в нашем примере</h3>
      <p class="note" style="margin:4px 0 0">Таблица 1. Ответы стажёров (шкала 1–5)</p>{table("i")}
      <p class="note" style="margin:0">Таблица 2. Ответы наставников (шкала 1–10)</p>{table("m")}
      <ul class="points">
        <li><span class="dot"><svg viewBox="0 0 24 24"><path d="M4 8h16M4 16h16M9 4l-4 4 4 4M15 12l4 4-4 4"/></svg></span><div><b>Пара по ID</b><span>Если колонки с парой нет, наставник Н-03 сопоставляется стажёру С-03 по числу в ID. Такие пары программа выводит в отчёт на проверку.</span></div></li>
        <li><span class="dot"><svg viewBox="0 0 24 24"><path d="M3 20h18M6 16l4-5 3 3 5-8"/></svg></span><div><b>Одна шкала</b><span>Шкалы 1–5 и 1–10 приводятся к 1–10. Исходные значения остаются в базе и показываются в карточке как «4 из 5».</span></div></li>
        <li><span class="dot"><svg viewBox="0 0 24 24"><path d="M12 3v12M7 10l5 5 5-5M4 20h16"/></svg></span><div><b>Пропуск остаётся пропуском</b><span>Пустая ячейка не превращается в ноль. Повторная загрузка файла не создаёт дублей.</span></div></li>
        <li><span class="dot"><svg viewBox="0 0 24 24"><path d="M5 12l4 4 10-10"/></svg></span><div><b>Разные вопросы у сторон</b><span>Вопросы стажёра и наставника сравниваются по парам, которые мы задаём в одном файле. Вопросы без пары показываются отдельно.</span></div></li>
      </ul>
      <p class="note">Готовые шаблоны двух таблиц и файл сопоставления колонок лежат в папке <code>prototype/mgts</code>. На финале мы смотрим выданные файлы командой <code>inspect_data.py</code>, правим названия колонок и загружаем данные. По плану это занимает 30–40 минут.</p>
    </section>

    """

p, a = d["people"], {x["id"]: x for x in d["people"]}
HEAT = json.dumps([[x["mentor"], x["m"]["performance"]] for x in p], ensure_ascii=False)
I4 = [round(1 + (v - 1) * 9 / 4, 2) for v in a["С-04"]["i"]["clarity"]]
T4 = a["С-04"]["m"]["performance"]

R = [
    ('<span class="tag">Учебные данные</span></a></div>\n  </section>', '<span class="tag">Учебные данные</span></a></div>\n  </section>'),
    ("<p>Три экрана на выдуманных данных.</p>", "<p>Пять экранов на выдуманных данных в формате вебинара.</p>"),
    ('<a href="#demo"><svg', '<a href="#data"><svg viewBox="0 0 24 24"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 9h16M4 15h16M10 3v18"/></svg><span>Данные</span></a>\n    <a href="#demo"><svg'),
    ("/* команда */", CSS + "/* команда */"),
    ('<section id="solution" class="card">', SECTION + '<section id="solution" class="card">'),
    ('<span class="pill">≥ 2 балла</span>', '<span class="pill">≥ 2,5 балла</span>'),
    ('<span class="pill">≥ 3 балла</span>', '<span class="pill">≥ 3,5 балла</span>'),
    ("<h2 id=\"exh\">Пример: нагрузка и ресурсы у одного стажёра</h2>", "<h2 id=\"exh\">Пример: понятность задач у одного стажёра</h2>"),
    ('<p class="sub">Выдуманные данные из макета. Оценки по шкале от 1 до 10.</p>\n      <div class="legend"><span><i></i>Стажёр</span><span><i class="m"></i>Наставник</span></div>',
     '<p class="sub">Выдуманные данные из макета. Вопросы у сторон разные, поэтому сравниваем пару: стажёр отвечает на «Насколько понятны задачи» (1–5), наставник на «Как стажёр справляется с задачами» (1–10). Обе шкалы приведены к 1–10.</p>\n      <div class="legend"><span><i></i>Стажёр: понятные задачи</span><span><i class="m"></i>Наставник: справляется с задачами</span></div>'),
    ('aria-label="Оценка стажёра по вопросу «Нагрузка и ресурсы» снижается с 8 до 4, оценка наставника остаётся 8"', 'aria-label="Оценка наставника «Справляется с задачами» снижается с 9 до 4 из 10, оценка стажёра «Понятные задачи» остаётся 4 из 5"'),
    ('С сентября стажёр ставит всё меньше, наставник по-прежнему ставит 8. Это расхождение попадает в список для проверки.', 'С сентября наставник снижает оценку с 9 до 4 из 10, а стажёр по-прежнему ставит 4 из 5 и считает задачи понятными. Стороны видят ситуацию по-разному: это расхождение попадает в список для проверки.'),
    ("I=[8,8,7,5,4,4],T=[8,8,8,8,8,8];", f"I={I4},T={T4};"),
    ("Стажёр 4 · Наставник 8", "Стажёр 4 из 5 · Наставник 4 из 10"),
    ('<rect width="138" height="50"', '<rect width="214" height="50"'),
    ("translate('+(x(5)-150)+'", "translate('+(x(5)-226)+'"),
    ("<h2 id=\"hh\">Пример: оценки стажёров по месяцам</h2>", "<h2 id=\"hh\">Пример: оценки наставников по месяцам</h2>"),
    ("Тот же вопрос у пяти выдуманных стажёров.", "Вопрос «Как стажёр справляется с задачами» у пяти выдуманных наставников, из 10."),
]
for path in [ROOT / "site/index.html", ROOT / "publish/docs/index.html"]:
    s = path.read_text(encoding="utf-8")
    if 'id="data"' in s:
        print("уже применено:", path)
        continue
    for old, new in R:
        if old not in s:
            raise SystemExit("не найдено: " + old[:70])
        s = s.replace(old, new, 1)
    # тепловая карта: данные, максимум, правило цвета по доле от максимума
    s = re.sub(r"var P=\[\[.*?\]\]\];", "var P=" + HEAT + ";", s, count=1, flags=re.S)
    old_cells = s[s.index("    var k=v>=7?"): s.index("}).join('');});")]
    s = s.replace(old_cells, "    var k=v/10>=.7?' good':v/10>.5?' mid':' low';\n    return'<span class=\"c'+k+'\">'+v+'/10</span>';")
    old_leg = s[s.index('<div class="hl"><span><i style="background:var(--g-bg)'):]
    old_leg = old_leg[: old_leg.index("</div>") + 6]
    s = s.replace(old_leg, '<div class="hl"><span><i style="background:var(--g-bg);border:1px solid var(--g-bd)"></i>хорошо: от 70 % максимума (7–10 из 10)</span><span><i style="background:var(--m-bg);border:1px solid var(--m-bd)"></i>средне: больше 50 % (6)</span><span><i style="background:var(--r-bg);border:1px solid var(--r-bd)"></i>плохо: 50 % и ниже (5 и ниже)</span></div>')
    path.write_text(s, encoding="utf-8", newline="")
    print("ок:", path)
