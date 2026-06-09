#!/usr/bin/env python3
"""
Finance News Agent — Agent-Ready Output
========================================
Liest RSS-Feeds, bewertet Meldungen auf Marktrelevanz,
extrahiert Entitäten (Unternehmen, Ticker, Indizes) und
clustert Themen. Output ist ein strukturiertes JSON-Schema,
das direkt von nachgelagerten Agenten konsumiert werden kann.

Setup:
    pip install anthropic feedparser requests

Verwendung:
    python finance_news_agent.py
    python finance_news_agent.py --output output/news_2026-06-09.json
    python finance_news_agent.py --threshold 7 --max-age 12

Cron (täglich 7:00, 12:00, 18:00 Uhr):
    0 7,12,18 * * * cd /pfad && python finance_news_agent.py --output /data/news_latest.json

Umgebungsvariable:
    export ANTHROPIC_API_KEY=sk-ant-...
"""

import os
import json
import uuid
import re
import argparse
import textwrap
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import anthropic
import feedparser
import requests

# ─────────────────────────────────────────────────────────────────────────────
# KONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

API_KEY            = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL              = "claude-haiku-4-5-20251001"   # günstig; für mehr Qualität: claude-sonnet-4-6
MAX_ITEMS_PER_FEED = 20
MAX_AGE_HOURS      = 24
RELEVANCE_THRESHOLD = 6
SCORE_BATCH_SIZE   = 40

RSS_FEEDS = [
    {"name": "Google News Finanzen",  "url": "https://news.google.com/rss/search?q=finanzen+aktien+börse&hl=de&gl=DE&ceid=DE:de"},
    {"name": "Google News Wirtschaft","url": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtUmxHZ0pFUlNnQVAB?hl=de&gl=DE&ceid=DE:de"},
    {"name": "FAZ Wirtschaft",     "url": "https://www.faz.net/rss/aktuell/wirtschaft/"},
    {"name": "FAZ Finanzen",       "url": "https://www.faz.net/rss/aktuell/finanzen/"},
    {"name": "WirtschaftsWoche",   "url": "https://www.wiwo.de/contentexport/feed/rss/schlagzeilen"},
    {"name": "NZZ Wirtschaft",     "url": "https://www.nzz.ch/wirtschaft.rss"},
    {"name": "NZZ Finanzen",       "url": "https://www.nzz.ch/finanzen.rss"},
    {"name": "WELT Wirtschaft",    "url": "https://www.welt.de/feeds/section/wirtschaft.rss"},
    {"name": "RND Wirtschaft",     "url": "https://www.rnd.de/arc/outboundfeeds/rss/category/wirtschaft/"},
    {"name": "RND Geld & Finanzen","url": "https://www.rnd.de/arc/outboundfeeds/rss/category/geld-und-finanzen/"},
]


# ─────────────────────────────────────────────────────────────────────────────
# SCHRITT 1 — RSS FEEDS ABRUFEN
# ─────────────────────────────────────────────────────────────────────────────

CUSTOM_URLS_FILE = "custom_urls.txt"

def fetch_custom_urls() -> list[dict]:
    if not os.path.exists(CUSTOM_URLS_FILE):
        return []
    articles = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    with open(CUSTOM_URLS_FILE, encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            # Titel aus <title>-Tag extrahieren
            title_match = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
            title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else url
            articles.append({
                "id":           str(uuid.uuid4())[:8],
                "source":       "Eigener Link",
                "title":        title[:200],
                "summary":      "",
                "url":          url,
                "published_at": datetime.now(timezone.utc).isoformat(),
            })
            print(f"  ✓  Eigener Link: {title[:60]}")
        except Exception as e:
            print(f"  ⚠  Eigener Link ({url[:50]}): {e}")
    return articles


def fetch_all_feeds(max_age_hours: int) -> list[dict]:
    all_articles = []
    now = datetime.now(timezone.utc)
    headers = {"User-Agent": "FinanceNewsAgent/2.0 (Python/feedparser)"}

    for source in RSS_FEEDS:
        try:
            resp = requests.get(source["url"], headers=headers, timeout=10)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as e:
            print(f"  ⚠  {source['name']}: {e}")
            continue

        count = 0
        for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
            pub = None
            for attr in ("published", "updated"):
                raw = getattr(entry, attr, None)
                if raw:
                    try:
                        pub = parsedate_to_datetime(raw)
                        if pub.tzinfo is None:
                            pub = pub.replace(tzinfo=timezone.utc)
                        break
                    except Exception:
                        pass

            if max_age_hours > 0 and pub:
                if (now - pub).total_seconds() / 3600 > max_age_hours:
                    continue

            title = entry.get("title", "").strip()
            if not title:
                continue

            summary = entry.get("summary", entry.get("description", "")).strip()
            summary = re.sub(r"<[^>]+>", " ", summary)
            summary = re.sub(r"\s+", " ", summary).strip()[:300]

            all_articles.append({
                "id":           str(uuid.uuid4())[:8],
                "source":       source["name"],
                "title":        title,
                "summary":      summary,
                "url":          entry.get("link", ""),
                "published_at": pub.isoformat() if pub else None,
            })
            count += 1

        print(f"  ✓  {source['name']}: {count} Einträge")

    seen, unique = set(), []
    for a in all_articles:
        key = a["title"].lower()[:60]
        if key not in seen:
            seen.add(key)
            unique.append(a)

    return unique


# ─────────────────────────────────────────────────────────────────────────────
# SCHRITT 2 — SCORING + ENTITY-EXTRAKTION
# ─────────────────────────────────────────────────────────────────────────────

def score_and_enrich(articles: list[dict], client: anthropic.Anthropic) -> list[dict]:
    if not articles:
        return []

    lines = []
    for i, a in enumerate(articles):
        lines.append(f"{i+1}. [{a['source']}] {a['title']}")
        if a["summary"]:
            lines.append(f"   {a['summary'][:200]}")

    prompt = textwrap.dedent(f"""
        Du bist ein Finanzmarkt-Analyst. Analysiere folgende Nachrichtenmeldungen
        für einen automatisierten Investment-Agenten.

        Antworte NUR mit einem JSON-Array. Ein Objekt pro Meldung:
        {{
          "id": <Nummer 1-N>,
          "score": <1-10>,
          "category": "<Aktien|Zinsen/EZB|Rohstoffe|M&A/IPO|Makro|Devisen|Krypto|Immobilien|Nicht relevant>",
          "reason": "<max 10 Wörter, deutsch>",
          "sentiment": "<positiv|negativ|neutral>",
          "action_hint": "<alert|watch|research|ignore>",
          "entities": {{
            "companies": ["<Firmenname>"],
            "tickers":   ["<TICKER.EXCHANGE>"],
            "indices":   ["<DAX|MDAX|S&P500|...>"],
            "assets":    ["<Gold|Öl|Bitcoin|EUR/USD|...>"]
          }}
        }}

        Score-Skala:
        9-10 = Marktbewegend, sofortige Auswirkung (Zinsänderung, Gewinnwarnung, Übernahme-Angebot)
        7-8  = Klar marktrelevant (Quartalszahlen, Konjunkturdaten, M&A-Gerüchte, wichtige Personalien)
        5-6  = Bedingt relevant (Hintergrundanalysen, mittelfristige Trends)
        1-4  = Kaum/nicht relevant für Finanzmarkt-Investoren

        action_hint-Logik:
        - alert    = Score ≥ 8, sofortiger Handlungsbedarf
        - watch    = Score 6-7, beobachten
        - research = Score 5, vertiefte Analyse sinnvoll
        - ignore   = Score ≤ 4

        Tickers im Format SYMBOL.EXCHANGE (z.B. CBK.DE, AAPL.US, UCG.MI).
        Wenn kein Ticker bekannt: leere Liste.

        Meldungen:
        {chr(10).join(lines)}

        Antworte ausschließlich mit dem JSON-Array, kein weiterer Text, keine Codeblöcke.
    """).strip()

    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        scores = {int(s["id"]): s for s in json.loads(raw)}

        for i, article in enumerate(articles):
            s = scores.get(i + 1, {})
            article["score"]       = int(s.get("score", 0))
            article["category"]    = s.get("category", "Unbekannt")
            article["reason"]      = s.get("reason", "")
            article["sentiment"]   = s.get("sentiment", "neutral")
            article["action_hint"] = s.get("action_hint", "ignore")
            article["entities"]    = s.get("entities", {
                "companies": [], "tickers": [], "indices": [], "assets": []
            })

    except Exception as e:
        print(f"  ⚠  Scoring-Fehler: {e}")
        for article in articles:
            article.update({"score": 0, "category": "Fehler", "reason": str(e),
                            "sentiment": "neutral", "action_hint": "ignore",
                            "entities": {"companies": [], "tickers": [], "indices": [], "assets": []}})

    return articles


# ─────────────────────────────────────────────────────────────────────────────
# SCHRITT 3 — THEMEN-CLUSTERING
# ─────────────────────────────────────────────────────────────────────────────

def cluster_themes(relevant: list[dict], client: anthropic.Anthropic) -> list[dict]:
    if not relevant:
        return []

    lines = [f"{a['id']}|{a['title']}" for a in relevant]

    prompt = textwrap.dedent(f"""
        Fasse folgende Finanznachrichten-Schlagzeilen zu übergeordneten Themen zusammen.
        Format: ID|Titel

        {chr(10).join(lines)}

        Antworte NUR mit einem JSON-Array von Themen-Objekten:
        {{
          "theme": "<prägnanter Thementitel, max 5 Wörter>",
          "urgency": "<hoch|mittel|niedrig>",
          "summary": "<1 Satz, was das Thema bedeutet>",
          "article_ids": ["<id1>", "<id2>"]
        }}

        Regeln:
        - Mindestens 2 Artikel für ein Thema (Einzelmeldungen weglassen)
        - Maximal 8 Themen
        - Sortiert nach Urgency (hoch → niedrig)
        - Kein weiterer Text, keine Codeblöcke
    """).strip()

    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"  ⚠  Clustering-Fehler: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# SCHRITT 4 — STRUKTURIERTER JSON-OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

def build_html(output: dict) -> str:
    meta = output["meta"]
    themes = output["top_themes"]
    articles = output["articles"]
    entity = output["entity_universe"]

    urgency_color = {"hoch": "#ef4444", "mittel": "#f59e0b", "niedrig": "#22c55e"}
    action_badge = {
        "alert":    ("#ef4444", "🔔 Alert"),
        "watch":    ("#f59e0b", "👀 Watch"),
        "research": ("#3b82f6", "🔍 Research"),
        "ignore":   ("#6b7280", "ignore"),
    }
    sentiment_icon = {"positiv": "🟢", "negativ": "🔴", "neutral": "⚪"}

    theme_cards = ""
    for t in themes:
        color = urgency_color.get(t["urgency"], "#6b7280")
        theme_cards += f"""
        <div style="border-left:4px solid {color};padding:12px 16px;background:#1e293b;border-radius:6px">
          <div style="font-weight:600;font-size:15px">{t["theme"]}</div>
          <div style="color:#94a3b8;font-size:13px;margin-top:4px">{t["summary"]}</div>
          <div style="color:{color};font-size:12px;margin-top:6px">{t["urgency"].upper()} · {len(t["article_ids"])} Artikel</div>
        </div>"""

    sorted_articles = sorted(articles, key=lambda x: -x.get("score", 0))
    article_rows = ""
    for a in sorted_articles:
        color, label = action_badge.get(a["action_hint"], ("#6b7280", a["action_hint"]))
        s_icon = sentiment_icon.get(a["sentiment"], "⚪")
        tickers = ", ".join(a["entities"].get("tickers", [])) or "–"
        pub = (a["published_at"] or "")[:16].replace("T", " ")
        score_color = '#ef4444' if a['score'] >= 8 else '#f59e0b' if a['score'] >= 6 else '#94a3b8'
        url = a["url"] or "#"
        article_rows += f"""
        <tr onclick="window.open('{url}','_blank')" style="cursor:pointer" title="Artikel öffnen">
          <td style="padding:10px 8px;font-size:13px;font-weight:500">{a["title"]}</td>
          <td style="padding:10px 8px;color:#94a3b8;font-size:12px">{a["source"]}</td>
          <td style="padding:10px 8px;text-align:center;font-size:14px;font-weight:700;color:{score_color}">{a["score"]}</td>
          <td style="padding:10px 8px"><span style="background:{color}22;color:{color};padding:2px 8px;border-radius:12px;font-size:12px">{label}</span></td>
          <td style="padding:10px 8px;font-size:12px;color:#94a3b8">{a["category"]}</td>
          <td style="padding:10px 8px;text-align:center">{s_icon}</td>
          <td style="padding:10px 8px;color:#60a5fa;font-size:12px">{tickers}</td>
          <td style="padding:10px 8px;color:#64748b;font-size:11px">{pub}</td>
        </tr>"""

    ticker_pills = "".join(
        f'<span style="background:#1e3a5f;color:#93c5fd;padding:3px 10px;border-radius:12px;font-size:12px">{t}</span> '
        for t in entity["tickers"]
    ) or "<span style='color:#64748b'>–</span>"

    generated = meta["generated_at"][:16].replace("T", " ")

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Finance News Agent</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0 }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #0f172a; color: #e2e8f0; padding: 32px }}
  h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 4px }}
  h2 {{ font-size: 14px; font-weight: 600; text-transform: uppercase;
        letter-spacing: .08em; color: #64748b; margin-bottom: 12px }}
  .grid {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 32px }}
  .card {{ background: #1e293b; border-radius: 10px; padding: 16px }}
  .card .val {{ font-size: 28px; font-weight: 700 }}
  .card .lbl {{ font-size: 12px; color: #64748b; margin-top: 4px }}
  .themes {{ display: grid; grid-template-columns: repeat(auto-fill,minmax(300px,1fr));
             gap: 12px; margin-bottom: 32px }}
  table {{ width: 100%; border-collapse: collapse }}
  tr:hover td {{ background: #1e293b }}
  th {{ text-align: left; padding: 8px; font-size: 12px; color: #64748b;
        border-bottom: 1px solid #1e293b; font-weight: 500 }}
  td {{ border-bottom: 1px solid #0f172a }}
</style>
</head>
<body>
<div style="display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:24px">
  <div>
    <h1>📈 Finance News Agent</h1>
    <div style="color:#64748b;font-size:13px;margin-top:4px">Erstellt: {generated} · Modell: {meta["model"]}</div>
  </div>
</div>

<div class="grid">
  <div class="card"><div class="val">{meta["total_fetched"]}</div><div class="lbl">Artikel abgerufen</div></div>
  <div class="card"><div class="val" style="color:#22c55e">{meta["total_relevant"]}</div><div class="lbl">Relevant (Score ≥ {meta["threshold"]})</div></div>
  <div class="card"><div class="val" style="color:#ef4444">{meta["action_summary"]["alert"]}</div><div class="lbl">🔔 Alert</div></div>
  <div class="card"><div class="val" style="color:#f59e0b">{meta["action_summary"]["watch"]}</div><div class="lbl">👀 Watch</div></div>
</div>

<h2>Top-Themen</h2>
<div class="themes">{theme_cards}</div>

<h2 style="margin-bottom:8px">Ticker im Fokus</h2>
<div style="margin-bottom:28px;display:flex;flex-wrap:wrap;gap:6px">{ticker_pills}</div>

<h2>Alle relevanten Artikel</h2>
<table>
  <thead>
    <tr>
      <th>Titel</th><th>Quelle</th><th>Score</th><th>Aktion</th>
      <th>Kategorie</th><th>Sentiment</th><th>Ticker</th><th>Zeit</th><th></th>
    </tr>
  </thead>
  <tbody>{article_rows}</tbody>
</table>
</body>
</html>"""


def build_output(relevant: list[dict], themes: list[dict],
                 total_fetched: int, period_from: str, period_to: str,
                 threshold: int) -> dict:
    all_companies = sorted({c for a in relevant for c in a["entities"].get("companies", [])})
    all_tickers   = sorted({t for a in relevant for t in a["entities"].get("tickers", [])})
    all_indices   = sorted({i for a in relevant for i in a["entities"].get("indices", [])})

    score_dist = {"alert": 0, "watch": 0, "research": 0, "ignore": 0}
    for a in relevant:
        key = a.get("action_hint", "ignore")
        score_dist[key] = score_dist.get(key, 0) + 1

    return {
        "schema_version": "2.0",
        "meta": {
            "generated_at":   period_to,
            "period_from":    period_from,
            "period_to":      period_to,
            "total_fetched":  total_fetched,
            "total_relevant": len(relevant),
            "threshold":      threshold,
            "model":          MODEL,
            "sources":        [s["name"] for s in RSS_FEEDS],
            "action_summary": score_dist,
        },
        "entity_universe": {
            "companies": all_companies,
            "tickers":   all_tickers,
            "indices":   all_indices,
        },
        "top_themes": themes,
        "articles": [
            {
                "id":           a["id"],
                "title":        a["title"],
                "source":       a["source"],
                "url":          a["url"],
                "published_at": a["published_at"],
                "score":        a["score"],
                "category":     a["category"],
                "reason":       a["reason"],
                "sentiment":    a["sentiment"],
                "action_hint":  a["action_hint"],
                "entities":     a["entities"],
            }
            for a in relevant
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# HAUPTPROGRAMM
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Finance News Agent – Agent-Ready JSON Output")
    parser.add_argument("--output",    default=None,
                        help="Ausgabepfad für JSON (Standard: Konsole)")
    parser.add_argument("--threshold", type=int, default=RELEVANCE_THRESHOLD,
                        help=f"Mindest-Score 1-10 (Standard: {RELEVANCE_THRESHOLD})")
    parser.add_argument("--max-age",   type=int, default=MAX_AGE_HOURS,
                        help=f"Maximales Alter in Stunden (Standard: {MAX_AGE_HOURS})")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Nur Feeds abrufen, kein Claude-API-Aufruf (zum Testen)")
    parser.add_argument("--html",      default=None,
                        help="Zusätzlich eine HTML-Übersicht speichern (z.B. output/report.html)")
    args = parser.parse_args()

    if not args.dry_run and not API_KEY:
        print("❌  ANTHROPIC_API_KEY nicht gesetzt.")
        return

    client = anthropic.Anthropic(api_key=API_KEY) if not args.dry_run else None
    period_from = datetime.now(timezone.utc).isoformat()

    print(f"\n🔄  Lese {len(RSS_FEEDS)} RSS-Feeds …")
    articles = fetch_all_feeds(args.max_age)
    custom = fetch_custom_urls()
    if custom:
        print(f"  ✚  {len(custom)} eigene Links aus {CUSTOM_URLS_FILE}")
        articles = custom + articles
    print(f"    → {len(articles)} Artikel nach Deduplizierung\n")

    if args.dry_run:
        print("🧪  Dry-run: kein API-Aufruf. Feeds erfolgreich abgerufen.")
        return

    print(f"🤖  Scoring & Entity-Extraktion ({MODEL}) …")
    enriched = []
    for i in range(0, len(articles), SCORE_BATCH_SIZE):
        batch = articles[i:i + SCORE_BATCH_SIZE]
        print(f"    Batch {i // SCORE_BATCH_SIZE + 1}/{-(-len(articles) // SCORE_BATCH_SIZE)}: {len(batch)} Artikel")
        enriched.extend(score_and_enrich(batch, client))

    relevant = sorted(
        [a for a in enriched if a.get("score", 0) >= args.threshold],
        key=lambda x: -x["score"]
    )
    print(f"\n✅  {len(relevant)} relevante Artikel (Score ≥ {args.threshold})\n")

    print("🗂️   Themen-Clustering …")
    themes = cluster_themes(relevant, client)
    print(f"    → {len(themes)} Themen identifiziert\n")

    period_to = datetime.now(timezone.utc).isoformat()
    output = build_output(relevant, themes, len(articles), period_from, period_to, args.threshold)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"💾  Gespeichert: {args.output}")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))

    if args.html:
        html_path = args.html
        os.makedirs(os.path.dirname(html_path) or ".", exist_ok=True)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(build_html(output))
        print(f"🌐  HTML-Report: {html_path}")
        import webbrowser
        webbrowser.open(html_path)

    print(f"\n{'─'*60}")
    print(f"  🔔 Alert:    {output['meta']['action_summary']['alert']} Meldungen")
    print(f"  👀 Watch:    {output['meta']['action_summary']['watch']} Meldungen")
    print(f"  🔍 Research: {output['meta']['action_summary']['research']} Meldungen")
    print(f"  📌 Ticker:   {', '.join(output['entity_universe']['tickers'][:10]) or '–'}")
    if themes:
        print(f"\n  Top-Themen:")
        for t in themes[:5]:
            icon = {"hoch": "🔴", "mittel": "🟡", "niedrig": "🟢"}.get(t["urgency"], "⚪")
            print(f"    {icon} {t['theme']} ({len(t['article_ids'])} Artikel)")
    print(f"{'─'*60}\n")


if __name__ == "__main__":
    main()
