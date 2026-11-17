"""Приёмник ответов внешней формы (webhook).
  POST /response       готовый ответ в формате проекта (JSON, см. README)
  POST /form/<имя>     сырой ответ формы (Google Forms, Яндекс Формы): колонки сопоставляются по mapping.json, источник с таким именем
  GET  /health
Подтверждает получение сразу, без ожидания разбора текста моделью. Заголовок x-delivery-id сохраняется для повторных доставок.
Если задана WEBHOOK_TOKEN, нужен заголовок x-token (или параметр ?token=, для сервисов, которые не умеют заголовки).
Каждое тело запроса пишется в таблицу inbox: по ней видно настоящий формат присланных данных.
Запуск: python receiver.py   (по умолчанию 127.0.0.1:8765; mapping.json берётся из MAPPING_FILE)
Реальные формы (Яндекс, Google) шлют запросы из интернета: для них нужен публичный адрес (VPS), у Яндекс Форм исходящие запросы идут по IPv6.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import core
import ingest_tools as it

TOKEN = os.environ.get("WEBHOOK_TOKEN")
MAPPING_FILE = Path(os.environ.get("MAPPING_FILE", Path(__file__).with_name("mapping.json")))


def load_mapping() -> dict:
    return json.loads(MAPPING_FILE.read_text(encoding="utf-8")) if MAPPING_FILE.exists() else {"sources": []}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(200, {"status": "ok"}) if urlparse(self.path).path == "/health" else self._send(404, {"status": "not_found"})

    def do_POST(self):
        url = urlparse(self.path)
        qs = parse_qs(url.query)
        token = self.headers.get("x-token") or (qs.get("token") or [None])[0]
        if TOKEN and token != TOKEN:
            return self._send(401, {"status": "unauthorized"})
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        con = core.connect()
        try:
            core.log_inbox(con, url.path, raw.decode("utf-8", "replace"))
            try:
                payload = json.loads(raw or b"null")
            except ValueError:
                return self._send(400, {"status": "rejected", "reason": "тело запроса не JSON"})
            delivery = self.headers.get("x-delivery-id")
            if url.path == "/response":
                res = core.ingest(payload, delivery_id=delivery, con=con)
            elif url.path.startswith("/form/"):
                name = url.path.split("/form/", 1)[1]
                mapping = load_mapping()
                spec = next((s for s in mapping["sources"] if s["name"] == name), None)
                if spec is None:
                    return self._send(404, {"status": "rejected", "reason": f"источник {name!r} не описан в mapping.json"})
                res = it.ingest_row(con, spec, it.flatten_payload(payload), mapping, delivery)
            else:
                return self._send(404, {"status": "not_found"})
            self._send(400 if res["status"] == "rejected" else 200, res)
        finally:
            con.close()

    def log_message(self, fmt, *args):
        print("[receiver]", fmt % args)


if __name__ == "__main__":
    host, port = os.environ.get("RECEIVER_HOST", "127.0.0.1"), int(os.environ.get("RECEIVER_PORT", "8765"))
    print(f"Приёмник слушает http://{host}:{port}/response и /form/<имя>, база {core.DB_PATH}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
