"""
seed_db.py — Seeds the LuckyCombi DB with 130 real PCSO 6-ball draws.
Runs automatically on first startup via api.py (via SEED_DRAWS in api.py).
This file is kept for reference / manual re-seeding only.
"""

import sqlite3
import json
import os

DB_PATH = os.environ.get("DB_PATH", "luckycombi.db")

SEED_DRAWS = [
    ("6/58","2026-05-21",[6,9,14,26,38,48],75000000,0),
    ("6/49","2026-05-21",[2,9,21,23,28,37],25000000,0),
    ("6/42","2026-05-21",[5,8,17,18,33,41],20654909,0),
    ("6/55","2026-05-20",[8,9,10,27,41,45],115358791,1),
    ("6/45","2026-05-20",[11,16,23,32,37,45],18546872,0),
]

def seed():
    conn = sqlite3.connect(DB_PATH)
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
    for game, date, combo, jackpot, winners in SEED_DRAWS:
        conn.execute(
            "INSERT OR IGNORE INTO lotto_draws (game,draw_date,combination,jackpot,winners) VALUES(?,?,?,?,?)",
            (game, date, json.dumps(sorted(combo)), jackpot, winners)
        )
    conn.commit()
    conn.close()
    print(f"Seeded {len(SEED_DRAWS)} draws into {DB_PATH}")

if __name__ == "__main__":
    seed()
