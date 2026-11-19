"""Готовый набор mgts/ (формат вебинара) загружается без ошибок и даёт ожидаемые сигналы. Запуск: python -m unittest test_mgts -v"""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).parent
M = HERE / "mgts"
RUN = r"""
import json, core, ingest_tools as it
m, b = it.load_mapping(r'%s')
con = core.connect(); rep = it.import_mapping(con, m, b); core.analyze_pending(con)
df, p, a = core.load_answers(con), core.participants(con), core.load_analysis(con)
print(json.dumps({"rep": rep["status"], "n": len(p), "sigs": sorted({(s["type"], s["intern"]) for s in core.compute_signals(df, p, a)})}, ensure_ascii=False))
""" % (M / "mapping.json")


class Mgts(unittest.TestCase):
    def test_package_loads(self):
        subprocess.run([sys.executable, "-X", "utf8", str(M / "make_data.py")], check=True, capture_output=True)
        env = {**os.environ, "SURVEY_CONFIG": str(M / "survey.json"), "PULSE_DB": str(Path(tempfile.mkdtemp()) / "t.db"),
               "PYTHONPATH": str(HERE), "PYTHONIOENCODING": "utf-8", "PYTHONWARNINGS": "ignore"}
        o = subprocess.run([sys.executable, "-c", RUN], capture_output=True, text=True, env=env, encoding="utf-8")
        self.assertEqual(o.returncode, 0, o.stderr)
        r = json.loads(o.stdout.strip().splitlines()[-1])
        self.assertEqual((r["n"], r["rep"]["new"], r["rep"]["rejected"]), (5, 59, 0))
        types = {t for t, _ in r["sigs"]}
        self.assertTrue({"divergence", "low", "change", "data", "content"} <= types)

    def test_templates_have_headers(self):
        import pandas as pd
        for f in ["Шаблон_ответы_стажёров.xlsx", "Шаблон_ответы_наставников.xlsx"]:
            self.assertIn("Как заполнять", pd.ExcelFile(M / "templates" / f).sheet_names)


if __name__ == "__main__":
    unittest.main()
