"""Приёмник ответов внешней формы (webhook).
POST /response с JSON-ответом. Подтверждает получение сразу, без ожидания разбора текста моделью.
Заголовок x-delivery-id сохраняется для повторных доставок. Если задана WEBHOOK_TOKEN, нужен заголовок x-token.
Запуск: python receiver.py   (по умолчанию 127.0.0.1:8765)
Реальные формы (Яндекс, Google) шлют запросы с интернета: для них нужен публичный адрес, это за рамками прототипа.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import core

TOKEN = os.environ.get("WEBHOOK_TOKEN")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(200, {"status": "ok"}) if self.path == "/health" else self._send(404, {"status": "not_found"})

    def do_POST(self):
        if self.path != "/response":
            return self._send(404, {"status": "not_found"})
        if TOKEN and self.headers.get("x-token") != TOKEN:
            return self._send(401, {"status": "unauthorized"})
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"null")
        except ValueError:
            return self._send(400, {"status": "rejected", "reason": "тело запроса не JSON"})
        res = core.ingest(payload, delivery_id=self.headers.get("x-delivery-id"))
        self._send(400 if res["status"] == "rejected" else 200, res)

    def log_message(self, fmt, *args):
        print("[receiver]", fmt % args)


if __name__ == "__main__":
    host, port = os.environ.get("RECEIVER_HOST", "127.0.0.1"), int(os.environ.get("RECEIVER_PORT", "8765"))
    print(f"Приёмник слушает http://{host}:{port}/response, база {core.DB_PATH}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
