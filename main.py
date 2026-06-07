import os
import time
import asyncio
import traceback
import libsql_client
from datetime import datetime, timezone
from dotenv import load_dotenv

from fetch_data import fetch_crypto_data
from clean_data import clean_crypto_data
from load_data import load_to_db

load_dotenv()
TURSO_URL = os.getenv("TURSO_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

# Force HTTP mode (same fix as in load_data.py)
if TURSO_URL and TURSO_URL.startswith("libsql://"):
    TURSO_URL = TURSO_URL.replace("libsql://", "https://", 1)

async def _log_pipeline_run_async(status, rows_inserted, duration_seconds, error_message=None):
    """Write one audit row to pipeline_runs in Turso. Never raises."""
    try:
        async with libsql_client.create_client(
            url=TURSO_URL,
            auth_token=TURSO_AUTH_TOKEN,
        ) as client:
            await client.execute(
                """
                INSERT INTO pipeline_runs (
                    status, rows_inserted, duration_seconds, error_message
                ) VALUES (?, ?, ?, ?)
                """,
                (status, rows_inserted, duration_seconds, error_message),
            )
    except Exception as e:
        print(f"⚠️  Failed to write to pipeline_runs: {e}")


def log_pipeline_run(status, rows_inserted, duration_seconds, error_message=None):
    """Sync wrapper so the rest of main.py stays simple."""
    asyncio.run(_log_pipeline_run_async(status, rows_inserted, duration_seconds, error_message))


def run_pipeline():
    start_time = time.monotonic()
    start_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"Pipeline started at {start_iso}\n")
    
    rows_inserted = 0
    status = "failed"
    error_message = None
    
    try:
        print("📥 [1/3] Fetching from CoinGecko...")
        raw_data = fetch_crypto_data()
        print(f"        Got {len(raw_data)} coins\n")
        
        print("🧹 [2/3] Cleaning...")
        coins, prices, dropped, snapshot_ts = clean_crypto_data(raw_data)
        print(f"        Cleaned {len(coins)} coins, dropped {dropped} bad rows")
        print(f"        Batch timestamp: {snapshot_ts}\n")
        
        print("💾 [3/3] Loading into Turso...")
        coins_affected, prices_inserted = load_to_db(coins, prices)
        print(f"        coins table:           {coins_affected} rows affected")
        print(f"        price_snapshots table: {prices_inserted} rows actually inserted\n")
        
        status = "success"
        rows_inserted = prices_inserted
    
    except Exception as e:
        status = "failed"
        error_message = f"{type(e).__name__}: {str(e)}"
        print("❌ Pipeline FAILED:")
        print("─" * 60)
        traceback.print_exc()
        print("─" * 60)
    
    finally:
        duration = round(time.monotonic() - start_time, 2)
        log_pipeline_run(
            status=status,
            rows_inserted=rows_inserted,
            duration_seconds=duration,
            error_message=error_message,
        )
        if status == "success":
            print(f"✅ SUCCESS in {duration}s — {rows_inserted} new rows")
        else:
            print(f"❌ FAILED in {duration}s")
    
    return status == "success"


if __name__ == "__main__":
    success = run_pipeline()
    exit(0 if success else 1)