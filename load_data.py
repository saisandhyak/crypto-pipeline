"""
load_data.py
─────────────────────────────────────────────────────────────
Loads cleaned records into Turso (cloud SQLite).
Uses the official libsql driver (sync API).
"""

import os
import libsql
from dotenv import load_dotenv
from fetch_data import fetch_crypto_data
from clean_data import clean_crypto_data

load_dotenv()

TURSO_URL = os.getenv("TURSO_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

if not TURSO_URL or not TURSO_AUTH_TOKEN:
    raise RuntimeError(
        "Missing TURSO_URL or TURSO_AUTH_TOKEN. Check your .env file."
    )


def load_to_db(coins_records, prices_records):
    """Load cleaned records into Turso atomically."""
    
    conn = libsql.connect(
        database=TURSO_URL,
        auth_token=TURSO_AUTH_TOKEN,
    )
    
    try:
        cursor = conn.cursor()
        
        coins_sql = """
            INSERT INTO coins (coin_id, symbol, name, image_url)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(coin_id) DO UPDATE SET
                symbol          = excluded.symbol,
                name            = excluded.name,
                image_url       = excluded.image_url,
                last_updated_at = CURRENT_TIMESTAMP
        """
        coins_params = [
            (c["coin_id"], c["symbol"], c["name"], c["image_url"])
            for c in coins_records
        ]
        cursor.executemany(coins_sql, coins_params)
        coins_affected = cursor.rowcount
        
        prices_sql = """
            INSERT INTO price_snapshots (
                coin_id, snapshot_timestamp, price_usd, market_cap,
                volume_24h, price_change_pct_24h, circulating_supply,
                market_cap_rank
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(coin_id, snapshot_timestamp) DO NOTHING
        """
        prices_params = [
            (
                p["coin_id"], p["snapshot_timestamp"], p["price_usd"], p["market_cap"],
                p["volume_24h"], p["price_change_pct_24h"], p["circulating_supply"],
                p["market_cap_rank"],
            )
            for p in prices_records
        ]
        cursor.executemany(prices_sql, prices_params)
        prices_affected = cursor.rowcount
        
        conn.commit()
        return coins_affected, prices_affected
    
    except Exception as e:
        conn.rollback()
        print(f"❌ Database error, rolled back: {e}")
        raise
    
    finally:
        conn.close()


if __name__ == "__main__":
    print("📥 Fetching from CoinGecko...")
    raw_data = fetch_crypto_data()
    print(f"   Got {len(raw_data)} coins\n")
    
    print("🧹 Cleaning...")
    coins, prices, dropped, ts = clean_crypto_data(raw_data)
    print(f"   Cleaned: {len(coins)} coins, {len(prices)} prices, dropped {dropped}\n")
    
    print("💾 Loading into Turso cloud DB...")
    coins_affected, prices_inserted = load_to_db(coins, prices)
    print(f"   coins table:           {coins_affected} rows affected")
    print(f"   price_snapshots table: {prices_inserted} rows actually inserted\n")
    
    print(f"✅ Pipeline complete for batch {ts}")