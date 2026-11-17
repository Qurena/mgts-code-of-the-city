"""Проверки ядра. Запуск: python -m unittest -v"""
import os
import tempfile
import unittest

import core
import seed


def fresh():
    d = tempfile.mkdtemp()
    con = core.connect(os.path.join(d, "t.db"))
    seed.seed(con)
    core.analyze_pending(con)
    return con


def answer(rid, side="intern", iid=5, period=6, **kw):
    return {"response_id": rid, "source": side, "intern_id": iid, "period": period,
            "scores": kw.pop("scores", {"goals": 7, "feedback": 7, "resources": 7, "growth": 7}), "comment": kw.pop("comment", None), **kw}


class Ingest(unittest.TestCase):
    def setUp(self):
        self.con = fresh()

    def test_duplicate_is_counted_once(self):
        self.assertEqual(core.ingest(answer("x1"), con=self.con)["status"], "new")
        self.assertEqual(core.ingest(answer("x1"), con=self.con)["status"], "duplicate")
        n = self.con.execute("SELECT COUNT(*) FROM responses_raw WHERE response_id='x1'").fetchone()[0]
        self.assertEqual(n, 1)

    def test_rejects_are_logged_with_reason(self):
        bad = [answer("b1", scores={"goals": 11}), answer("b2", side="boss"), answer("b3", iid=99), answer("b4", period=7), {"x": 1}, "text"]
        for p in bad:
            self.assertEqual(core.ingest(p, con=self.con)["status"], "rejected")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM rejects").fetchone()[0], len(bad))

    def test_correction_replaces_earlier_version(self):
        core.ingest(answer("c1", period=5, scores={"goals": 7}), con=self.con)
        core.ingest(answer("c1", period=5, scores={"goals": 3}, version=2), con=self.con)
        df = core.load_answers(self.con)
        v = df[(df.response_id == "c1")]
        self.assertEqual(len(v), 1)
        self.assertEqual(v.iloc[0]["goals"], 3)

    def test_missing_answer_is_not_zero(self):
        df = core.load_answers(self.con)
        self.assertTrue(df[(df.source == "intern") & (df.intern_id == 5) & (df.period == 6)].empty)


class Signals(unittest.TestCase):
    def setUp(self):
        self.con = fresh()

    def sig(self):
        return core.compute_signals(core.load_answers(self.con), core.participants(self.con), core.load_analysis(self.con))

    def test_expected_demo_signals(self):
        types = sorted(s["type"] for s in self.sig())
        self.assertEqual(types, ["change", "change", "content", "content", "content", "content", "data", "divergence", "divergence"])

    def test_new_answer_removes_data_gap_signal(self):
        self.assertTrue(any(s["type"] == "data" and s["intern_id"] == 5 for s in self.sig()))
        core.ingest(answer("new1"), con=self.con)
        self.assertFalse(any(s["type"] == "data" and s["intern_id"] == 5 for s in self.sig()))

    def test_new_low_answer_creates_signals(self):
        core.ingest(answer("new2", scores={"goals": 7, "feedback": 7, "resources": 3, "growth": 7}, comment="Нет доступа к нужной системе."), con=self.con)
        core.analyze_pending(self.con)
        kinds = {(s["type"], s["dim"]) for s in self.sig() if s["intern_id"] == 5}
        self.assertIn(("change", "resources"), kinds)
        self.assertIn(("divergence", "resources"), kinds)
        self.assertIn(("content", "resources"), kinds)

    def test_repeated_topic_raises_priority(self):
        pr = {s["key"]: s["priority"] for s in self.sig() if s["type"] == "content" and s["intern_id"] == 2}
        self.assertEqual(sorted(pr.values()), [4, 4])

    def test_mentor_comment_gives_no_content_signal(self):
        self.assertFalse(any(s["type"] == "content" and "mentor" in s["key"] for s in self.sig()))


class Analysis(unittest.TestCase):
    def test_quote_is_verbatim(self):
        for text in ["Доступа до сих пор нет, задачи делаю в тестовой среде.", "Задания однотипные, нового мало.", "Всё устраивает."]:
            r = core.analyze(text)
            if r["evidence_quote"]:
                self.assertIn(r["evidence_quote"], text)

    def test_unknown_text_is_undefined_not_forced(self):
        r = core.analyze("Ну такое.")
        self.assertEqual(r["topics"], ["other"])
        self.assertIsNone(r["suggested_action"])

    def test_invented_quote_goes_to_manual_review(self):
        r = core.finalize({"topics": ["resources"], "evidence_quote": "выдуманная фраза", "summary": ""}, "Нет доступа к системе", "test")
        self.assertEqual(r["validation_status"], "manual")
        self.assertIsNone(r["evidence_quote"])
        self.assertIsNone(r["suggested_action"])

    def test_unknown_topic_is_dropped(self):
        r = core.finalize({"topics": ["salary"], "evidence_quote": None}, "текст", "test")
        self.assertEqual(r["topics"], ["other"])

    def test_cache_is_reused(self):
        con = fresh()
        self.assertEqual(core.analyze_pending(con), 0)


class LlmMode(unittest.TestCase):
    """Режим llm проверяется на поддельном сервере: настоящей модели в тестах нет."""

    def serve(self, content, code=200):
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class H(BaseHTTPRequestHandler):
            def do_POST(s):
                self.seen = json.loads(s.rfile.read(int(s.headers["Content-Length"])))
                s.send_response(code)
                s.send_header("Content-Type", "application/json")
                s.end_headers()
                s.wfile.write(json.dumps({"choices": [{"message": {"content": content}}]}).encode())

            def log_message(s, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)  # выполняется после shutdown: очистка идёт в обратном порядке
        self.addCleanup(srv.shutdown)
        os.environ.update(ANALYZER="llm", LLM_BASE_URL=f"http://127.0.0.1:{srv.server_port}/v1", LLM_TIMEOUT="5")
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in ("ANALYZER", "LLM_BASE_URL", "LLM_TIMEOUT")])

    def test_valid_answer_is_accepted(self):
        self.serve('Вот ответ: {"topics":["resources"],"evidence_quote":"нет доступа","summary":"нет доступа","ambiguity_flag":false}')
        r = core.analyze("У меня нет доступа к системе")
        self.assertEqual((r["analyzer"], r["validation_status"], r["topics"]), ("llm", "ok", ["resources"]))
        self.assertEqual(r["suggested_action"], core.ACTIONS["resources"])
        self.assertEqual(self.seen["response_format"], {"type": "json_object"})

    def test_invented_quote_from_model_is_not_trusted(self):
        self.serve('{"topics":["resources"],"evidence_quote":"доступ закрыт","summary":""}')
        r = core.analyze("У меня нет доступа к системе")
        self.assertEqual(r["validation_status"], "manual")

    def test_broken_answer_falls_back_to_rules(self):
        self.serve("не json")
        r = core.analyze("Задания однотипные, нового мало.")
        self.assertEqual(r["analyzer"], "keywords(fallback)")
        self.assertEqual(r["topics"], ["growth"])

    def test_server_error_falls_back_to_rules(self):
        self.serve("{}", code=500)
        self.assertEqual(core.analyze("Задания однотипные.")["analyzer"], "keywords(fallback)")


if __name__ == "__main__":
    unittest.main()
