"""Репетиционные данные в «неудобном» формате, не похожем на нашу внутреннюю модель.
Нужны, чтобы заранее прогнать весь путь: файлы -> mapping.json -> база -> дашборд (и в тестах).
Запуск:  python rehearsal/make_sample_data.py [папка]
Создаёт: interns.xlsx (длинная таблица, оценки 1-5 и текстом «4 - хорошо», дата вместо месяца),
         mentors.csv (шкала 1-10, колонка стажёра с иным написанием имени),
         interns_wide.xlsx (широкая таблица: месяцы в колонках, нужна preprocess-функция) и interns.docx (таблица Word).
Все имена и тексты выдуманы.
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data"
OUT.mkdir(parents=True, exist_ok=True)

INTERNS = ["Соколова Анна Петровна", "Громов Илья Сергеевич", "Белова Мария Олеговна", "Ким Даниил Алексеевич", "Орлов Артём Викторович"]
MENTORS = ["Фомин Д.", "Лебедева Е.", "Кузнецов П.", "Захарова Т.", "Николаев С."]
MONTHS = [date(2026, m, 15) for m in range(6, 12)]  # июнь-ноябрь
LABEL5 = {1: "1 - плохо", 2: "2 - ниже ожиданий", 3: "3 - нормально", 4: "4 - хорошо", 5: "5 - отлично"}
# оценки стажёров по 5-балльной шкале: [Q1 понятность задач, Q2 доступ к инструментам, Q3 обратная связь]
INT = {
    0: ([5, 5, 4, 4, 4, 5], [5, 5, 5, 4, 5, 5], [4, 4, 4, 5, 4, 4]),
    1: ([4, 4, 4, 3, 3, 3], [5, 5, 4, 4, 4, 4], [3, 3, 3, 3, 2, 2]),
    2: ([4, 4, 4, 4, 4, 4], [5, 4, 3, 2, 1, 1], [4, 4, 4, 4, 4, 4]),
    3: ([3, 4, 4, 4, 4, 4], [4, 4, 4, 4, 4, None], [4, 4, 4, 4, 4, None]),
    4: ([5, 5, 5, 5, 5, 5], [5, 5, 5, 5, 5, 5], [5, 5, 5, 5, 5, 5]),
}
INT_TEXT = {
    (2, 3): "Не могу получить доступ к системе заявок, жду доступ уже две недели.",
    (2, 5): "Доступа до сих пор нет, работаю в тестовой среде.",
    (1, 4): "За месяц так и не получилось обсудить работу с наставником.",
}
MEN = {i: [min(10, max(1, round(v * 2))) for v in INT[i][0]] for i in INT}
MEN[2] = [8, 8, 8, 8, 8, 8]
MEN_TEXT = {(2, 5): "Мария быстро включилась, вопросов по работе нет."}

rows = []
for i, name in enumerate(INTERNS):
    for m in range(6):
        if INT[i][1][m] is None:
            continue
        rows.append({
            "Отметка времени": MONTHS[m].strftime("%d.%m.%Y") + f" 18:{i * 7:02d}:00", "ФИО": name, "Наставник": MENTORS[i],
            "Понятны ли задачи": LABEL5[INT[i][0][m]], "Хватает ли доступов и инструментов": INT[i][1][m], "Достаточно ли обратной связи": INT[i][2][m],
            "Что мешает работать?": INT_TEXT.get((i, m)), "Что получилось лучше всего?": "Разобрался с процессом" if m == 5 and i == 0 else None,
        })
pd.DataFrame(rows).to_excel(OUT / "interns.xlsx", index=False)

mrows = []
for i, name in enumerate(INTERNS):
    for m in range(6):
        short = name.split()[0] + " " + name.split()[1][0] + "."  # другое написание: «Соколова А.»
        mrows.append({
            "Timestamp": MONTHS[m].strftime("%Y-%m-%d"), "Наставник": MENTORS[i], "Стажёр": short,
            "Самостоятельность (1-10)": MEN[i][m], "Качество результата (1-10)": MEN[i][m], "Комментарий": MEN_TEXT.get((i, m)),
        })
pd.DataFrame(mrows).to_csv(OUT / "mentors.csv", index=False, encoding="utf-8-sig")

wide = {"ФИО": INTERNS}
for m, mon in enumerate(["Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь"]):
    wide[f"{mon}: понятность задач"] = [INT[i][0][m] for i in range(5)]
    wide[f"{mon}: комментарий"] = [INT_TEXT.get((i, m)) for i in range(5)]
pd.DataFrame(wide).to_excel(OUT / "interns_wide.xlsx", index=False)

try:
    import docx

    d = docx.Document()
    d.add_paragraph("Анкета стажёра, ответы")
    t = d.add_table(rows=1, cols=4)
    for c, h in zip(t.rows[0].cells, ["ФИО", "Месяц", "Понятность задач (1-5)", "Комментарий"]):
        c.text = h
    for i, name in enumerate(INTERNS[:3]):
        for m in range(6):
            r = t.add_row().cells
            r[0].text, r[1].text, r[2].text, r[3].text = name, ["Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь"][m], str(INT[i][0][m]), INT_TEXT.get((i, m)) or ""
    d.save(OUT / "interns.docx")
except ImportError:
    pass
print("Готово:", ", ".join(sorted(p.name for p in OUT.iterdir())), "->", OUT)
