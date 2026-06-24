"""
migrate_reliability_layer.py
─────────────────────────────────────────────────────────────
Adds the reliability layer to the existing schema.

Builds:
  1. coin_classifications table (tier assignments)
  2. Seed CFTC Tier 1 commodities (hardcoded regulatory fact)
  3. Auto-detect stablecoins from price stability over 24h
  4. v_coin_analytics view (joined, classified, flagged)

Idempotent — safe to re-run anytime.
"""

import os
import libsql
from dotenv import load_dotenv

load_dotenv()
TURSO_URL = os.getenv("TURSO_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

if not TURSO_URL or not TURSO_AUTH_TOKEN:
    raise RuntimeError("Missing TURSO_URL or TURSO_AUTH_TOKEN")


# ─── Tier 1: CFTC Digital Commodities ─────────────────────────
# Source: SEC/CFTC Joint Release 33-11412 (March 17, 2026)
# These are hardcoded because they're a fixed regulatory fact.
# Update only when SEC/CFTC issues new classification.
CFTC_COMMODITIES = [
    "bitcoin", "ethereum", "solana", "ripple", "cardano",
    "chainlink", "polkadot", "avalanche-2", "stellar",
    "hedera-hashgraph", "litecoin", "dogecoin", "shiba-inu",
    "tezos", "bitcoin-cash", "aptos",
]


def main():
    print("Connecting to Turso...")
    conn = libsql.connect(
        database=TURSO_URL,
        auth_token=TURSO_AUTH_TOKEN,
    )
    cursor = conn.cursor()
    
    # ─── Step 1: Classification table ────────────────────────
    print("\n[1/5] Creating coin_classifications table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coin_classifications (
            coin_id TEXT PRIMARY KEY,
            tier TEXT NOT NULL,
            classification_source TEXT NOT NULL,
            classified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            FOREIGN KEY (coin_id) REFERENCES coins(coin_id)
        )
    """)
    print("    Table ready ✓")
    
    # ─── Step 2: Seed CFTC Tier 1 ────────────────────────────
    print("\n[2/5] Seeding CFTC Tier 1 commodities...")
    tier1_count = 0
    for coin_id in CFTC_COMMODITIES:
        cursor.execute("""
            INSERT INTO coin_classifications 
                (coin_id, tier, classification_source, notes)
            VALUES (?, 'TIER_1_CFTC', ?, ?)
            ON CONFLICT(coin_id) DO UPDATE SET
                tier = 'TIER_1_CFTC',
                classification_source = excluded.classification_source,
                notes = excluded.notes,
                classified_at = CURRENT_TIMESTAMP
        """, (
            coin_id,
            "SEC/CFTC Release 33-11412",
            "Classified as digital commodity, March 17 2026",
        ))
        tier1_count += 1
    print(f"    {tier1_count} CFTC commodities tagged ✓")
    
    # ─── Step 3: Auto-detect stablecoins from data ──────────
    print("\n[3/5] Auto-detecting stablecoins from price stability...")
    # A coin is treated as a stablecoin if:
    #   - All snapshots in last 24h have price between $0.95 and $1.05
    #   - We have at least 3 snapshots to assess
    #   - Standard deviation across snapshots is small (< 5%)
    stable_candidates = cursor.execute("""
        WITH last_24h AS (
            SELECT 
                coin_id,
                price_usd,
                snapshot_timestamp,
                ROW_NUMBER() OVER (
                    PARTITION BY coin_id 
                    ORDER BY snapshot_timestamp DESC
                ) AS rn
            FROM price_snapshots
        ),
        recent AS (
            SELECT * FROM last_24h WHERE rn <= 24
        ),
        stats AS (
            SELECT 
                coin_id,
                COUNT(*) AS n_snapshots,
                MIN(price_usd) AS min_p,
                MAX(price_usd) AS max_p,
                AVG(price_usd) AS avg_p
            FROM recent
            GROUP BY coin_id
        )
        SELECT coin_id, n_snapshots, min_p, max_p, avg_p
        FROM stats
        WHERE n_snapshots >= 3
          AND min_p >= 0.95 AND max_p <= 1.05
          AND avg_p BETWEEN 0.97 AND 1.03
    """).fetchall()
    
    stablecoin_count = 0
    for coin_id, n, min_p, max_p, avg_p in stable_candidates:
        cursor.execute("""
            INSERT INTO coin_classifications 
                (coin_id, tier, classification_source, notes)
            VALUES (?, 'TIER_S_STABLECOIN', ?, ?)
            ON CONFLICT(coin_id) DO UPDATE SET
                tier = 'TIER_S_STABLECOIN',
                classification_source = excluded.classification_source,
                notes = excluded.notes,
                classified_at = CURRENT_TIMESTAMP
            WHERE coin_classifications.tier != 'TIER_1_CFTC'
        """, (
            coin_id,
            "Auto-detected: price stability over 24h",
            f"Avg ${avg_p:.4f}, range [{min_p:.4f}, {max_p:.4f}], {n} snapshots",
        ))
        stablecoin_count += 1
    print(f"    {stablecoin_count} stablecoins auto-detected ✓")
    
    # ─── Step 4: Create the analytics view ───────────────────
    print("\n[4/5] Creating v_coin_analytics view...")
    cursor.execute("DROP VIEW IF EXISTS v_coin_analytics")
    cursor.execute("""
        CREATE VIEW v_coin_analytics AS
        WITH latest_snapshot AS (
            SELECT 
                coin_id,
                MAX(snapshot_timestamp) AS max_ts
            FROM price_snapshots
            GROUP BY coin_id
        ),
        coin_stats AS (
            SELECT 
                coin_id,
                COUNT(*) AS n_snapshots,
                MIN(snapshot_timestamp) AS first_snapshot,
                MAX(snapshot_timestamp) AS last_snapshot,
                MIN(price_usd) AS min_price_7d,
                MAX(price_usd) AS max_price_7d,
                AVG(price_usd) AS avg_price_7d
            FROM price_snapshots
            GROUP BY coin_id
        )
        SELECT
            -- Identity
            c.coin_id,
            c.symbol,
            c.name,
            c.image_url,
            c.first_seen_at,
            
            -- Latest snapshot
            ps.snapshot_timestamp AS latest_snapshot,
            ps.price_usd,
            ps.market_cap,
            ps.volume_24h,
            ps.price_change_pct_24h,
            ps.market_cap_rank,
            ps.circulating_supply,
            
            -- Historical stats (across all our data)
            cs.n_snapshots,
            cs.first_snapshot,
            cs.min_price_7d,
            cs.max_price_7d,
            cs.avg_price_7d,
            
            -- Classification
            COALESCE(cc.tier, 'UNCLASSIFIED') AS tier,
            cc.classification_source,
            cc.notes AS classification_notes,
            
            -- Computed tier_display (uses classification + market cap rank)
            CASE
                WHEN cc.tier = 'TIER_1_CFTC' THEN 'Tier 1: CFTC-Classified'
                WHEN cc.tier = 'TIER_S_STABLECOIN' THEN 'Tier S: Stablecoin'
                WHEN ps.market_cap_rank <= 50 THEN 'Tier 2: Large-cap Unclassified'
                WHEN ps.market_cap_rank <= 200 THEN 'Tier 3: Mid-cap'
                ELSE 'Tier 4: Small-cap'
            END AS tier_display,
            
            -- Risk color for UI
            CASE
                WHEN cc.tier = 'TIER_1_CFTC' THEN 'green'
                WHEN cc.tier = 'TIER_S_STABLECOIN' THEN 'green'
                WHEN ps.market_cap_rank <= 50 THEN 'green'
                WHEN ps.market_cap_rank <= 200 THEN 'yellow'
                ELSE 'red'
            END AS risk_color,
            
            -- Turnover ratio
            CASE 
                WHEN ps.market_cap > 0 THEN ps.volume_24h * 1.0 / ps.market_cap
                ELSE NULL
            END AS turnover_ratio,
            
            -- Quality Flag 1: Stablecoin depeg
            CASE
                WHEN cc.tier = 'TIER_S_STABLECOIN' 
                     AND ABS(ps.price_usd - 1.0) > 0.03 
                THEN 1 ELSE 0 
            END AS flag_stablecoin_depeg,
            
            -- Quality Flag 2: Extreme turnover (wash trading signal)
            CASE
                WHEN cc.tier != 'TIER_S_STABLECOIN'
                     AND ps.market_cap > 0
                     AND ps.volume_24h > (5 * ps.market_cap)
                THEN 1 ELSE 0 
            END AS flag_extreme_turnover,
            
            -- Quality Flag 3: High turnover (investigate)
            CASE
                WHEN cc.tier != 'TIER_S_STABLECOIN'
                     AND ps.market_cap > 0
                     AND ps.volume_24h > (2 * ps.market_cap)
                     AND ps.volume_24h <= (5 * ps.market_cap)
                THEN 1 ELSE 0 
            END AS flag_high_turnover,
            
            -- Quality Flag 4: Recent listing (low history)
            CASE
                WHEN (julianday('now') - julianday(c.first_seen_at)) < 7
                THEN 1 ELSE 0 
            END AS flag_recent_listing,
            
            -- Quality Flag 5: Low history (volatility metrics unreliable)
            CASE
                WHEN cs.n_snapshots < 24
                THEN 1 ELSE 0 
            END AS flag_low_history
            
        FROM coins c
        INNER JOIN latest_snapshot ls ON c.coin_id = ls.coin_id
        INNER JOIN price_snapshots ps 
            ON ps.coin_id = ls.coin_id 
            AND ps.snapshot_timestamp = ls.max_ts
        LEFT JOIN coin_classifications cc ON c.coin_id = cc.coin_id
        LEFT JOIN coin_stats cs ON c.coin_id = cs.coin_id
    """)
    print("    v_coin_analytics view created ✓")
    
    conn.commit()
    
    # ─── Step 5: Verification ────────────────────────────────
    print("\n[5/5] Verifying...\n")
    
    total_classified = cursor.execute(
        "SELECT COUNT(*) FROM coin_classifications"
    ).fetchone()[0]
    print(f"  Total classified coins: {total_classified}")
    
    print("\n  Coins per tier:")
    tiers = cursor.execute("""
        SELECT tier_display, COUNT(*) 
        FROM v_coin_analytics 
        GROUP BY tier_display
        ORDER BY tier_display
    """).fetchall()
    for tier, count in tiers:
        print(f"    {tier:38s}  {count:>4d} coins")
    
    print("\n  Active quality flags:")
    for flag_name in [
        "flag_stablecoin_depeg",
        "flag_extreme_turnover",
        "flag_high_turnover",
        "flag_recent_listing",
        "flag_low_history",
    ]:
        count = cursor.execute(
            f"SELECT COUNT(*) FROM v_coin_analytics WHERE {flag_name} = 1"
        ).fetchone()[0]
        print(f"    {flag_name:30s}  {count:>4d} coins")
    
    print("\n  Off-peg stablecoins right now:")
    depegged = cursor.execute("""
        SELECT symbol, name, price_usd 
        FROM v_coin_analytics 
        WHERE flag_stablecoin_depeg = 1
        ORDER BY ABS(price_usd - 1.0) DESC
    """).fetchall()
    if depegged:
        for sym, name, price in depegged:
            deviation = abs(price - 1.0) * 100
            print(f"    {sym:>6s}  {name:30s}  ${price:.4f}  ({deviation:.1f}% off peg)")
    else:
        print("    None (all stablecoins holding peg)")
    
    conn.close()
    print("\n✅ Migration complete.\n")


if __name__ == "__main__":
    main()