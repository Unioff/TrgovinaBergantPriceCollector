import json
import sqlite3
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DB_PATH = Path(__file__).with_name("prices.db")
PAGE_PATH = Path(__file__).with_name("viewer.html")
HOST, PORT = "127.0.0.1", 8000


def load_data() -> dict:
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return {
            "artikli": [dict(r) for r in conn.execute("SELECT id, name FROM artikel ORDER BY name")],
            "trgovine": [dict(r) for r in conn.execute("SELECT ID AS id, Name AS name FROM trgovina ORDER BY ID")],
            "cene": [
                dict(r)
                for r in conn.execute(
                    "SELECT artikel_id, trgovina_id, date, price FROM cena ORDER BY date"
                )
            ],
        }
    finally:
        conn.close()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self.respond(200, "text/html; charset=utf-8", PAGE_PATH.read_bytes())
        elif self.path == "/api/data":
            self.respond(200, "application/json; charset=utf-8", json.dumps(load_data()).encode())
        else:
            self.respond(404, "text/plain; charset=utf-8", b"Not found")

    def respond(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/"
    print(f"Pregledovalnik cen: {url} (Ctrl+C za izhod)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
