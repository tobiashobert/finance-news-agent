#!/usr/bin/env python3
"""
Finance News Agent — Quellen & Watchlist Verwaltung
====================================================
Verwendung:  python link_collector.py
PC:          http://localhost:8765
Handy:       http://<lokale-IP>:8765  (gleiches WLAN)
"""

import os, re, json, socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import requests

CUSTOM_URLS_FILE  = "custom_urls.txt"
BLOCKLIST_FILE    = "blocklist.txt"
CUSTOM_FEEDS_FILE = "custom_feeds.json"
WATCHLIST_FILE    = "watchlist.json"
GITHUB_REPO       = "tobiashobert/finance-news-agent"
PORT              = 8765

RSS_FEEDS = [
    {"name": "Google News Finanzen",    "url": "https://news.google.com/rss/search?q=finanzen+aktien+börse&hl=de&gl=DE&ceid=DE:de",          "category": "Märkte"},
    {"name": "Google News Wirtschaft",  "url": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtUmxHZ0pFUlNnQVAB?hl=de&gl=DE&ceid=DE:de", "category": "Märkte"},
    {"name": "FAZ Wirtschaft",          "url": "https://www.faz.net/rss/aktuell/wirtschaft/",                                                  "category": "Märkte"},
    {"name": "FAZ Finanzen",            "url": "https://www.faz.net/rss/aktuell/finanzen/",                                                    "category": "Märkte"},
    {"name": "WirtschaftsWoche",        "url": "https://www.wiwo.de/contentexport/feed/rss/schlagzeilen",                                      "category": "Märkte"},
    {"name": "Handelsblatt",            "url": "https://www.handelsblatt.com/contentexport/feed/schlagzeilen",                                 "category": "Märkte"},
    {"name": "NZZ Wirtschaft",          "url": "https://www.nzz.ch/wirtschaft.rss",                                                           "category": "Märkte"},
    {"name": "NZZ Finanzen",            "url": "https://www.nzz.ch/finanzen.rss",                                                             "category": "Märkte"},
    {"name": "WELT Wirtschaft",         "url": "https://www.welt.de/feeds/section/wirtschaft.rss",                                            "category": "Märkte"},
    {"name": "RND Wirtschaft",          "url": "https://www.rnd.de/arc/outboundfeeds/rss/category/wirtschaft/",                               "category": "Märkte"},
    {"name": "RND Geld & Finanzen",     "url": "https://www.rnd.de/arc/outboundfeeds/rss/category/geld-und-finanzen/",                        "category": "Märkte"},
    {"name": "Tagesschau",              "url": "https://www.tagesschau.de/xml/rss2/",                                                         "category": "Welt"},
    {"name": "Spiegel Wirtschaft",      "url": "https://www.spiegel.de/wirtschaft/index.rss",                                                 "category": "Welt"},
    {"name": "Spiegel Politik",         "url": "https://www.spiegel.de/politik/index.rss",                                                    "category": "Welt"},
    {"name": "Zeit Wirtschaft",         "url": "https://newsfeed.zeit.de/wirtschaft/index",                                                   "category": "Welt"},
    {"name": "Zeit Politik",            "url": "https://newsfeed.zeit.de/politik/index",                                                      "category": "Welt"},
    {"name": "BBC Business",            "url": "https://feeds.bbci.co.uk/news/business/rss.xml",                                              "category": "Welt"},
    {"name": "BBC World",               "url": "https://feeds.bbci.co.uk/news/world/rss.xml",                                                 "category": "Welt"},
    {"name": "Google News Geopolitik",  "url": "https://news.google.com/rss/search?q=geopolitik+krieg+sanktionen&hl=de&gl=DE&ceid=DE:de",     "category": "Welt"},
    {"name": "Google News Rohstoffe",   "url": "https://news.google.com/rss/search?q=öl+gold+rohstoffe+preise&hl=de&gl=DE&ceid=DE:de",       "category": "Welt"},
    {"name": "Google News USA/Fed",     "url": "https://news.google.com/rss/search?q=fed+zinsen+usa+wirtschaft&hl=de&gl=DE&ceid=DE:de",       "category": "Welt"},
    {"name": "Google News China",       "url": "https://news.google.com/rss/search?q=china+wirtschaft+export&hl=de&gl=DE&ceid=DE:de",        "category": "Welt"},
]

# ── Datei-Hilfsfunktionen ─────────────────────────────────────────────────────

def load_custom_urls():
    if not os.path.exists(CUSTOM_URLS_FILE): return []
    with open(CUSTOM_URLS_FILE, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]

def save_url(url):
    url = url.strip()
    if not url.startswith("http"): return False
    if url in load_custom_urls(): return False
    with open(CUSTOM_URLS_FILE, "a", encoding="utf-8") as f: f.write(url + "\n")
    return True

def delete_custom_url(url):
    urls = [u for u in load_custom_urls() if u != url]
    with open(CUSTOM_URLS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(urls) + ("\n" if urls else ""))

def load_blocklist():
    if not os.path.exists(BLOCKLIST_FILE): return []
    with open(BLOCKLIST_FILE, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]

def save_blocked(domain):
    domain = domain.strip().lower().lstrip("www.").rstrip("/")
    if not domain or "." not in domain: return False
    if domain in load_blocklist(): return False
    with open(BLOCKLIST_FILE, "a", encoding="utf-8") as f: f.write(domain + "\n")
    return True

def delete_blocked(domain):
    entries = [e for e in load_blocklist() if e != domain]
    with open(BLOCKLIST_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(entries) + ("\n" if entries else ""))

def load_custom_feeds():
    if not os.path.exists(CUSTOM_FEEDS_FILE):
        return {"Märkte": [], "Welt": []}
    with open(CUSTOM_FEEDS_FILE, encoding="utf-8") as f:
        return json.load(f)

def save_custom_feed(name, url, category):
    data = load_custom_feeds()
    if category not in data: data[category] = []
    if any(f["url"] == url for f in data[category]): return False
    data[category].append({"name": name, "url": url})
    with open(CUSTOM_FEEDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return True

def delete_custom_feed(url, category):
    data = load_custom_feeds()
    if category in data:
        data[category] = [f for f in data[category] if f["url"] != url]
    with open(CUSTOM_FEEDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_watchlist():
    if not os.path.exists(WATCHLIST_FILE): return []
    with open(WATCHLIST_FILE, encoding="utf-8") as f:
        return json.load(f)

def save_watchlist(entries):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

def add_watchlist_entry(name, identifier, ticker, finanzen_url):
    entries = load_watchlist()
    if any(e["ticker"] == ticker for e in entries): return False
    entries.append({"name": name, "identifier": identifier,
                    "ticker": ticker, "finanzen_url": finanzen_url})
    save_watchlist(entries)
    return True

def delete_watchlist_entry(ticker):
    entries = [e for e in load_watchlist() if e["ticker"] != ticker]
    save_watchlist(entries)

def load_github_issues():
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/issues?state=open&per_page=50",
            headers=headers, timeout=8)
        resp.raise_for_status()
        return [i for i in resp.json() if "pull_request" not in i]
    except Exception:
        return []

def fetch_price(ticker):
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = info.last_price
        prev  = info.previous_close
        if price and prev:
            change = ((price - prev) / prev) * 100
            return price, change
    except Exception:
        pass
    return None, None

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# ── HTML ──────────────────────────────────────────────────────────────────────

def render_page(message="", message_type="success"):
    custom_urls   = load_custom_urls()
    github_issues = load_github_issues()
    blocklist     = load_blocklist()
    custom_feeds  = load_custom_feeds()
    watchlist     = load_watchlist()
    url_pattern   = re.compile(r"https?://[^\s\)\]>\"']+")

    msg_html = ""
    if message:
        bg    = "#14532d" if message_type == "success" else "#7f1d1d"
        col   = "#86efac" if message_type == "success" else "#fca5a5"
        msg_html = f'<div style="background:{bg};color:{col};padding:10px 14px;border-radius:8px;margin-bottom:16px;font-size:14px">{message}</div>'

    # ── Einzelmeldungen ───────────────────────────────────────────────────────
    einzeln_rows = ""
    for u in custom_urls:
        short = u[:65] + "…" if len(u) > 65 else u
        einzeln_rows += f"""
        <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:#1e293b;border-radius:8px;margin-bottom:8px">
          <div style="width:6px;height:6px;border-radius:50%;background:#60a5fa;flex-shrink:0"></div>
          <a href="{u}" target="_blank" style="flex:1;color:#93c5fd;font-size:13px;word-break:break-all;text-decoration:none">{short}</a>
          <span style="background:#1e3a5f;color:#93c5fd;padding:2px 7px;border-radius:10px;font-size:11px;flex-shrink:0">Datei</span>
          <form method="post" action="/delete" style="margin:0">
            <input type="hidden" name="url" value="{u}">
            <button type="submit" style="background:#7f1d1d;color:#fca5a5;border:none;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:12px">✕</button>
          </form>
        </div>"""
    for issue in github_issues:
        text = (issue.get("title","") + " " + (issue.get("body") or ""))
        for u in url_pattern.findall(text):
            short = u[:65] + "…" if len(u) > 65 else u
            einzeln_rows += f"""
            <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:#1e293b;border-radius:8px;margin-bottom:8px">
              <div style="width:6px;height:6px;border-radius:50%;background:#a78bfa;flex-shrink:0"></div>
              <div style="flex:1;min-width:0">
                <a href="{u}" target="_blank" style="color:#93c5fd;font-size:13px;word-break:break-all;text-decoration:none;display:block">{short}</a>
                <a href="{issue.get('html_url','')}" target="_blank" style="color:#64748b;font-size:11px;text-decoration:none">Issue #{issue['number']}: {issue.get('title','')[:50]}</a>
              </div>
              <span style="background:#2d1b69;color:#a78bfa;padding:2px 7px;border-radius:10px;font-size:11px;flex-shrink:0">GitHub</span>
            </div>"""
    total_einzeln = len(custom_urls) + sum(len(url_pattern.findall((i.get("title","")+" "+(i.get("body") or "")))) for i in github_issues)
    if not einzeln_rows:
        einzeln_rows = '<div style="color:#475569;font-size:13px;padding:10px 0">Noch keine Einzelmeldungen.</div>'

    # ── Feed-Blöcke ───────────────────────────────────────────────────────────
    def feed_section(category, dot_color, badge_bg, badge_col, icon):
        base_feeds   = [f for f in RSS_FEEDS if f.get("category") == category]
        custom       = custom_feeds.get(category, [])
        all_feeds    = base_feeds + [dict(f, custom=True) for f in custom]
        rows = ""
        for feed in all_feeds:
            base = "{u.scheme}://{u.netloc}".format(u=urlparse(feed["url"]))
            is_custom = feed.get("custom", False)
            delete_btn = ""
            if is_custom:
                delete_btn = f"""
                <form method="post" action="/delete_feed" style="margin:0">
                  <input type="hidden" name="url" value="{feed['url']}">
                  <input type="hidden" name="category" value="{category}">
                  <button type="submit" style="background:#7f1d1d;color:#fca5a5;border:none;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:12px">✕</button>
                </form>"""
            rows += f"""
            <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:#1e293b;border-radius:8px;margin-bottom:8px">
              <a href="{base}" target="_blank" style="display:flex;align-items:center;gap:10px;flex:1;text-decoration:none"
                 onmouseover="this.parentElement.style.background='#263548'" onmouseout="this.parentElement.style.background='#1e293b'">
                <div style="width:6px;height:6px;border-radius:50%;background:{dot_color};flex-shrink:0"></div>
                <div>
                  <div style="font-size:13px;font-weight:600;color:#e2e8f0">{feed['name']}{'  <span style="font-size:10px;color:#64748b">eigener Feed</span>' if is_custom else ''}</div>
                  <div style="color:#475569;font-size:11px">{base}</div>
                </div>
              </a>
              <span style="background:{badge_bg};color:{badge_col};padding:2px 7px;border-radius:10px;font-size:11px;flex-shrink:0">RSS ↗</span>
              {delete_btn}
            </div>"""
        # Formular zum Hinzufügen
        rows += f"""
        <form method="post" action="/add_feed" style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
          <input type="hidden" name="category" value="{category}">
          <input type="text" name="feed_name" placeholder="Name (z.B. Reuters DE)"
                 style="flex:1;min-width:120px;padding:8px 12px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:#e2e8f0;font-size:13px">
          <input type="url" name="feed_url" placeholder="RSS-URL"
                 style="flex:2;min-width:200px;padding:8px 12px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:#e2e8f0;font-size:13px">
          <button type="submit" style="padding:8px 14px;background:#1e3a5f;color:#93c5fd;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap">+ Feed</button>
        </form>"""
        return f"""
        <div class="section-title">{icon} {category} — regelmäßige Bewertung
          <span class="badge" style="background:{badge_bg};color:{badge_col}">{len(all_feeds)}</span>
        </div>
        {rows}"""

    feeds_html  = feed_section("Märkte", "#22c55e", "#14532d", "#86efac", "📈")
    feeds_html += feed_section("Welt",   "#f59e0b", "#451a03", "#fcd34d", "🌍")

    # ── Blocklist ─────────────────────────────────────────────────────────────
    blocklist_rows = ""
    for domain in blocklist:
        blocklist_rows += f"""
        <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:#1e293b;border-radius:8px;margin-bottom:8px">
          <div style="width:6px;height:6px;border-radius:50%;background:#ef4444;flex-shrink:0"></div>
          <span style="flex:1;font-size:13px;color:#fca5a5">{domain}</span>
          <form method="post" action="/unblock" style="margin:0">
            <input type="hidden" name="domain" value="{domain}">
            <button type="submit" style="background:#7f1d1d;color:#fca5a5;border:none;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:12px">✕ Freigeben</button>
          </form>
        </div>"""
    if not blocklist_rows:
        blocklist_rows = '<div style="color:#475569;font-size:13px;padding:8px 0">Noch keine Domains ausgeschlossen.</div>'

    # ── Watchlist ─────────────────────────────────────────────────────────────
    watchlist_rows = ""
    for entry in watchlist:
        price, change = fetch_price(entry["ticker"])
        if price is not None:
            price_str  = f"{price:,.2f}"
            change_col = "#22c55e" if change >= 0 else "#ef4444"
            change_str = f'<span style="color:{change_col};font-weight:600">{"+" if change>=0 else ""}{change:.2f}%</span>'
        else:
            price_str  = "–"
            change_str = '<span style="color:#64748b">–</span>'
        fn_url = entry.get("finanzen_url") or f"https://www.finanzen.net/suche/{entry['name'].replace(' ','+')}"
        watchlist_rows += f"""
        <div style="background:#1e293b;border-radius:8px;padding:12px 14px;margin-bottom:8px">
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
            <div style="flex:1;min-width:150px">
              <div style="font-size:14px;font-weight:700">{entry['name']}</div>
              <div style="font-size:11px;color:#64748b;margin-top:2px">{entry['identifier']} · {entry['ticker']}</div>
            </div>
            <div style="text-align:right">
              <div style="font-size:16px;font-weight:700">{price_str}</div>
              <div style="font-size:13px;margin-top:2px">{change_str}</div>
            </div>
            <a href="{fn_url}" target="_blank"
               style="background:#1e3a5f;color:#93c5fd;padding:6px 12px;border-radius:8px;font-size:12px;text-decoration:none;white-space:nowrap">
              📊 finanzen.net ↗
            </a>
            <form method="post" action="/delete_watchlist" style="margin:0">
              <input type="hidden" name="ticker" value="{entry['ticker']}">
              <button type="submit" style="background:#7f1d1d;color:#fca5a5;border:none;padding:6px 12px;border-radius:8px;cursor:pointer;font-size:12px">✕</button>
            </form>
          </div>
        </div>"""
    if not watchlist_rows:
        watchlist_rows = '<div style="color:#475569;font-size:13px;padding:8px 0">Noch keine Einträge. Unten hinzufügen.</div>'

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Finance News Agent — Quellen</title>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0 }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          background:#0f172a; color:#e2e8f0; padding:24px 16px; max-width:780px; margin:0 auto }}
  h1 {{ font-size:20px; font-weight:700; margin-bottom:4px }}
  .section-title {{ font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;
                    color:#64748b;margin:28px 0 10px;display:flex;align-items:center;gap:8px }}
  .badge {{ padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600 }}
  input[type=url],input[type=text] {{ padding:10px 12px;background:#1e293b;
    border:1px solid #334155;border-radius:8px;color:#e2e8f0;font-size:14px }}
  .btn-primary {{ padding:10px 16px;background:#2563eb;color:white;border:none;
                  border-radius:8px;font-size:14px;font-weight:600;cursor:pointer }}
  .btn-primary:hover {{ background:#1d4ed8 }}
  .btn-danger {{ padding:10px 16px;background:#7f1d1d;color:#fca5a5;border:none;
                 border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap }}
  .hint {{ color:#64748b;font-size:12px;margin-top:6px }}
  .legend {{ display:flex;gap:16px;margin-bottom:12px;flex-wrap:wrap }}
  .legend-item {{ display:flex;align-items:center;gap:6px;font-size:12px;color:#94a3b8 }}
  .dot {{ width:8px;height:8px;border-radius:50%;flex-shrink:0 }}
</style>
</head>
<body>
  <h1>📊 Finance News Agent — Quellen & Watchlist</h1>
  <p style="color:#64748b;font-size:13px;margin-top:4px">Alle Quellen und Investments auf einen Blick.</p>

  {msg_html}

  <div class="section-title">➕ Einzelmeldung hinzufügen</div>
  <form method="post" action="/add" style="display:flex;gap:8px">
    <input type="url" name="url" placeholder="https://..." required style="flex:1" autocomplete="off">
    <button type="submit" class="btn-primary">Hinzufügen</button>
  </form>
  <div class="hint">Oder per GitHub App: Repo öffnen → Issues → New Issue → Link einfügen</div>

  <div class="section-title">📌 Einzelmeldungen — einmalige Bewertung
    <span class="badge" style="background:#1e3a5f;color:#93c5fd">{total_einzeln}</span>
  </div>
  <div class="legend">
    <div class="legend-item"><div class="dot" style="background:#60a5fa"></div>Direkt</div>
    <div class="legend-item"><div class="dot" style="background:#a78bfa"></div>GitHub Issue</div>
  </div>
  {einzeln_rows}

  {feeds_html}

  <div class="section-title" style="margin-top:32px">🚫 Ausgeschlossene Domains
    <span class="badge" style="background:#3b0f0f;color:#fca5a5">{len(blocklist)}</span>
  </div>
  <p style="color:#64748b;font-size:12px;margin-bottom:10px">Meldungen von diesen Domains werden in allen Feeds gefiltert.</p>
  <form method="post" action="/block" style="display:flex;gap:8px;margin-bottom:12px">
    <input type="text" name="domain" placeholder="z.B. bild.de" style="flex:1" autocomplete="off">
    <button type="submit" class="btn-danger">+ Ausschließen</button>
  </form>
  {blocklist_rows}

  <div class="section-title" style="margin-top:32px">💼 Watchlist / Portfolio
    <span class="badge" style="background:#1e3a5f;color:#93c5fd">{len(watchlist)}</span>
  </div>
  <p style="color:#64748b;font-size:12px;margin-bottom:12px">
    Kurse werden live von Yahoo Finance abgerufen. Ticker im Format <strong style="color:#93c5fd">AIR.PA</strong> (europäisch) oder <strong style="color:#93c5fd">AAPL</strong> (US).
  </p>
  {watchlist_rows}
  <form method="post" action="/add_watchlist" style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px">
    <input type="text" name="w_name"       placeholder="Name (z.B. Airbus)" required>
    <input type="text" name="w_identifier" placeholder="WKN / ISIN (z.B. AIR.PA)">
    <input type="text" name="w_ticker"     placeholder="Yahoo Ticker (z.B. AIR.PA)" required>
    <input type="url"  name="w_finanzen"   placeholder="finanzen.net URL (optional)">
    <button type="submit" class="btn-primary" style="grid-column:1/-1;padding:12px">+ Zur Watchlist hinzufügen</button>
  </form>
  <div class="hint" style="margin-top:6px">Ticker-Suche: <a href="https://finance.yahoo.com/lookup" target="_blank" style="color:#60a5fa">finance.yahoo.com/lookup</a></div>

  <p style="color:#334155;font-size:11px;margin-top:32px;text-align:center">
    finance-news-agent · github.com/{GITHUB_REPO}
  </p>
</body>
</html>"""


# ── Server ────────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(render_page().encode("utf-8"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length).decode("utf-8")
        params = parse_qs(body)
        get    = lambda k, d="": params.get(k, [d])[0].strip()

        url      = get("url")
        domain   = get("domain").lower().lstrip("www.").rstrip("/")
        category = get("category")

        if self.path == "/add":
            msg, mt = (f"✓ Gespeichert: {url[:60]}", "success") if save_url(url) else ("Link bereits vorhanden oder ungültig.", "error")
        elif self.path == "/delete":
            delete_custom_url(url); msg, mt = "Gelöscht.", "success"
        elif self.path == "/block":
            msg, mt = (f"🚫 Ausgeschlossen: {domain}", "success") if save_blocked(domain) else (f"{domain} bereits vorhanden oder ungültig.", "error")
        elif self.path == "/unblock":
            delete_blocked(domain); msg, mt = f"✓ Freigegeben: {domain}", "success"
        elif self.path == "/add_feed":
            name, url2 = get("feed_name"), get("feed_url")
            msg, mt = (f"✓ Feed hinzugefügt: {name}", "success") if save_custom_feed(name, url2, category) else ("Feed bereits vorhanden oder Felder fehlen.", "error")
        elif self.path == "/delete_feed":
            delete_custom_feed(url, category); msg, mt = "Feed entfernt.", "success"
        elif self.path == "/add_watchlist":
            ok = add_watchlist_entry(get("w_name"), get("w_identifier"), get("w_ticker"), get("w_finanzen"))
            msg, mt = (f"✓ {get('w_name')} zur Watchlist hinzugefügt.", "success") if ok else ("Ticker bereits vorhanden.", "error")
        elif self.path == "/delete_watchlist":
            delete_watchlist_entry(get("ticker")); msg, mt = "Aus Watchlist entfernt.", "success"
        else:
            msg, mt = "", "success"

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(render_page(msg, mt).encode("utf-8"))


if __name__ == "__main__":
    ip = get_local_ip()
    print(f"\n📊  Finance News Agent — Quellen & Watchlist")
    print(f"    PC:    http://localhost:{PORT}")
    print(f"    Handy: http://{ip}:{PORT}  (gleiches WLAN)")
    print(f"\n    Strg+C zum Beenden\n")
    import webbrowser
    webbrowser.open(f"http://localhost:{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
