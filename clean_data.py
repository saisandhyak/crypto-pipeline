from datetime import datetime, timezone
from fetch_data import fetch_crypto_data
def clean_crypto_data(raw_data):
    now = datetime.now(timezone.utc)
    snapshot_dt = now.replace(minute=0, second=0, microsecond=0)
    snapshot_timestamp = snapshot_dt.strftime("%Y-%m-%d %H:%M:%S")
    coins_records = []
    prices_records = []
    dropped_count = 0
    for coin in raw_data:
        coin_id    = coin.get("id")
        price      = coin.get("current_price")
        market_cap = coin.get("market_cap")
        if not coin_id or price is None or market_cap is None:
            dropped_count += 1
            print(f"Dropped row cuz we are missing core data: {coin.get('id', 'UNKNOWN')}")
            continue
        coin_record = {
            "coin_id":   coin_id,
            "symbol":    coin.get("symbol", "").upper(),
            "name":      coin.get("name"),
            "image_url": coin.get("image"),
        }
        coins_records.append(coin_record)
        price_record = {
            "coin_id":              coin_id,
            "snapshot_timestamp":   snapshot_timestamp,
            "price_usd":            price,
            "market_cap":           market_cap,
            "volume_24h":           coin.get("total_volume"),
            "price_change_pct_24h": coin.get("price_change_percentage_24h"),
            "circulating_supply":   coin.get("circulating_supply"),
            "market_cap_rank":      coin.get("market_cap_rank"),
        } 
        prices_records.append(price_record)
    return coins_records, prices_records, dropped_count, snapshot_timestamp


if __name__ == "__main__":
    raw_data = fetch_crypto_data()
    print(f"data collected {len(raw_data)} raw coins from API\n")
    coins, prices, dropped, ts = clean_crypto_data(raw_data)
    print(f"Batch timestamp:  {ts}")
    print(f"Cleaned coins:    {len(coins)}")
    print(f"Cleaned prices:   {len(prices)}")
    print(f"Dropped rows:    {dropped}")
    print()
    print("Sample coin record:")
    print(f"   {coins[0]}")
    print()
    print("Sample price record:")
    print(f"   {prices[0]}")