import time
import requests

MAX_RETRIES = 7
def fetch_crypto_data():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1,
        "price_change_percentage": "24h"
    }
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=30)

            response.raise_for_status()

            data = response.json()

            if not isinstance(data, list) or len(data) == 0:
                raise ValueError("Invalid response: expected a non-empty list")

            return data

        except (requests.exceptions.RequestException, ValueError) as error:
            print(f"Attempt {attempt + 1} failed: {error}")

            if attempt == MAX_RETRIES - 1:
                raise

            wait_time = 2 ** attempt
            print(f"Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
if __name__ == "__main__":
    crypto_data = fetch_crypto_data()
    print(f"Number of coins: {len(crypto_data)} coins\n")
    for i, coin in enumerate(crypto_data, start=1):
        print(f"#{i:3d}: {coin['name']:30s} ${coin['current_price']:>15,.2f}")
