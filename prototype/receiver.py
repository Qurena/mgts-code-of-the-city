"""Приёмник ответов внешней формы (webhook).
  POST /response       готовый ответ в формате проекта (JSON, см. README)
  POST /form/<имя>     сырой ответ формы (Google Forms, Яндекс Формы): колонки сопоставляются по mapping.json, источник с таким именем
  GET  /health
  GET  /api/dashboard  данные живого дашборда (dashboard_api.py); POST /api/status и /api/action пишут статус сигнала и действие HR
  GET  /, /index.html, /dashboard-prototype.html  статические страницы из STATIC_DIR (по умолчанию ../docs): красивый дашборд открывается на этом же адресе
Подтверждает получение сразу, без ожидания разбора текста моделью. Заголовок x-delivery-id сохраняется для повторных доставок.
Если задана WEBHOOK_TOKEN, нужен заголовок x-token (или параметр ?token=, для сервисов, которые не умеют заголовки).
Каждое тело запроса пишется в таблицу inbox: по ней видно настоящий формат присланных данных.
Запуск: python receiver.py   (по умолчанию 127.0.0.1:8765; сопоставление колонок: MAPPING_FILE, иначе mapping.json, иначе mapping.demo.json)
Реальные формы (Яндекс, Google) шлют запросы из интернета: для них нужен публичный адрес (VPS), у Яндекс Форм исходящие запросы идут по IPv6.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import core
import dashboard_api
import ingest_tools as it

TOKEN = os.environ.get("WEBHOOK_TOKEN")
STATIC_DIR = Path(os.environ.get("STATIC_DIR", Path(__file__).resolve().parent.parent / "docs"))
PAGES = {"/": "dashboard-prototype.html", "/index.html": "index.html", "/dashboard-prototype.html": "dashboard-prototype.html"}


def load_mapping() -> dict:
    return core.load_mapping()  # читается заново на каждый запрос: mapping.json можно править без перезапуска


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict, cache: bool = True) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if not cache:
            self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            return self._send(200, {"status": "ok"})
        if path == "/api/dashboard":
            con = core.connect()
            try:
                return self._send(200, dashboard_api.build(con), cache=False)
            finally:
                con.close()
        page = STATIC_DIR / PAGES[path] if path in PAGES else None
        if page and page.is_file():
            data = page.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        self._send(404, {"status": "not_found"})

    def do_POST(self):
        url = urlparse(self.path)
        if url.path in ("/api/status", "/api/action"):  # действия HR на странице дашборда: без токена вебхука, тело небольшое
            raw = self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 8192))
            try:
                payload = json.loads(raw or b"{}")
            except ValueError:
                return self._send(400, {"status": "rejected", "reason": "тело запроса не JSON"})
            con = core.connect()
            try:
                res = (dashboard_api.set_status if url.path == "/api/status" else dashboard_api.add_action)(con, payload if isinstance(payload, dict) else {})
            finally:
                con.close()
            return self._send(400 if res["status"] == "rejected" else 200, res)
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
