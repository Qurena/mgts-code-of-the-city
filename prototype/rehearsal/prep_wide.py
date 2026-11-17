"""Пример preprocess-функции: превращает широкую таблицу (месяцы в колонках) в длинную (одна строка = один месяц)."""
import pandas as pd


def prep(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for _, r in df.iterrows():
        months = {}
        for col in df.columns:
            if ":" in col:
                month, field = [x.strip() for x in col.split(":", 1)]
                months.setdefault(month, {})[field] = r[col]
        for month, vals in months.items():
            out.append({"ФИО": r["ФИО"], "Месяц": month, **vals})
    return pd.DataFrame(out)
