"""
LuckyCombi — Flask API
======================
Render-ready (no --host flag needed on cloud).
Auto-scrapes PCSO on startup + every 24h.
Falls back to seeded data if PCSO is unreachable.

Endpoints:
  GET  /api/games
  GET  /api/draws?game=6/49&from=YYYY-MM-DD&to=YYYY-MM-DD&limit=200
  GET  /api/generate?game=6/49
  POST /api/check-ticket  { game, draw_date?, bets: [[n,n,n,n,n,n]] }
  POST /api/refresh        — manually trigger a PCSO scrape

Deploy to Render:
  1. Push to GitHub
  2. New Web Service → connect repo
  3. Build command:  pip install -r requirements.txt
  4. Start command:  python api.py
  5. Done — copy the https://xxx.onrender.com URL
"""

import os
import json
import random
import sqlite3
import threading
import time
import re
import sys
import time as _time_mod
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS

# ── Try to import scraping libs (optional — graceful fallback if missing) ──
try:
    import requests as req_lib
    from bs4 import BeautifulSoup
    SCRAPER_AVAILABLE = True
except ImportError:
    SCRAPER_AVAILABLE = False
    print("⚠  requests/bs4 not installed — scraper disabled, using seeded data only")

app = Flask(__name__)
CORS(app, origins="*")

DB_PATH = os.environ.get("DB_PATH", "luckycombi.db")

# ── Seeded fallback draws (Feb–May 2026) ──────────────────────────────────────
SEED_DRAWS = [
    ("6/58","2026-05-21",[6,9,14,26,38,48],75000000,0),
    ("6/49","2026-05-21",[2,9,21,23,28,37],25000000,0),
    ("6/42","2026-05-21",[5,8,17,18,33,41],20654909,0),
    ("6/55","2026-05-20",[8,9,10,27,41,45],115358791,1),
    ("6/45","2026-05-20",[11,16,23,32,37,45],18546872,0),
    ("6/58","2026-05-19",[6,9,14,26,38,48],75000000,0),
    ("6/49","2026-05-19",[4,5,14,35,44,49],25000000,0),
    ("6/42","2026-05-19",[6,15,16,22,25,31],17376838,0),
    ("6/55","2026-05-17",[3,7,19,22,41,55],98000000,0),
    ("6/45","2026-05-17",[3,6,12,18,29,44],16200000,0),
    ("6/58","2026-05-16",[5,11,23,33,40,57],63000000,0),
    ("6/49","2026-05-15",[1,12,19,31,42,47],25000000,0),
    ("6/42","2026-05-15",[3,11,20,27,34,39],16100000,0),
    ("6/55","2026-05-14",[4,15,22,33,48,52],89000000,0),
    ("6/45","2026-05-14",[7,14,21,28,35,42],15800000,0),
    ("6/58","2026-05-13",[2,18,27,36,45,54],58000000,0),
    ("6/49","2026-05-13",[5,16,23,30,37,44],25000000,0),
    ("6/42","2026-05-13",[1,8,15,22,29,36],15500000,0),
    ("6/55","2026-05-12",[6,12,24,36,48,54],80000000,0),
    ("6/45","2026-05-12",[3,9,18,27,36,45],15200000,0),
    ("6/58","2026-05-09",[7,14,21,35,49,56],52000000,0),
    ("6/49","2026-05-08",[8,17,26,35,44,49],25000000,0),
    ("6/42","2026-05-08",[2,9,16,23,30,37],14800000,0),
    ("6/55","2026-05-07",[5,11,22,33,44,55],72000000,0),
    ("6/45","2026-05-07",[4,13,22,31,40,45],14500000,0),
    ("6/58","2026-05-06",[3,12,21,30,39,48],48000000,0),
    ("6/49","2026-05-06",[6,15,24,33,42,48],25000000,0),
    ("6/42","2026-05-06",[4,11,18,25,32,39],14200000,0),
    ("6/55","2026-05-05",[2,14,26,38,50,53],65000000,0),
    ("6/45","2026-05-05",[5,10,20,30,40,44],14000000,0),
    ("6/58","2026-05-02",[9,18,27,36,45,54],44000000,0),
    ("6/49","2026-05-01",[3,14,25,36,47,49],25000000,0),
    ("6/42","2026-05-01",[6,13,20,27,34,41],13600000,0),
    ("6/55","2026-04-30",[1,11,21,31,41,51],58000000,0),
    ("6/45","2026-04-30",[2,12,22,32,42,45],13300000,0),
    ("6/58","2026-04-29",[4,13,22,31,40,49],40000000,0),
    ("6/49","2026-04-29",[7,16,25,34,43,49],25000000,0),
    ("6/42","2026-04-29",[1,8,19,28,35,42],13000000,0),
    ("6/55","2026-04-28",[3,13,23,33,43,53],52000000,0),
    ("6/45","2026-04-28",[6,11,23,31,38,44],12700000,0),
    ("6/58","2026-04-26",[5,15,25,35,45,55],36000000,0),
    ("6/49","2026-04-24",[2,13,24,35,46,49],25000000,0),
    ("6/42","2026-04-24",[3,10,17,24,31,38],12400000,0),
    ("6/55","2026-04-23",[7,17,27,37,47,54],47000000,0),
    ("6/45","2026-04-23",[1,9,19,29,39,43],12100000,0),
    ("6/58","2026-04-22",[8,16,24,32,40,48],32000000,0),
    ("6/49","2026-04-22",[4,15,26,37,48,49],25000000,0),
    ("6/42","2026-04-22",[5,12,19,26,33,40],11800000,0),
    ("6/55","2026-04-21",[2,12,22,32,42,52],42000000,0),
    ("6/45","2026-04-21",[4,14,24,34,44,45],11500000,0),
    ("6/58","2026-04-19",[6,16,26,36,46,56],28000000,0),
    ("6/49","2026-04-17",[1,10,21,32,43,49],25000000,0),
    ("6/42","2026-04-17",[2,11,20,29,38,41],11200000,0),
    ("6/55","2026-04-16",[5,15,25,35,45,55],38000000,0),
    ("6/45","2026-04-16",[3,13,23,33,43,44],11000000,0),
    ("6/58","2026-04-15",[4,14,24,34,44,54],25000000,0),
    ("6/49","2026-04-15",[6,17,28,39,45,49],25000000,0),
    ("6/42","2026-04-15",[7,14,21,28,35,42],10700000,0),
    ("6/55","2026-04-14",[1,13,25,37,49,54],34000000,0),
    ("6/45","2026-04-14",[5,15,25,35,45,43],10400000,0),
    ("6/58","2026-04-12",[3,11,19,27,35,43],22000000,0),
    ("6/49","2026-04-10",[8,19,30,41,47,49],25000000,0),
    ("6/42","2026-04-10",[4,11,18,25,32,40],10100000,0),
    ("6/55","2026-04-09",[6,16,26,36,46,53],30000000,0),
    ("6/45","2026-04-09",[2,12,22,32,42,44],9800000,0),
    ("6/58","2026-04-08",[9,19,29,39,49,57],19000000,0),
    ("6/49","2026-04-08",[3,12,23,34,45,49],25000000,0),
    ("6/42","2026-04-08",[1,10,19,28,37,41],9500000,0),
    ("6/55","2026-04-07",[4,14,24,34,44,51],27000000,0),
    ("6/45","2026-04-07",[7,17,27,37,43,45],9200000,0),
    ("6/58","2026-04-05",[2,10,18,26,34,42],16000000,0),
    ("6/49","2026-04-03",[5,14,23,32,41,48],25000000,0),
    ("6/42","2026-04-03",[3,12,21,30,39,42],8900000,0),
    ("6/55","2026-04-02",[8,18,28,38,48,53],24000000,0),
    ("6/45","2026-04-02",[1,11,21,31,41,43],8600000,0),
    ("6/58","2026-04-01",[7,15,23,31,39,47],14000000,0),
    ("6/49","2026-04-01",[2,11,22,33,44,49],25000000,0),
    ("6/42","2026-04-01",[5,14,23,32,41,42],8300000,0),
    ("6/55","2026-03-30",[3,13,23,33,43,50],21000000,0),
    ("6/45","2026-03-30",[6,16,26,36,44,45],8000000,0),
    ("6/58","2026-03-28",[4,12,20,28,36,44],12000000,0),
    ("6/49","2026-03-27",[7,18,29,40,46,49],25000000,0),
    ("6/42","2026-03-27",[2,9,16,23,30,38],7700000,0),
    ("6/55","2026-03-26",[5,15,25,35,45,52],19000000,0),
    ("6/45","2026-03-26",[3,13,23,33,43,44],7400000,0),
    ("6/58","2026-03-25",[6,14,22,30,38,46],10000000,0),
    ("6/49","2026-03-25",[1,12,23,34,45,48],25000000,0),
    ("6/42","2026-03-25",[4,13,22,31,40,42],7100000,0),
    ("6/55","2026-03-23",[2,14,26,38,50,54],17000000,0),
    ("6/45","2026-03-23",[5,15,25,35,41,45],6800000,0),
    ("6/58","2026-03-21",[8,17,26,35,44,53],75000000,1),
    ("6/49","2026-03-20",[3,14,25,36,47,48],25000000,0),
    ("6/42","2026-03-20",[6,15,24,33,42,41],6500000,0),
    ("6/55","2026-03-19",[1,11,21,31,41,51],16000000,0),
    ("6/45","2026-03-19",[4,12,24,32,40,43],6200000,0),
    ("6/58","2026-03-18",[5,13,21,29,37,45],16000000,0),
    ("6/49","2026-03-18",[6,17,28,39,46,49],25000000,0),
    ("6/42","2026-03-18",[1,8,17,26,35,40],5900000,0),
    ("6/55","2026-03-16",[7,17,27,37,47,53],15000000,0),
    ("6/45","2026-03-16",[2,12,22,32,42,44],5600000,0),
    ("6/58","2026-03-14",[3,11,19,27,35,51],14000000,0),
    ("6/49","2026-03-13",[8,19,30,41,47,49],25000000,0),
    ("6/42","2026-03-13",[3,10,17,24,31,39],5300000,0),
    ("6/55","2026-03-12",[4,16,28,40,52,55],14000000,0),
    ("6/45","2026-03-12",[7,14,21,28,35,43],5000000,0),
    ("6/58","2026-03-11",[6,16,26,36,46,56],13000000,0),
    ("6/49","2026-03-11",[2,13,24,35,46,49],25000000,0),
    ("6/42","2026-03-11",[5,12,19,26,33,41],4700000,0),
    ("6/55","2026-03-09",[3,15,27,39,51,54],13000000,0),
    ("6/45","2026-03-09",[1,11,21,31,41,42],4400000,0),
    ("6/58","2026-03-07",[9,18,27,36,45,54],12000000,0),
    ("6/49","2026-03-06",[4,15,26,37,48,49],25000000,0),
    ("6/42","2026-03-06",[2,11,20,29,38,40],4100000,0),
    ("6/55","2026-03-05",[5,17,29,41,53,55],12000000,0),
    ("6/45","2026-03-05",[3,13,23,33,43,44],3800000,0),
    ("6/58","2026-03-04",[4,14,24,34,44,52],11000000,0),
    ("6/49","2026-03-04",[7,16,25,34,43,49],25000000,0),
    ("6/42","2026-03-04",[4,13,22,31,40,42],3500000,0),
    ("6/55","2026-03-02",[2,12,22,32,42,52],11000000,0),
    ("6/45","2026-03-02",[5,15,25,35,45,43],3200000,0),
    ("6/58","2026-02-28",[7,15,23,31,39,47],10000000,0),
    ("6/49","2026-02-27",[1,10,21,32,43,47],25000000,0),
    ("6/42","2026-02-27",[6,15,24,33,42,41],2900000,0),
    ("6/55","2026-02-26",[8,18,28,38,48,53],10000000,0),
    ("6/45","2026-02-26",[2,12,22,32,42,44],2600000,0),
    ("6/58","2026-02-25",[6,14,22,30,38,50],9000000,0),
    ("6/49","2026-02-25",[3,12,23,34,45,49],25000000,0),
    ("6/42","2026-02-25",[1,8,15,22,29,37],2300000,0),
    ("6/55","2026-02-23",[6,16,26,36,46,54],9000000,0),
    ("6/45","2026-02-23",[4,14,24,34,44,45],2000000,0),
]

# PCSO game name → our short label
GAME_MAP = {
    "ultra lotto 6/58": "6/58",
    "grand lotto 6/55": "6/55",
    "superlotto 6/49": "6/49",
    "megalotto 6/45": "6/45",
    "lotto 6/42": "6/42",
}

# ── Database helpers ──────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lotto_draws (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            game        TEXT    NOT NULL,
            draw_date   TEXT    NOT NULL,
            combination TEXT    NOT NULL,
            jackpot     REAL,
            winners     INTEGER DEFAULT 0,
            scraped_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(game, draw_date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()

def seed_if_empty():
    """Seed with fallback data only if DB has no rows."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM lotto_draws").fetchone()[0]
    if count == 0:
        print("  Seeding DB with fallback data...")
        for game, date, combo, jackpot, winners in SEED_DRAWS:
            conn.execute(
                "INSERT OR IGNORE INTO lotto_draws (game,draw_date,combination,jackpot,winners) VALUES(?,?,?,?,?)",
                (game, date, json.dumps(sorted(combo)), jackpot, winners)
            )
        conn.commit()
        print(f"  Seeded {len(SEED_DRAWS)} rows.")
    conn.close()

def upsert_draw(conn, game, draw_date, combo, jackpot, winners):
    conn.execute("""
        INSERT OR REPLACE INTO lotto_draws (game, draw_date, combination, jackpot, winners)
        VALUES (?, ?, ?, ?, ?)
    """, (game, draw_date, json.dumps(sorted(combo)), jackpot, winners))

def get_last_scrape_time():
    conn = get_db()
    row = conn.execute("SELECT value FROM meta WHERE key='last_scrape'").fetchone()
    conn.close()
    return row["value"] if row else None

def set_last_scrape_time(ts):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO meta (key,value) VALUES ('last_scrape',?)", (ts,))
    conn.commit()
    conn.close()

# ── PCSO Scraper ──────────────────────────────────────────────────────────────
HEADERS_SCRAPE = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.lottopcso.com/",
}

HISTORY_URLS = {
    "6/42": "https://www.lottopcso.com/6-42-lotto-result-history-and-summary/",
    "6/45": "https://www.lottopcso.com/6-45-lotto-result-history-and-summary/",
    "6/49": "https://www.lottopcso.com/6-49-lotto-result-history-and-summary/",
    "6/55": "https://www.lottopcso.com/6-55-lotto-result-history-and-summary/",
    "6/58": "https://www.lottopcso.com/6-58-lotto-result-history-and-summary/",
}
TODAY_URL = "https://www.lottopcso.com/lotto-result-today-pcso-daily-draw-summary/"

def _parse_combo(text):
    nums = [int(n) for n in re.findall(r'\d+', text) if 1 <= int(n) <= 58]
    return nums if len(nums) == 6 else None

def _parse_jackpot(text):
    clean = re.sub(r'[^\d.]', '', text.replace(',', ''))
    try:
        v = float(clean); return v if v > 0 else None
    except ValueError:
        return None

def _parse_date_lotto(text):
    text = text.strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%b. %d, %Y"):
        try: return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError: continue
    return None

def _scrape_today(session):
    """Scrape today's 6-ball results from lottopcso.com summary page."""
    if not SCRAPER_AVAILABLE:
        return []
    try:
        resp = session.get(TODAY_URL, headers=HEADERS_SCRAPE, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ✗ today page failed: {e}"); return []

    soup = BeautifulSoup(resp.text, "lxml")
    results = []
    GAME_LABELS = {
        "6/58 ultra lotto":"6/58","ultra lotto 6/58":"6/58",
        "6/55 grand lotto":"6/55","grand lotto 6/55":"6/55",
        "6/49 super lotto":"6/49","super lotto 6/49":"6/49",
        "6/45 mega lotto":"6/45","mega lotto 6/45":"6/45",
        "6/42 lotto":"6/42","lotto 6/42":"6/42",
    }
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2: continue
        hdr = " ".join(td.get_text(strip=True).lower() for td in rows[0].find_all(["td","th"]))
        game = next((v for k,v in GAME_LABELS.items() if k in hdr), None)
        if not game: continue
        draw_date = next((
            _parse_date_lotto(td.get_text(strip=True))
            for td in rows[0].find_all(["td","th"])
            if _parse_date_lotto(td.get_text(strip=True))
        ), None)
        for row in rows[1:]:
            cells = [td.get_text(separator=" ", strip=True) for td in row.find_all(["td","th"])]
            for i, cell in enumerate(cells):
                if "winning combination" in cell.lower() and i+1 < len(cells):
                    combo = _parse_combo(cells[i+1])
                    if combo and draw_date:
                        jackpot = None
                        for r2 in rows[1:]:
                            c2 = [td.get_text(separator=" ", strip=True) for td in r2.find_all(["td","th"])]
                            if any("jackpot prize" in c.lower() for c in c2):
                                for c in c2:
                                    j = _parse_jackpot(c)
                                    if j and j > 1000: jackpot=j; break
                        results.append((game, draw_date, combo, jackpot, 0))
                    break
    seen=set(); unique=[]
    for r in results:
        k=(r[0],r[1])
        if k not in seen: seen.add(k); unique.append(r)
    print(f"  ✓ Today's page: {len(unique)} 6-ball draws")
    return unique

def _scrape_history(game, url, cutoff, session):
    """Scrape one game's history page from lottopcso.com."""
    if not SCRAPER_AVAILABLE:
        return []
    try:
        resp = session.get(url, headers=HEADERS_SCRAPE, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ✗ {game} history failed: {e}"); return []
    soup = BeautifulSoup(resp.text, "lxml")
    results = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [td.get_text(separator=" ", strip=True) for td in row.find_all(["td","th"])]
            if len(cells) < 2: continue
            if any(h in cells[0].lower() for h in ["draw date","date","game"]): continue
            draw_date = _parse_date_lotto(cells[0])
            if not draw_date: continue
            if cutoff and draw_date < cutoff: continue
            combo = _parse_combo(cells[1]) if len(cells)>1 else None
            if not combo: continue
            jackpot = _parse_jackpot(cells[2]) if len(cells)>2 else None
            results.append((game, draw_date, combo, jackpot, 0))
    print(f"  ✓ {game}: {len(results)} rows from history page")
    return results

def _scrape_pcso_official(days_back, session):
    """Fallback: official PCSO site with VIEWSTATE handling."""
    if not SCRAPER_AVAILABLE:
        return []
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days_back)
    print(f"  → PCSO official fallback ({from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')})…")
    try:
        h = {**HEADERS_SCRAPE, "Referer": "https://www.pcso.gov.ph/"}
        resp = session.get("https://www.pcso.gov.ph/SearchLottoResult.aspx", headers=h, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        def hv(n):
            el = soup.find("input", {"name": n}); return el["value"] if el and el.get("value") else ""
        payload = {
            "__EVENTTARGET":"","__EVENTARGUMENT":"",
            "__VIEWSTATE": hv("__VIEWSTATE"),
            "__VIEWSTATEGENERATOR": hv("__VIEWSTATEGENERATOR"),
            "__EVENTVALIDATION": hv("__EVENTVALIDATION"),
            "ctl00$cphContainer$ddlStartMonth": str(from_date.month),
            "ctl00$cphContainer$ddlStartDay":   str(from_date.day),
            "ctl00$cphContainer$ddlStartYear":  str(from_date.year),
            "ctl00$cphContainer$ddlEndMonth":   str(to_date.month),
            "ctl00$cphContainer$ddlEndDay":     str(to_date.day),
            "ctl00$cphContainer$ddlEndYear":    str(to_date.year),
            "ctl00$cphContainer$ddlSelectGame": "0",
            "ctl00$cphContainer$btnSearch":     "Search Lotto",
        }
        time.sleep(1)
        resp2 = session.post("https://www.pcso.gov.ph/SearchLottoResult.aspx",
                             data=payload, headers={**h,"Referer":"https://www.pcso.gov.ph/SearchLottoResult.aspx"}, timeout=30)
        resp2.raise_for_status()
        soup2 = BeautifulSoup(resp2.text, "lxml")
        table = next((t for t in soup2.find_all("table") if "COMBINATIONS" in t.get_text()), None)
        if not table:
            print("  ✗ PCSO official: table not found"); return []
        results = []
        for row in table.find_all("tr")[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < 5: continue
            game = next((v for k,v in GAME_MAP.items() if k in cells[0].lower()), None)
            if not game: continue
            combo = _parse_combo(cells[1])
            if not combo: continue
            try: draw_date = datetime.strptime(cells[2].strip(),"%m/%d/%Y").strftime("%Y-%m-%d")
            except ValueError: continue
            jackpot = _parse_jackpot(cells[3])
            try: winners = int(re.sub(r'[^\d]','',cells[4]) or "0")
            except: winners = 0
            results.append((game, draw_date, combo, jackpot, winners))
        print(f"  ✓ PCSO official: {len(results)} rows")
        return results
    except Exception as e:
        print(f"  ✗ PCSO official failed: {e}"); return []

def run_scrape_and_save():
    """
    Dual-source scrape:
      1. lottopcso.com today page  (always fast)
      2. lottopcso.com history pages per game
      3. pcso.gov.ph official (fallback if above returns nothing)
    Returns count of new rows inserted.
    """
    if not SCRAPER_AVAILABLE:
        return 0

    import time as _time
    session = req_lib.Session()
    all_rows = []
    cutoff = (datetime.now() - timedelta(days=35)).strftime("%Y-%m-%d")

    # Step 1 — today
    all_rows.extend(_scrape_today(session))

    # Step 2 — history pages
    for game, url in HISTORY_URLS.items():
        all_rows.extend(_scrape_history(game, url, cutoff, session))
        _time.sleep(0.4)

    # Step 3 — fallback
    if not all_rows:
        print("  ⚠ lottopcso.com returned nothing — trying PCSO official…")
        all_rows = _scrape_pcso_official(35, session)

    if not all_rows:
        print("  ✗ All sources failed. DB unchanged.")
        return 0

    inserted = 0
    seen = set()
    conn = get_db()
    for game, draw_date, combo, jackpot, winners in all_rows:
        k = (game, draw_date)
        if k in seen: continue
        seen.add(k)
        cur = conn.execute(
            "INSERT OR IGNORE INTO lotto_draws (game,draw_date,combination,jackpot,winners) VALUES(?,?,?,?,?)",
            (game, draw_date, json.dumps(sorted(combo)), jackpot, winners)
        )
        if cur.rowcount > 0:
            inserted += 1
    conn.commit()
    conn.close()
    set_last_scrape_time(datetime.now().isoformat())
    print(f"  ✓ Saved {inserted} new draws to DB")
    return inserted

# ── Background auto-refresh (every 24h) ──────────────────────────────────────
def auto_refresh_loop():
    while True:
        time.sleep(86400)  # 24 hours
        print("  ⏰ Auto-refresh: scraping PCSO...")
        run_scrape_and_save()

# ── Pattern engine ────────────────────────────────────────────────────────────
def generate_combos(game, draws):
    pools = {"6/42": 42, "6/45": 45, "6/49": 49, "6/55": 55, "6/58": 58}
    pool = pools.get(game, 49)

    all_nums = []
    for d in draws:
        combo = d["combination"] if isinstance(d["combination"], list) else json.loads(d["combination"])
        all_nums.extend(combo)

    # Frequency map
    freq = {}
    for n in range(1, pool + 1):
        freq[n] = all_nums.count(n)

    sorted_by_freq = sorted(freq.keys(), key=lambda x: -freq[x])
    hot_numbers  = set(sorted_by_freq[:12])
    cold_numbers = set(sorted_by_freq[-12:])

    sums = []
    for d in draws:
        combo = d["combination"] if isinstance(d["combination"], list) else json.loads(d["combination"])
        sums.append(sum(combo))
    avg_sum = sum(sums) / len(sums) if sums else (pool * 3.5)
    sum_lo  = avg_sum * 0.75
    sum_hi  = avg_sum * 1.25

    def is_valid(nums):
        s = sum(nums)
        if not (sum_lo <= s <= sum_hi):
            return False
        odds = sum(1 for n in nums if n % 2 != 0)
        if not (2 <= odds <= 4):
            return False
        mid = pool / 2
        lows  = sum(1 for n in nums if n <= mid)
        highs = 6 - lows
        if not (2 <= lows <= 4):
            return False
        sorted_n = sorted(nums)
        consec = sum(1 for i in range(len(sorted_n)-1) if sorted_n[i+1] - sorted_n[i] == 1)
        if consec >= 3:
            return False
        return True

    combos = []
    attempts = 0
    while len(combos) < 5 and attempts < 5000:
        attempts += 1
        # Weight toward hot numbers
        weights = [3 if n in hot_numbers else (0.5 if n in cold_numbers else 1) for n in range(1, pool+1)]
        total_w = sum(weights)
        probs   = [w / total_w for w in weights]
        nums    = set()
        candidates = list(range(1, pool+1))
        while len(nums) < 6:
            r = random.random()
            cum = 0
            for i, p in enumerate(probs):
                cum += p
                if r <= cum:
                    n = candidates[i]
                    if n not in nums:
                        nums.add(n)
                    break
        nums = sorted(nums)
        if not is_valid(nums):
            continue
        # No duplicate combos
        if any(c["numbers"] == nums for c in combos):
            continue
        hot_c  = len([n for n in nums if n in hot_numbers])
        cold_c = len([n for n in nums if n in cold_numbers])
        odd_c  = sum(1 for n in nums if n % 2 != 0)
        combos.append({
            "numbers":   nums,
            "sum":       sum(nums),
            "hotCount":  hot_c,
            "coldCount": cold_c,
            "oddCount":  odd_c,
            "evenCount": 6 - odd_c,
            "insight":   f"{odd_c} Odd / {6-odd_c} Even · {hot_c} Hot · {cold_c} Cold · Sum {sum(nums)}"
        })

    # Pad if we couldn't get 5 valid ones (very unlikely)
    while len(combos) < 5:
        nums = sorted(random.sample(range(1, pool+1), 6))
        odd_c = sum(1 for n in nums if n % 2 != 0)
        combos.append({
            "numbers": nums, "sum": sum(nums),
            "hotCount": 0, "coldCount": 0,
            "oddCount": odd_c, "evenCount": 6-odd_c,
            "insight": f"{odd_c} Odd / {6-odd_c} Even · Sum {sum(nums)}"
        })

    return combos, {
        "historySize": len(draws),
        "avgSum": round(avg_sum),
        "hotNumbers": list(hot_numbers),
        "coldNumbers": list(cold_numbers),
    }

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/api/games")
def api_games():
    last = get_last_scrape_time()
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) as c FROM lotto_draws").fetchone()["c"]
    conn.close()
    return jsonify({"games": ["6/42","6/45","6/49","6/55","6/58"], "totalDraws": count, "lastScrape": last})

@app.route("/api/draws")
def api_draws():
    game  = request.args.get("game")
    from_ = request.args.get("from", (datetime.now()-timedelta(days=30)).strftime("%Y-%m-%d"))
    to_   = request.args.get("to",   datetime.now().strftime("%Y-%m-%d"))
    limit = int(request.args.get("limit", 200))

    conn  = get_db()
    query = "SELECT * FROM lotto_draws WHERE draw_date BETWEEN ? AND ?"
    params = [from_, to_]
    if game and game != "All":
        query += " AND game = ?"
        params.append(game)
    query += " ORDER BY draw_date DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    draws = []
    for r in rows:
        draws.append({
            "id": r["id"], "game": r["game"],
            "draw_date": r["draw_date"],
            "combination": json.loads(r["combination"]),
            "jackpot": r["jackpot"],
            "winners": r["winners"],
        })
    return jsonify({"draws": draws, "count": len(draws)})

@app.route("/api/generate")
def api_generate():
    game = request.args.get("game", "6/49")
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM lotto_draws WHERE game=? ORDER BY draw_date DESC LIMIT 200",
        (game,)
    ).fetchall()
    conn.close()

    if not rows:
        return jsonify({"error": "No draw history for this game"}), 404

    draws = [{"combination": json.loads(r["combination"])} for r in rows]
    combos, stats = generate_combos(game, draws)
    return jsonify({"game": game, "combos": combos, "stats": stats})

@app.route("/api/check-ticket", methods=["POST"])
def api_check_ticket():
    body      = request.get_json(force=True)
    game      = body.get("game", "6/49")
    draw_date = body.get("draw_date")
    bets      = body.get("bets", [])

    conn = get_db()
    if draw_date:
        row = conn.execute(
            "SELECT * FROM lotto_draws WHERE game=? AND draw_date=? ORDER BY draw_date DESC LIMIT 1",
            (game, draw_date)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM lotto_draws WHERE game=? ORDER BY draw_date DESC LIMIT 1",
            (game,)
        ).fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "No draw found for this game/date"}), 404

    winning = sorted(json.loads(row["combination"]))
    win_set = set(winning)

    results = []
    for bet in bets:
        matched = [n for n in bet if n in win_set]
        mc = len(matched)
        tier = ("Jackpot" if mc==6 else "2nd Prize" if mc==5 else
                "3rd Prize" if mc==4 else "Consolation" if mc==3 else "No Prize")
        results.append({"bet": bet, "matched": matched, "matchCount": mc, "prizeTier": tier})

    best = max((r["matchCount"] for r in results), default=0)
    return jsonify({
        "game": game,
        "drawDate": row["draw_date"],
        "winning": winning,
        "jackpot": row["jackpot"],
        "winners": row["winners"],
        "results": results,
        "bestMatch": best,
    })

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Manually trigger a PCSO scrape."""
    inserted = run_scrape_and_save()
    last = get_last_scrape_time()
    return jsonify({"inserted": inserted, "lastScrape": last, "ok": True})

@app.route("/")
def index():
    last = get_last_scrape_time()
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) as c FROM lotto_draws").fetchone()["c"]
    conn.close()
    return jsonify({
        "app": "LuckyCombi API",
        "status": "running",
        "draws": count,
        "lastScrape": last,
        "endpoints": ["/api/games", "/api/draws", "/api/generate", "/api/check-ticket", "/api/refresh"]
    })

# ── Startup ───────────────────────────────────────────────────────────────────
def startup():
    init_db()
    seed_if_empty()

    # Try a live scrape on startup
    print("  🔍 Startup scrape: fetching latest PCSO draws...")
    inserted = run_scrape_and_save()
    if inserted == 0:
        print("  ℹ  Startup scrape returned 0 new rows (PCSO blocked or no new draws)")
    else:
        print(f"  ✓  {inserted} new draws added from PCSO")

    # Start background thread for daily refresh
    t = threading.Thread(target=auto_refresh_loop, daemon=True)
    t.start()
    print("  ✓  Auto-refresh thread started (every 24h)")

# Initialize DB on import (works for both gunicorn and direct python run)
try:
    startup()
    print("✓ Startup complete")
except Exception as e:
    print(f"✗ Startup error: {e}")

if __name__ == "__main__":
    print("=" * 55)
    print("  LuckyCombi API")
    print("=" * 55)

    # Render sets PORT env variable; local uses 5000
    port = int(os.environ.get("PORT", 5000))
    host = "0.0.0.0"
    print(f"  Running on http://{host}:{port}")
    print("=" * 55)
    app.run(host=host, port=port, debug=False)
