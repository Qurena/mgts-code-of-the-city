"""Быстрый осмотр незнакомой таблицы: какие колонки есть и что в них лежит. Нужен, чтобы за минуты составить mapping.json.
Запуск:  python inspect_data.py файл.xlsx [--sheet 0|имя] [--table 0]      (для .docx берётся таблица Word)
         python inspect_data.py "https://docs.google.com/spreadsheets/d/..../edit#gid=0"
"""
import argparse
import re

import pandas as pd

import ingest_tools as it


def guess(s: pd.Series) -> str:
    vals = s.dropna().astype(str).str.strip()
    vals = vals[vals != ""]
    n = len(vals)
    if n == 0:
        return "пусто"
    num = pd.to_numeric(vals.str.replace(",", ".", regex=False), errors="coerce")
    if num.notna().mean() > 0.9:
        return f"число {num.min():g}..{num.max():g}" + (" (похоже на оценку)" if num.max() <= 10 and num.min() >= 0 else "")
    lead = vals.str.extract(r"^\s*(\d+)\b")[0]
    if lead.notna().mean() > 0.9:
        return f"оценка с подписью (число в начале: {lead.astype(float).min():g}..{lead.astype(float).max():g})"
    dates = pd.to_datetime(vals, dayfirst=True, errors="coerce")
    if dates.notna().mean() > 0.9:
        return f"дата {dates.min():%Y-%m-%d}..{dates.max():%Y-%m-%d}"
    uniq = vals.nunique()
    avg = vals.str.len().mean()
    if avg > 40:
        return f"длинный текст (в среднем {avg:.0f} знаков) — похоже на комментарий"
    if uniq <= 12:
        return f"категории ({uniq}): {', '.join(vals.value_counts().index[:8])}"
    if uniq >= 0.8 * n:
        return f"почти уникальные значения ({uniq} из {n}) — имя или идентификатор"
    return f"текст, {uniq} разных значений"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--sheet", default=0)
    ap.add_argument("--table", type=int, default=0)
    a = ap.parse_args()
    sheet = int(a.sheet) if str(a.sheet).isdigit() else a.sheet
    spec = {"name": "inspect", "file" if not a.source.startswith("http") else "url": a.source, "sheet": sheet, "table": a.table}
    if a.source.lower().endswith(".xlsx") or a.source.lower().endswith(".xls"):
        xl = pd.ExcelFile(a.source)
        print("Листы:", xl.sheet_names)
    df = it.read_source(spec)
    print(f"Строк: {len(df)}, колонок: {len(df.columns)}\n")
    for c in df.columns:
        print(f"• {c!r}\n    {guess(df[c])}\n    примеры: {[str(x)[:40] for x in df[c].dropna().head(3)]}")
    print("\nПервые строки:")
    with pd.option_context("display.max_columns", 30, "display.width", 200, "display.max_colwidth", 30):
        print(df.head(5).to_string())
    ids = [c for c in df.columns if re.search(r"фио|имя|стажёр|стажер|наставник|участник|name|id", c, re.I)]
    if ids:
        print("\nКандидаты в колонки участников:", ids)


if __name__ == "__main__":
    main()
