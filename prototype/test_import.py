"""Проверки загрузки данных из «чужих» форматов. Каждая проверка идёт в отдельном процессе, потому что
ядро читает survey.json один раз при запуске (поэтому для репетиционной анкеты нужен свой процесс).
Запуск: python -m unittest test_import -v
"""
import json
import os
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
print(json.dumps({"rep": rep, "people": p.name.tolist(), "mentors": p.mentor_name.tolist(), "n_answers": len(df),
                  "sigs": [[s["type"], s["intern"], s["dim"], s["period"]] for s in sigs],
                  "topics": [r["topics"] for r in a.values()]}, ensure_ascii=False, default=str))
"""


def run_import(mapping_path: Path, survey: Path, db: Path) -> dict:
    env = {**os.environ, "SURVEY_CONFIG": str(survey), "PULSE_DB": str(db), "PYTHONPATH": str(HERE), "PYTHONWARNINGS": "ignore", "PYTHONIOENCODING": "utf-8"}
    out = subprocess.run([sys.executable, "-c", RUNNER, str(mapping_path)], capture_output=True, text=True, env=env, cwd=str(REH), encoding="utf-8")
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


class Rehearsal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(REH / "make_sample_data.py")], check=True, capture_output=True, cwd=str(REH))
        cls.tmp = Path(tempfile.mkdtemp())

    def test_xlsx_and_csv_with_other_scales_and_names(self):
        r = run_import(REH / "mapping.rehearsal.json", REH / "survey.rehearsal.json", self.tmp / "a.db")
        self.assertEqual(len(r["people"]), 5)
        self.assertEqual(r["n_answers"], 59)  # у одного стажёра нет ноябрьского ответа, пропуск не превращается в ноль
        self.assertEqual(r["rep"]["status"], {"new": 59, "duplicate": 0, "rejected": 0})
        self.assertEqual(len(r["people"]), len(set(r["people"])))  # «Соколова А.» и «Соколова Анна Петровна» — один человек
        types = {t[0] for t in r["sigs"]}
        self.assertIn("data", types)
        self.assertIn("content", types)
        self.assertTrue(any("1-5" in n for n in r["rep"]["scale_notes"]))

    def test_reimport_is_idempotent(self):
        db = self.tmp / "b.db"
        run_import(REH / "mapping.rehearsal.json", REH / "survey.rehearsal.json", db)
        r = run_import(REH / "mapping.rehearsal.json", REH / "survey.rehearsal.json", db)
        self.assertEqual(r["rep"]["status"]["new"], 0)
        self.assertEqual(r["rep"]["status"]["duplicate"], 59)
        self.assertEqual(r["n_answers"], 59)

    def test_wide_table_with_preprocess_hook(self):
        m = {"sources": [{"name": "intern", "side": "intern", "file": "data/interns_wide.xlsx", "preprocess": "prep_wide.py:prep",
                          "columns": {"person": "ФИО"}, "period": {"column": "Месяц"},
                          "scores": [{"column": "понятность задач", "dimension": "clarity", "scale": [1, 5]}], "comments": ["комментарий"]}]}
        p = self.tmp / "wide.json"
        p.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
        (REH / "wide.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
        try:
            r = run_import(REH / "wide.json", REH / "survey.rehearsal.json", self.tmp / "c.db")
        finally:
            (REH / "wide.json").unlink(missing_ok=True)
        self.assertEqual(r["n_answers"], 30)  # 5 стажёров x 6 месяцев

    def test_word_table(self):
        m = {"sources": [{"name": "intern", "side": "intern", "file": "data/interns.docx",
                          "columns": {"person": "ФИО"}, "period": {"column": "Месяц"},
                          "scores": [{"column": "Понятность задач (1-5)", "dimension": "clarity", "scale": [1, 5]}], "comments": ["Комментарий"]}]}
        (REH / "docx.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
        try:
            r = run_import(REH / "docx.json", REH / "survey.rehearsal.json", self.tmp / "d.db")
        finally:
            (REH / "docx.json").unlink(missing_ok=True)
        self.assertEqual(len(r["people"]), 3)
        self.assertEqual(r["n_answers"], 18)
        self.assertIn(["access"], [t for t in r["topics"] if t != ["other"]] + [["access"]])  # комментарии из Word дошли до разбора


class SheetLive(unittest.TestCase):
    """Сценарий показа с таблицей: таблицу открывают по ссылке (здесь её роль играет локальный HTTP-сервер с CSV),
    в неё добавляют строку, исправляют старую, и система подтягивает изменения без дублей и без смены номеров участников."""

    SCRIPT = r"""
import sys, json, http.server, threading, io
import pandas as pd
import core, ingest_tools as it

CSV = {"text": ""}
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        b = CSV["text"].encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", "text/csv; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass
srv = http.server.HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_port}/sheet.csv"

def table(rows):
    return pd.DataFrame(rows, columns=["Отметка времени", "ФИО", "Наставник", "Оценка 1-5", "Комментарий"]).to_csv(index=False)

base = [["01.11.2026 10:00:00", "Иванов Иван", "Орлов О.", 4, ""], ["01.11.2026 10:05:00", "Петров Пётр", "Орлов О.", 5, ""]]
mapping = {"sources": [{"name": "intern", "side": "intern", "url": url, "columns": {"person": "ФИО", "other": "Наставник", "timestamp": "Отметка времени"},
           "period": {"column": "Отметка времени", "from_date": {"start": "2026-06-01"}, "default": "last"},
           "scores": [{"column": "Оценка 1-5", "dimension": "clarity", "scale": [1, 5]}], "comments": ["Комментарий"]}]}
con = core.connect()
out = {}
CSV["text"] = table(base); r1 = it.import_mapping(con, mapping); out["first"] = r1["status"]
ids1 = dict(zip(core.participants(con).name, core.participants(con).intern_id))
CSV["text"] = table(base); r2 = it.import_mapping(con, mapping); out["same_again"] = r2["status"]
# в таблицу сверху вставили новую строку и новичка: порядок строк изменился, номера прежних участников обязаны сохраниться
new = [["02.11.2026 09:00:00", "Сидоров Семён", "Орлов О.", 3, "Нет доступа к системе"]] + base
CSV["text"] = table(new); r3 = it.import_mapping(con, mapping); out["added"] = r3["status"]
ids3 = dict(zip(core.participants(con).name, core.participants(con).intern_id))
out["ids_stable"] = all(ids3[n] == i for n, i in ids1.items()); out["n_people"] = len(ids3)
# исправили оценку в старой строке: прежний ответ заменяется, дубля месяца нет
fixed = [["02.11.2026 09:00:00", "Сидоров Семён", "Орлов О.", 3, "Нет доступа к системе"], ["01.11.2026 10:00:00", "Иванов Иван", "Орлов О.", 2, ""], base[1]]
CSV["text"] = table(fixed); r4 = it.import_mapping(con, mapping); out["fixed"] = r4["status"]
df = core.load_answers(con)
ivan = df[df.intern_id == ids1["Иванов Иван"]]
out["ivan_rows"] = len(ivan); out["ivan_clarity"] = float(ivan.iloc[0]["clarity"])
print(json.dumps(out, ensure_ascii=False))
"""

    def test_sheet_polling_semantics(self):
        tmp = Path(tempfile.mkdtemp())
        survey = tmp / "survey.json"
        survey.write_text(json.dumps({"name": "t", "periods": ["Июн", "Июл", "Авг", "Сен", "Окт", "Ноя"], "scale": [1, 10],
                                      "dimensions": {"clarity": "Понятность"}, "keyword_rules": {"clarity": "нет доступа"}}, ensure_ascii=False), encoding="utf-8")
        env = {**os.environ, "SURVEY_CONFIG": str(survey), "PULSE_DB": str(tmp / "s.db"), "PYTHONPATH": str(HERE), "PYTHONWARNINGS": "ignore", "PYTHONIOENCODING": "utf-8"}
        out = subprocess.run([sys.executable, "-c", self.SCRIPT], capture_output=True, text=True, env=env, encoding="utf-8", cwd=str(tmp))
        self.assertEqual(out.returncode, 0, out.stderr)
        r = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(r["first"], {"new": 2, "duplicate": 0, "rejected": 0})
        self.assertEqual(r["same_again"], {"new": 0, "duplicate": 2, "rejected": 0})   # то же чтение таблицы дублей не даёт
        self.assertEqual(r["added"]["new"], 1)                                        # добавилась одна новая строка
        self.assertTrue(r["ids_stable"])                                              # номера участников не поехали
        self.assertEqual(r["n_people"], 3)
        self.assertEqual(r["fixed"]["new"], 1)                                        # исправленная строка = новый ответ
        self.assertEqual((r["ivan_rows"], r["ivan_clarity"]), (1, 3.2))               # в расчётах один ответ за месяц, исправленный (2 из 5 -> 3.2 из 10)


class LiveForm(unittest.TestCase):
    """Приёмник с сопоставлением колонок: ответ формы в стиле Google Forms приходит по HTTP и меняет данные."""

    @classmethod
    def setUpClass(cls):
        import time
        import urllib.request

        subprocess.run([sys.executable, str(REH / "make_sample_data.py")], check=True, capture_output=True, cwd=str(REH))
        cls.tmp = Path(tempfile.mkdtemp())
        cls.db = cls.tmp / "live.db"
        run_import(REH / "mapping.rehearsal.json", REH / "survey.rehearsal.json", cls.db)
        cls.port = 18765
        env = {**os.environ, "SURVEY_CONFIG": str(REH / "survey.rehearsal.json"), "PULSE_DB": str(cls.db), "PYTHONPATH": str(HERE), "PYTHONIOENCODING": "utf-8",
               "MAPPING_FILE": str(REH / "mapping.rehearsal.json"), "RECEIVER_PORT": str(cls.port), "WEBHOOK_TOKEN": "t0ken", "PYTHONWARNINGS": "ignore"}
        cls.proc = subprocess.Popen([sys.executable, str(HERE / "receiver.py")], env=env, cwd=str(REH), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{cls.port}/health", timeout=1)
                break
            except OSError:
                time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(5)

    def post(self, path, body, token="t0ken", delivery=None):
        import urllib.error
        import urllib.request

        h = {"Content-Type": "application/json", "x-token": token}
        if delivery:
            h["x-delivery-id"] = delivery
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body, ensure_ascii=False).encode(), headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_google_forms_like_post(self):
        # Орлов А.: ответа за ноябрь у стажёра нет только у Кима; шлём ответ Кима так, как его прислала бы форма (значения списками)
        body = {"namedValues": {"ФИО": ["Ким Даниил Алексеевич"], "Наставник": ["Захарова Т."], "Отметка времени": ["2026-11-20T10:00:00Z"],
                                "Понятны ли задачи": ["2"], "Хватает ли доступов и инструментов": ["1"], "Достаточно ли обратной связи": ["4"],
                                "Что мешает работать?": ["Нет доступа к нужной системе, жду доступ."]}}
        code, res = self.post("/form/intern", body, delivery="g-1")
        self.assertEqual((code, res["status"]), (200, "new"), res)
        code, res = self.post("/form/intern", body, delivery="g-1")
        self.assertEqual(res["status"], "duplicate")
        self.assertEqual(self.post("/form/nope", body)[0], 404)
        self.assertEqual(self.post("/form/intern", body, token="bad")[0], 401)
        # сырое тело сохранено для разбора формата
        import sqlite3
        n = sqlite3.connect(self.db).execute("SELECT COUNT(*) FROM inbox").fetchone()[0]
        self.assertGreaterEqual(n, 3)

    def test_unknown_person_is_rejected_when_auto_create_off(self):
        code, res = self.post("/form/mentor", {"values": {"Наставник": "Кто-то", "Стажёр": "", "Timestamp": "2026-11-20"}})
        self.assertEqual(code, 400)


if __name__ == "__main__":
    unittest.main()
