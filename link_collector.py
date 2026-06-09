#!/usr/bin/env python3
"""
Link Collector — Übersicht aller Quellen des Finance News Agent
===============================================================
Startet einen kleinen Webserver mit zwei Listen:
  - Einzelmeldungen: eigene Links (custom_urls.txt) + GitHub Issues
  - News-Seiten:     RSS-Feeds (regelmäßige Bewertung)

Verwendung:
    python link_collector.py

Dann im Browser (PC):   http://localhost:8765
"""

import os
import re
import socket
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs
from datetime import datetime, timezone

import requests

CUSTOM_URLS_FILE = "custom_urls.txt"
GITHUB_REPO      = "tobiashobert/finance-news-agent"
PORT             = 8765

RSS_FEEDS = [
    {"name": "Google News Finanzen",   "url": "https://news.google.com/rss/search?q=finanzen+aktien+börse&hl=de&gl=DE&ceid=DE:de"},
    {"name": "Google News Wirtschaft", "url": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtUmxHZ0pFUlNnQVAB?hl=de&gl=DE&ceid=DE:de"},
    {"name": "FAZ Wirtschaft",         "url": "https://www.faz.net/rss/aktuell/wirtschaft/"},
    {"name": "FAZ Finanzen",           "url": "https://www.faz.net/rss/aktuell/finanzen/"},
    {"name": "WirtschaftsWoche",       "url": "https://www.wiwo.de/contentexport/feed/rss/schlagzeilen"},
    {"name": "NZZ Wirtschaft",         "url": "https://www.nzz.ch/wirtschaft.rss"},
    {"name": "NZZ Finanzen",           "url": "https://www.nzz.ch/finanzen.rss"},
    {"name": "WELT Wirtschaft",        "url": "https://www.welt.de/feeds/section/wirtschaft.rss"},
    {"name": "RND Wirtschaft",         "url": "https://www.rnd.de/arc/outboundfeeds/rss/category/wirtschaft/"},
    {"name": "RND Geld & Finanzen",    "url": "https://www.rnd.de/arc/outboundfeeds/rss/category/geld-und-finanzen/"},
]


# ── Datei-Hilfsfunktionen ─────────────────────────────────────────────────────

def load_custom_urls() -> list[str]:
    if not os.path.exists(CUSTOM_URLS_FILE):
        return []
    with open(CUSTOM_URLS_FILE, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def save_url(url: str) -> bool:
    url = url.strip()
    if not url.startswith("http"):
        return False
    if url in load_custom_urls():
        return False
    with open(CUSTOM_URLS_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")
    return True


def delete_custom_url(url: str):
    urls = [u for u in load_custom_urls() if u != url]
    with open(CUSTOM_URLS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(urls) + ("\n" if urls else ""))


def load_github_issues() -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/issues?state=open&per_page=50",
            headers=headers, timeout=8
        )
        resp.raise_for_status()
        return [i for i in resp.json() if "pull_request" not in i]
    except Exception:
        return []


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ── HTML ──────────────────────────────────────────────────────────────────────

def render_page(message: str = "", message_type: str = "success") -> str:
    custom_urls  = load_custom_urls()
    github_issues = load_github_issues()
    url_pattern  = re.compile(r"https?://[^\s\)\]>\"']+")

    msg_html = ""
    if message:
        bg    = "#14532d" if message_type == "success" else "#7f1d1d"
        color = "#86efac" if message_type == "success" else "#fca5a5"
        msg_html = f'<div style="background:{bg};color:{color};padding:10px 14px;border-radius:8px;margin-bottom:16px;font-size:14px">{message}</div>'

    # ── Liste 1: Einzelmeldungen ──────────────────────────────────────────────
    einzeln_rows = ""

    for u in custom_urls:
        short = u[:65] + "…" if len(u) > 65 else u
        einzeln_rows += f"""
        <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;
                    background:#1e293b;border-radius:8px;margin-bottom:8px">
          <div style="width:6px;height:6px;border-radius:50%;background:#60a5fa;flex-shrink:0"></div>
          <a href="{u}" target="_blank"
             style="flex:1;color:#93c5fd;font-size:13px;word-break:break-all;text-decoration:none">{short}</a>
          <span style="background:#1e3a5f;color:#93c5fd;padding:2px 7px;border-radius:10px;
                       font-size:11px;flex-shrink:0">Datei</span>
          <form method="post" action="/delete" style="margin:0">
            <input type="hidden" name="url" value="{u}">
            <button type="submit" style="background:#7f1d1d;color:#fca5a5;border:none;
                    padding:4px 10px;border-radius:6px;cursor:pointer;font-size:12px">✕</button>
          </form>
        </div>"""

    for issue in github_issues:
        text = (issue.get("title", "") + " " + (issue.get("body") or ""))
        urls = url_pattern.findall(text)
        for u in urls:
            short = u[:65] + "…" if len(u) > 65 else u
            gh_url = issue.get("html_url", "")
            einzeln_rows += f"""
            <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;
                        background:#1e293b;border-radius:8px;margin-bottom:8px">
              <div style="width:6px;height:6px;border-radius:50%;background:#a78bfa;flex-shrink:0"></div>
              <div style="flex:1;min-width:0">
                <a href="{u}" target="_blank"
                   style="color:#93c5fd;font-size:13px;word-break:break-all;text-decoration:none;display:block">{short}</a>
                <a href="{gh_url}" target="_blank"
                   style="color:#64748b;font-size:11px;text-decoration:none">
                  Issue #{issue['number']}: {issue.get('title','')[:50]}</a>
              </div>
              <span style="background:#2d1b69;color:#a78bfa;padding:2px 7px;border-radius:10px;
                           font-size:11px;flex-shrink:0">GitHub</span>
            </div>"""

    total_einzeln = len(custom_urls) + sum(
        len(url_pattern.findall((i.get("title","")+" "+(i.get("body") or ""))))
        for i in github_issues
    )
    if not einzeln_rows:
        einzeln_rows = '<div style="color:#475569;font-size:13px;padding:10px 0">Noch keine Einzelmeldungen.</div>'

    # ── Liste 2: RSS News-Seiten ───────────────────────────────────────────────
    feed_rows = ""
    for feed in RSS_FEEDS:
        feed_rows += f"""
        <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;
                    background:#1e293b;border-radius:8px;margin-bottom:8px">
          <div style="width:6px;height:6px;border-radius:50%;background:#22c55e;flex-shrink:0"></div>
          <div style="flex:1">
            <div style="font-size:13px;font-weight:600">{feed['name']}</div>
            <a href="{feed['url']}" target="_blank"
               style="color:#475569;font-size:11px;text-decoration:none;word-break:break-all">{feed['url'][:70]}{"…" if len(feed['url'])>70 else ""}</a>
          </div>
          <span style="background:#14532d;color:#86efac;padding:2px 7px;border-radius:10px;
                       font-size:11px;flex-shrink:0">RSS</span>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Finance News Agent — Quellen</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0 }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #0f172a; color: #e2e8f0;
          padding: 24px 16px; max-width: 680px; margin: 0 auto }}
  h1 {{ font-size: 20px; font-weight: 700; margin-bottom: 4px }}
  .section-title {{ font-size: 13px; font-weight: 600; text-transform: uppercase;
                    letter-spacing: .07em; color: #64748b; margin: 24px 0 10px;
                    display: flex; align-items: center; gap: 8px }}
  .badge {{ padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600 }}
  input[type=url] {{ width: 100%; padding: 12px 14px; background: #1e293b;
                     border: 1px solid #334155; border-radius: 8px;
                     color: #e2e8f0; font-size: 15px; margin-bottom: 10px }}
  button[type=submit] {{ width: 100%; padding: 12px; background: #2563eb;
                         color: white; border: none; border-radius: 8px;
                         font-size: 15px; font-weight: 600; cursor: pointer }}
  button[type=submit]:hover {{ background: #1d4ed8 }}
  .hint {{ color: #64748b; font-size: 12px; margin-top: 6px }}
  .legend {{ display:flex; gap:16px; margin-bottom:12px; flex-wrap:wrap }}
  .legend-item {{ display:flex; align-items:center; gap:6px; font-size:12px; color:#94a3b8 }}
  .dot {{ width:8px; height:8px; border-radius:50%; flex-shrink:0 }}
</style>
</head>
<body>
  <h1>📊 Finance News Agent — Quellen</h1>
  <p style="color:#64748b;font-size:13px;margin-top:4px">
    Übersicht aller Quellen, die beim nächsten Agentenlauf ausgewertet werden.
  </p>

  {msg_html}

  <div class="section-title">
    ➕ Link hinzufügen
  </div>
  <form method="post" action="/add">
    <input type="url" name="url" placeholder="https://..." required
           autocomplete="off" autocorrect="off" spellcheck="false">
    <button type="submit">Zur Einzelmeldung hinzufügen</button>
  </form>
  <div class="hint">Oder per GitHub App: Repo öffnen → Issues → New Issue → Link einfügen</div>

  <div class="section-title">
    📌 Einzelmeldungen — einmalige Bewertung
    <span class="badge" style="background:#1e3a5f;color:#93c5fd">{total_einzeln}</span>
  </div>
  <div class="legend">
    <div class="legend-item"><div class="dot" style="background:#60a5fa"></div>Direkt gespeichert</div>
    <div class="legend-item"><div class="dot" style="background:#a78bfa"></div>Via GitHub Issue</div>
  </div>
  {einzeln_rows}

  <div class="section-title">
    📡 News-Seiten — regelmäßige Bewertung
    <span class="badge" style="background:#14532d;color:#86efac">{len(RSS_FEEDS)}</span>
  </div>
  {feed_rows}

  <p style="color:#334155;font-size:11px;margin-top:28px;text-align:center">
    finance-news-agent · github.com/{GITHUB_REPO}
  </p>
</body>
</html>"""


# ── Server ────────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(render_page().encode("utf-8"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length).decode("utf-8")
        params = parse_qs(body)
        url    = params.get("url", [""])[0].strip()

        if self.path == "/add":
            if save_url(url):
                msg, mtype = f"✓ Gespeichert: {url[:60]}", "success"
            elif url:
                msg, mtype = "Link bereits vorhanden.", "error"
            else:
                msg, mtype = "Bitte eine gültige URL eingeben.", "error"
        elif self.path == "/delete":
            delete_custom_url(url)
            msg, mtype = "Gelöscht.", "success"
        else:
            msg, mtype = "", "success"

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(render_page(msg, mtype).encode("utf-8"))


if __name__ == "__main__":
    ip = get_local_ip()
    print(f"\n📊  Finance News Agent — Quellen")
    print(f"    PC:    http://localhost:{PORT}")
    print(f"    Handy: http://{ip}:{PORT}  (gleiches WLAN)")
    print(f"\n    Strg+C zum Beenden\n")
    import webbrowser
    webbrowser.open(f"http://localhost:{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
