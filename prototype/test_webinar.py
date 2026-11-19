"""Проверка формата, который описали на вебинаре: две таблицы Excel, анонимные ID, пары один к одному,
разные вопросы у стажёра и наставника, сравнение по парам вопросов, настраиваемые пороги.
Запуск: python -m unittest test_webinar -v
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
REH = HERE / "rehearsal"

RUNNER = r"""
import json, sys
import core, ingest_tools as it
mapping, base = it.load_mapping(sys.argv[1])
con = core.connect()
rep = it.import_mapping(con, mapping, base)
core.analyze_pending(con)
df, p, a = core.load_answers(con), core.participants(con), core.load_analysis(con)
sigs = core.compute_signals(df, p, a)
strict = core.compute_signals(df, p, a, {"divergence": 9, "drop": 9, "low": 0})
core.set_threshold(con, "divergence", 8)
saved = core.get_thresholds(con)
core.reset_thresholds(con)
print(json.dumps({"rep": rep, "names": p.name.tolist(), "mentors": p.mentor_name.tolist(), "n_answers": len(df),
                  "sigs": [[s["type"], s["intern"], s["dim"], s["period"]] for s in sigs], "strict": [s["type"] for s in strict],
                  "items": [i["id"] for i in core.ITEMS], "saved": saved, "default": core.get_thresholds(con),
                  "summary": core.intern_summary(df, int(p.intern_id.iloc[1]))}, ensure_ascii=False, default=str))
"""


class Webinar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(REH / "make_webinar_data.py")], check=True, capture_output=True, cwd=str(REH))
        tmp = Path(tempfile.mkdtemp())
        env = {**os.environ, "SURVEY_CONFIG": str(REH / "survey.webinar.json"), "PULSE_DB": str(tmp / "w.db"), "PYTHONPATH": str(HERE),
               "PYTHONWARNINGS": "ignore", "PYTHONIOENCODING": "utf-8"}
        out = subprocess.run([sys.executable, "-c", RUNNER, str(REH / "mapping.webinar.json")], capture_output=True, text=True, env=env, cwd=str(REH), encoding="utf-8")
        assert out.returncode == 0, out.stderr
        cls.r = json.loads(out.stdout.strip().splitlines()[-1])

    def test_pairs_by_id_number_and_counts(self):
        r = self.r
        self.assertEqual(len(r["names"]), 5)
        for s, m in zip(r["names"], r["mentors"]):  # С-03 и Н-03: число в ID одно, хотя строки наставников шли в обратном порядке
            self.assertEqual(re.findall(r"\d+", s), re.findall(r"\d+", m))
        self.assertEqual(r["n_answers"], 29 + 30)  # у стажёра 5 нет ноябрьского ответа: пропуск остался пропуском
        self.assertTrue(any("по номеру в ID" in n for n in r["rep"]["notes"]))

    def test_comparison_items(self):
        self.assertIn("clarity-performance", self.r["items"])  # разные вопросы сторон сравниваются как пара
        self.assertIn("intern:access", self.r["items"])  # вопрос без пары показывается отдельно
        self.assertIn("mentor:speed", self.r["items"])

    def test_expected_signals(self):
        s = {(t, who, dim) for t, who, dim, _ in self.r["sigs"]}
        self.assertIn(("divergence", "С-03", "interest-independence"), s)  # стажёру неинтересно, наставник считает самостоятельным
        self.assertIn(("divergence", "С-04", "clarity-performance"), s)
        self.assertIn(("low", "С-02", "access"), s)  # доступов нет два месяца подряд
        self.assertIn(("change", "С-02", "access"), s)
        self.assertTrue(any(t == "data" and who == "С-05" for t, who, _ in s))
        self.assertTrue(any(t == "content" and who == "С-02" for t, who, _ in s))

    def test_thresholds_override_and_reset(self):
        self.assertEqual({"data", "content"} & set(self.r["strict"]), {"data", "content"})
        self.assertFalse({"divergence", "change", "low"} & set(self.r["strict"]))  # на строгих порогах оценочные сигналы пропадают
        self.assertEqual(self.r["saved"]["divergence"], 8)
        self.assertEqual(self.r["default"]["divergence"], 3.5)  # сброс возвращает значения из survey.json

    def test_intern_summary(self):
        row = next(x for x in self.r["summary"] if x["dim"] == "access")  # у стажёра 2 доступы упали с 4 до 1 (по 1-5)
        self.assertEqual(row["trend"], "↓")
        self.assertEqual(row["answered"], 6)


if __name__ == "__main__":
    unittest.main()
