import os
import asyncio
import libsql_client
from dotenv import load_dotenv
from fetch_data import fetch_crypto_data
from clean_data import clean_crypto_data

load_dotenv()

TURSO_URL = os.getenv("TURSO_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

# Force HTTP mode (avoids WebSocket handshake issues on Python 3.14)
if TURSO_URL and TURSO_URL.startswith("libsql://"):
    TURSO_URL = TURSO_URL.replace("libsql://", "https://", 1)

if not TURSO_URL or not TURSO_AUTH_TOKEN:
    raise RuntimeError(
        "Missing TURSO_URL or TURSO_AUTH_TOKEN. "
        "Make sure your .env file is set up correctly."
    )


async def _load_to_db_async(coins_records, prices_records):
    """Internal async loader. Not called directly."""
    
    async with libsql_client.create_client(
        url=TURSO_URL,
        auth_token=TURSO_AUTH_TOKEN,
    ) as client:
        
        coins_sql = """
            INSERT INTO coins (coin_id, symbol, name, image_url)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(coin_id) DO UPDATE SET
                symbol          = excluded.symbol,
                name            = excluded.name,
                image_url       = excluded.image_url,
                last_updated_at = CURRENT_TIMESTAMP
        """
        coins_statements = [
            (coins_sql, (c["coin_id"], c["symbol"], c["name"], c["image_url"]))
            for c in coins_records
        ]
        coins_results = await client.batch(coins_statements)
        coins_affected = sum(r.rows_affected for r in coins_results)
        
        # ── INSERT prices (fact table) ──
        prices_sql = """
            INSERT INTO price_snapshots (
                coin_id, snapshot_timestamp, price_usd, market_cap,
                volume_24h, price_change_pct_24h, circulating_supply,
                market_cap_rank
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(coin_id, snapshot_timestamp) DO NOTHING
        """
        prices_statements = [
            (prices_sql, (
                p["coin_id"], p["snapshot_timestamp"], p["price_usd"], p["market_cap"],
                p["volume_24h"], p["price_change_pct_24h"], p["circulating_supply"],
                p["market_cap_rank"],
            ))
            for p in prices_records
        ]
        prices_results = await client.batch(prices_statements)
        prices_affected = sum(r.rows_affected for r in prices_results)
        
        return coins_affected, prices_affected


def load_to_db(coins_records, prices_records):
    """
    Public sync wrapper around the async loader.
    Lets main.py call this without dealing with asyncio.
    """
    return asyncio.run(_load_to_db_async(coins_records, prices_records))


if __name__ == "__main__":
    print("📥 Fetching from CoinGecko...")
    raw_data = fetch_crypto_data()
    print(f"   Got {len(raw_data)} coins\n")
    
    print("🧹 Cleaning...")
    coins, prices, dropped, ts = clean_crypto_data(raw_data)
    print(f"   Cleaned: {len(coins)} coins, {len(prices)} prices, dropped {dropped}\n")
    
    print(f"💾 Loading into Turso cloud DB...")
    coins_affected, prices_inserted = load_to_db(coins, prices)
    print(f"   coins table:           {coins_affected} rows affected")
    print(f"   price_snapshots table: {prices_inserted} rows actually inserted\n")
    
    print(f"✅ Pipeline complete for batch {ts}")