"""
audit_db.py
Quick inventory of what's in our Turso database.
"""

import os
import libsql
from dotenv import load_dotenv

load_dotenv()
conn = libsql.connect(
    database=os.getenv("TURSO_URL"),
    auth_token=os.getenv("TURSO_AUTH_TOKEN"),
)

print("═══ DATABASE AUDIT ═══\n")

# Tables
print("--- Tables ---")
tables = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()
for t in tables:
    print(f"  {t[0]}")

# Coins count
print("\n--- Coins dimension ---")
total_coins = conn.execute("SELECT COUNT(*) FROM coins").fetchone()[0]
print(f"  Total unique coins: {total_coins}")

# Snapshots
print("\n--- Price snapshots ---")
total_rows = conn.execute("SELECT COUNT(*) FROM price_snapshots").fetchone()[0]
unique_hours = conn.execute(
    "SELECT COUNT(DISTINCT snapshot_timestamp) FROM price_snapshots"
).fetchone()[0]
date_range = conn.execute(
    "SELECT MIN(snapshot_timestamp), MAX(snapshot_timestamp) FROM price_snapshots"
).fetchone()
print(f"  Total rows: {total_rows}")
print(f"  Unique hours: {unique_hours}")
print(f"  Date range: {date_range[0]}  ->  {date_range[1]}")

# Columns in coins
print("\n--- Columns in `coins` table ---")
desc = conn.execute("SELECT * FROM coins LIMIT 1").description
for col in desc:
    print(f"  {col[0]}")

# Columns in price_snapshots
print("\n--- Columns in `price_snapshots` table ---")
desc2 = conn.execute("SELECT * FROM price_snapshots LIMIT 1").description
for col in desc2:
    print(f"  {col[0]}")

# Top 10 coins by latest market cap
print("\n--- Top 10 coins (latest snapshot) ---")
top10 = conn.execute("""
    SELECT 
        ps.market_cap_rank,
        c.name,
        c.symbol,
        ps.price_usd,
        ps.market_cap,
        ps.volume_24h
    FROM coins c
    INNER JOIN (
        SELECT coin_id, market_cap_rank, price_usd, market_cap, volume_24h
        FROM price_snapshots
        WHERE snapshot_timestamp = (SELECT MAX(snapshot_timestamp) FROM price_snapshots)
    ) ps ON c.coin_id = ps.coin_id
    ORDER BY ps.market_cap DESC
    LIMIT 10
""").fetchall()
for rank, name, symbol, price, mcap, vol in top10:
    turnover = (vol / mcap) if mcap else 0
    print(f"  #{rank:>3}  {name:25s} ({symbol:>5s})  ${price:>12,.4f}  vol/mcap={turnover:.3f}")

# Look for likely stablecoins
print("\n--- Likely stablecoins (price between $0.95 and $1.05) ---")
stable_candidates = conn.execute("""
    SELECT c.coin_id, c.symbol, c.name, ps.price_usd, ps.market_cap_rank
    FROM coins c
    INNER JOIN (
        SELECT coin_id, price_usd, market_cap_rank
        FROM price_snapshots
        WHERE snapshot_timestamp = (SELECT MAX(snapshot_timestamp) FROM price_snapshots)
        AND price_usd BETWEEN 0.95 AND 1.05
    ) ps ON c.coin_id = ps.coin_id
    ORDER BY ps.market_cap_rank
""").fetchall()
print(f"  Found {len(stable_candidates)} candidates:")
for coin_id, sym, name, price, rank in stable_candidates[:30]:
    print(f"  #{rank:>3}  {sym:>6s}  {name:30s}  ${price:.4f}")
if len(stable_candidates) > 30:
    print(f"  ... and {len(stable_candidates) - 30} more")

# Look for suspicious volume (volume > market cap)
print("\n--- Coins with volume > market cap (potential wash trading) ---")
sus = conn.execute("""
    SELECT c.coin_id, c.symbol, c.name, ps.market_cap, ps.volume_24h, ps.market_cap_rank
    FROM coins c
    INNER JOIN (
        SELECT coin_id, market_cap, volume_24h, market_cap_rank
        FROM price_snapshots
        WHERE snapshot_timestamp = (SELECT MAX(snapshot_timestamp) FROM price_snapshots)
        AND market_cap > 0
        AND volume_24h > market_cap
    ) ps ON c.coin_id = ps.coin_id
    ORDER BY ps.market_cap_rank
""").fetchall()
print(f"  Found {len(sus)} suspicious coins:")
for coin_id, sym, name, mcap, vol, rank in sus[:20]:
    turnover = vol / mcap
    print(f"  #{rank:>3}  {sym:>6s}  {name:25s}  turnover={turnover:.2f}x")

conn.close()
print("\n═══ Audit complete ═══")