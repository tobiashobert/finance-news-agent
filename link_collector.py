#!/usr/bin/env python3
"""
Link Collector — Eigene URLs für den Finance News Agent einsammeln
===================================================================
Startet einen kleinen Webserver, den du vom Handy und PC aufrufen kannst.
Links werden in custom_urls.txt gespeichert und beim nächsten
Agentenlauf automatisch mit analysiert.

Verwendung:
    python link_collector.py

Dann im Browser (PC):   http://localhost:8765
Dann im Browser (Handy): http://<deine-IP>:8765
    (IP findest du mit: ipconfig → IPv4-Adresse)
"""

import os
import re
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from datetime import datetime

CUSTOM_URLS_FILE = "custom_urls.txt"
PORT = 8765


def load_urls() -> list[str]:
    if not os.path.exists(CUSTOM_URLS_FILE):
        return []
    with open(CUSTOM_URLS_FILE, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def save_url(url: str) -> bool:
    url = url.strip()
    if not url.startswith("http"):
        return False
    existing = load_urls()
    if url in existing:
        return False
    with open(CUSTOM_URLS_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")
    return True


def delete_url(url: str):
    urls = [u for u in load_urls() if u != url]
    with open(CUSTOM_URLS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(urls) + ("\n" if urls else ""))


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def render_page(message: str = "", message_type: str = "success") -> str:
    urls = load_urls()
    url_rows = ""
    for u in urls:
        short = u[:70] + "…" if len(u) > 70 else u
        url_rows += f"""
        <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;
                    background:#1e293b;border-radius:8px;margin-bottom:8px">
          <a href="{u}" target="_blank"
             style="flex:1;color:#93c5fd;font-size:13px;word-break:break-all;
                    text-decoration:none">{short}</a>
          <form method="post" action="/delete" style="margin:0">
            <input type="hidden" name="url" value="{u}">
            <button type="submit"
                    style="background:#7f1d1d;color:#fca5a5;border:none;
                           padding:4px 10px;border-radius:6px;cursor:pointer;
                           font-size:12px">✕</button>
          </form>
        </div>"""

    msg_html = ""
    if message:
        bg = "#14532d" if message_type == "success" else "#7f1d1d"
        color = "#86efac" if message_type == "success" else "#fca5a5"
        msg_html = f'<div style="background:{bg};color:{color};padding:10px 14px;border-radius:8px;margin-bottom:16px;font-size:14px">{message}</div>'

    empty = '<div style="color:#475569;font-size:13px;padding:10px 0">Noch keine Links gespeichert.</div>' if not urls else ""

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Finance Link Collector</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0 }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #0f172a; color: #e2e8f0;
          padding: 24px 16px; max-width: 640px; margin: 0 auto }}
  h1 {{ font-size: 20px; font-weight: 700; margin-bottom: 4px }}
  h2 {{ font-size: 13px; font-weight: 600; text-transform: uppercase;
        letter-spacing: .07em; color: #64748b; margin: 20px 0 10px }}
  input[type=url] {{ width: 100%; padding: 12px 14px; background: #1e293b;
                     border: 1px solid #334155; border-radius: 8px;
                     color: #e2e8f0; font-size: 15px; margin-bottom: 10px }}
  button[type=submit] {{ width: 100%; padding: 12px; background: #2563eb;
                         color: white; border: none; border-radius: 8px;
                         font-size: 15px; font-weight: 600; cursor: pointer }}
  button[type=submit]:hover {{ background: #1d4ed8 }}
  .hint {{ color: #64748b; font-size: 12px; margin-top: 6px }}
</style>
</head>
<body>
  <h1>📎 Link Collector</h1>
  <p style="color:#64748b;font-size:13px;margin-top:4px">
    Links werden beim nächsten Agentenlauf mit analysiert.
  </p>

  {msg_html}

  <h2>Link hinzufügen</h2>
  <form method="post" action="/add">
    <input type="url" name="url" placeholder="https://..." required
           autocomplete="off" autocorrect="off" spellcheck="false">
    <button type="submit">Hinzufügen</button>
  </form>
  <div class="hint">Tipp am Handy: Seite teilen → Browser → diese Adresse eingeben</div>

  <h2>Gespeicherte Links ({len(urls)})</h2>
  {url_rows}{empty}

  <p style="color:#334155;font-size:11px;margin-top:24px;text-align:center">
    Gespeichert in: {os.path.abspath(CUSTOM_URLS_FILE)}
  </p>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # stille Logs

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(render_page().encode("utf-8"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        params = parse_qs(body)
        url = params.get("url", [""])[0].strip()

        if self.path == "/add":
            if save_url(url):
                msg, mtype = f"✓ Gespeichert: {url[:60]}", "success"
            elif url:
                msg, mtype = "Link bereits vorhanden.", "error"
            else:
                msg, mtype = "Bitte eine gültige URL eingeben.", "error"
        elif self.path == "/delete":
            delete_url(url)
            msg, mtype = f"Gelöscht.", "success"
        else:
            msg, mtype = "", "success"

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(render_page(msg, mtype).encode("utf-8"))


if __name__ == "__main__":
    ip = get_local_ip()
    print(f"\n📎  Link Collector läuft")
    print(f"    PC:    http://localhost:{PORT}")
    print(f"    Handy: http://{ip}:{PORT}  (gleiches WLAN)")
    print(f"\n    Strg+C zum Beenden\n")
    import webbrowser
    webbrowser.open(f"http://localhost:{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
