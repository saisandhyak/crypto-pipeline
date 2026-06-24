import os
import libsql
import streamlit as st
import pandas as pd
import plotly.express as px
from dotenv import load_dotenv

load_dotenv()
TURSO_URL = os.getenv("TURSO_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")


st.set_page_config(
    page_title="Crypto Intelligence",
    page_icon="📈",
    layout="wide",
)


@st.cache_data(ttl=600)
def load_analytics():
    conn = libsql.connect(database=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM v_coin_analytics")
        rows = cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        return pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()


@st.cache_data(ttl=600)
def load_market_stats():
    conn = libsql.connect(database=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COALESCE(SUM(market_cap), 0),
                COALESCE(SUM(volume_24h), 0),
                COUNT(*),
                MAX(latest_snapshot),
                COALESCE(SUM(CASE WHEN symbol = 'BTC' THEN market_cap ELSE 0 END), 0)
            FROM v_coin_analytics
        """)
        row = cursor.fetchone()
        total_mcap = row[0] or 0
        return {
            "total_market_cap": total_mcap,
            "total_volume_24h": row[1] or 0,
            "coin_count": row[2] or 0,
            "data_freshness": row[3] or "",
            "btc_dominance": (row[4] / total_mcap * 100) if total_mcap else 0,
        }
    finally:
        conn.close()


@st.cache_data(ttl=600)
def load_coin_history(coin_id):
    """Load last 7 days of snapshots for one coin."""
    conn = libsql.connect(database=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT snapshot_timestamp, price_usd, volume_24h, market_cap
            FROM price_snapshots
            WHERE coin_id = ?
              AND snapshot_timestamp >= datetime('now', '-7 days')
            ORDER BY snapshot_timestamp ASC
        """, (coin_id,))
        rows = cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        return pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()


TIER_COLORS = {
    "Tier 1: CFTC-Classified": "#10b981",
    "Tier S: Stablecoin": "#3b82f6",
    "Tier 2: Large-cap Unclassified": "#84cc16",
    "Tier 3: Mid-cap": "#eab308",
    "Tier 4: Small-cap": "#ef4444",
}

TIER_BADGES = {
    "Tier 1: CFTC-Classified": "🟢",
    "Tier S: Stablecoin": "🔵",
    "Tier 2: Large-cap Unclassified": "🟢",
    "Tier 3: Mid-cap": "🟡",
    "Tier 4: Small-cap": "🔴",
}


st.title("Crypto Intelligence")
st.write("Tracking risk tiers and data quality across the top 250 coins.")

df = load_analytics()
stats = load_market_stats()


st.divider()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Market Cap", f"${stats['total_market_cap'] / 1e12:.2f}T")
with col2:
    st.metric("24h Volume", f"${stats['total_volume_24h'] / 1e9:.1f}B")
with col3:
    st.metric("BTC Dominance", f"{stats['btc_dominance']:.1f}%")
with col4:
    st.metric("Coins", f"{stats['coin_count']}")

st.caption(f"Last snapshot: {stats['data_freshness']} UTC. Data via CoinGecko.")


st.divider()
st.subheader("Inspect a coin")

inspector_col1, inspector_col2 = st.columns([1, 3])

with inspector_col1:
    # Sort coins by rank for easier finding
    coin_options = df.sort_values("market_cap_rank")[["coin_id", "symbol", "name", "market_cap_rank"]]
    coin_options["label"] = coin_options.apply(
        lambda r: f"#{int(r['market_cap_rank'])} {r['name']} ({r['symbol']})", axis=1
    )
    
    selected_label = st.selectbox(
        "Pick a coin",
        options=coin_options["label"].tolist(),
        index=0,
    )
    selected_coin = coin_options[coin_options["label"] == selected_label].iloc[0]
    selected_coin_id = selected_coin["coin_id"]
    
    # Stats for the selected coin (from latest snapshot in df)
    coin_row = df[df["coin_id"] == selected_coin_id].iloc[0]
    st.metric("Current Price", f"${coin_row['price_usd']:.4f}")
    st.metric("24h Change", f"{coin_row['price_change_pct_24h']:.2f}%")
    st.write(f"**Tier:** {TIER_BADGES.get(coin_row['tier_display'], '')} {coin_row['tier_display']}")

with inspector_col2:
    history = load_coin_history(selected_coin_id)
    if history.empty:
        st.warning("No history found for this coin.")
    else:
        # 7-day stats
        stats_cols = st.columns(4)
        stats_cols[0].metric("7-day High", f"${history['price_usd'].max():.4f}")
        stats_cols[1].metric("7-day Low", f"${history['price_usd'].min():.4f}")
        stats_cols[2].metric("7-day Avg", f"${history['price_usd'].mean():.4f}")
        stats_cols[3].metric("Snapshots", f"{len(history)}")
        
        # Price chart
        fig_price = px.line(
            history,
            x="snapshot_timestamp",
            y="price_usd",
            title=f"{selected_coin['name']} ({selected_coin['symbol']}) — 7-day price",
            labels={"snapshot_timestamp": "Time", "price_usd": "Price (USD)"},
        )
        fig_price.update_layout(height=350, margin=dict(t=40, b=10, l=10, r=10))
        st.plotly_chart(fig_price, use_container_width=True)


chart_col1, chart_col2 = st.columns([1, 2])

with chart_col1:
    tier_counts = df["tier_display"].value_counts().reset_index()
    tier_counts.columns = ["Tier", "Count"]
    fig_donut = px.pie(
        tier_counts, values="Count", names="Tier", hole=0.5,
        color="Tier", color_discrete_map=TIER_COLORS,
        title="Coins by tier",
    )
    fig_donut.update_layout(showlegend=True, legend=dict(orientation="v", x=1.05, y=0.5), height=350, margin=dict(t=40, b=10, l=10, r=10))
    st.plotly_chart(fig_donut, use_container_width=True)

with chart_col2:
    top10 = df.nsmallest(10, "market_cap_rank")[["symbol", "name", "market_cap", "tier_display"]].copy()
    top10["mcap_b"] = top10["market_cap"] / 1e9
    fig_bar = px.bar(
        top10, x="mcap_b", y="symbol", orientation="h",
        color="tier_display", color_discrete_map=TIER_COLORS,
        labels={"mcap_b": "Market cap ($B)", "symbol": ""},
        title="Top 10 by market cap", text="mcap_b",
    )
    fig_bar.update_traces(texttemplate="$%{text:.1f}B", textposition="outside")
    fig_bar.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.15), height=350, margin=dict(t=40, b=10, l=10, r=10), yaxis=dict(categoryorder="total ascending"))
    st.plotly_chart(fig_bar, use_container_width=True)


st.divider()
st.subheader("Quality flags")

flag_data = [
    ("Stablecoin off-peg (>3%)", int(df["flag_stablecoin_depeg"].sum())),
    ("Extreme turnover (>5x mcap)", int(df["flag_extreme_turnover"].sum())),
    ("High turnover (>2x mcap)", int(df["flag_high_turnover"].sum())),
    ("Recently listed (<7d)", int(df["flag_recent_listing"].sum())),
    ("Low history (<24 snapshots)", int(df["flag_low_history"].sum())),
]
flag_df = pd.DataFrame(flag_data, columns=["Concern", "Count"])

col_a, col_b = st.columns([2, 1])
with col_a:
    st.dataframe(flag_df, hide_index=True, use_container_width=True)
with col_b:
    total_flags = sum(x[1] for x in flag_data)
    if total_flags == 0:
        st.success("Nothing flagged.")
    else:
        st.warning(f"{total_flags} coins flagged.")


stable_df = df[df["tier_display"] == "Tier S: Stablecoin"].copy()
if not stable_df.empty:
    st.divider()
    st.subheader(f"Stablecoin pegs ({len(stable_df)} coins)")
    stable_df["deviation_pct"] = (stable_df["price_usd"] - 1.0) * 100
    stable_df["status"] = stable_df["deviation_pct"].apply(
        lambda x: "Off-peg" if abs(x) > 3 else "Drift" if abs(x) > 1 else "Healthy"
    )
    fig_peg = px.scatter(
        stable_df.sort_values("market_cap_rank"),
        x="deviation_pct", y="symbol", color="status", size="market_cap",
        hover_data=["name", "price_usd", "market_cap_rank"],
        color_discrete_map={"Healthy": "#10b981", "Drift": "#eab308", "Off-peg": "#ef4444"},
        title="Deviation from $1.00",
        labels={"deviation_pct": "Off peg (%)", "symbol": ""},
    )
    fig_peg.add_vline(x=0, line_dash="dash", line_color="gray", opacity=0.5)
    fig_peg.add_vrect(x0=-3, x1=3, fillcolor="green", opacity=0.05, line_width=0)
    fig_peg.update_layout(height=600, showlegend=True)
    st.plotly_chart(fig_peg, use_container_width=True)
    st.caption("Green band = within 3% of $1.00. Bubble size = market cap.")


st.divider()
st.subheader("Browse coins")

search = st.text_input("Search", placeholder="bitcoin, BTC, etc.")

if search:
    mask = df["name"].str.contains(search, case=False, na=False) | df["symbol"].str.contains(search, case=False, na=False)
    df_view = df[mask]
else:
    df_view = df

tier_order = [
    "Tier 1: CFTC-Classified",
    "Tier S: Stablecoin",
    "Tier 2: Large-cap Unclassified",
    "Tier 3: Mid-cap",
    "Tier 4: Small-cap",
]

def make_flags(row):
    flags = []
    if row["flag_stablecoin_depeg"]: flags.append("Off-peg")
    if row["flag_extreme_turnover"]: flags.append("Extreme vol")
    if row["flag_high_turnover"]: flags.append("High vol")
    if row["flag_recent_listing"]: flags.append("New")
    if row["flag_low_history"]: flags.append("Low history")
    return ", ".join(flags) if flags else ""

for tier in tier_order:
    tier_df = df_view[df_view["tier_display"] == tier].copy()
    if tier_df.empty:
        continue
    tier_df["Flags"] = tier_df.apply(make_flags, axis=1)
    expanded_default = tier in ["Tier 1: CFTC-Classified", "Tier S: Stablecoin", "Tier 2: Large-cap Unclassified"]
    with st.expander(f"{TIER_BADGES.get(tier, '⚪')}  {tier}  ({len(tier_df)})", expanded=expanded_default):
        display_df = tier_df[["market_cap_rank", "symbol", "name", "price_usd", "price_change_pct_24h", "market_cap", "volume_24h", "turnover_ratio", "Flags"]].sort_values("market_cap_rank")
        st.dataframe(
            display_df, hide_index=True, use_container_width=True,
            column_config={
                "market_cap_rank": st.column_config.NumberColumn("Rank", width="small"),
                "symbol": st.column_config.TextColumn("Symbol", width="small"),
                "name": st.column_config.TextColumn("Name"),
                "price_usd": st.column_config.NumberColumn("Price", format="$%.4f"),
                "price_change_pct_24h": st.column_config.NumberColumn("24h %", format="%.2f%%"),
                "market_cap": st.column_config.NumberColumn("Market Cap", format="$%.0f"),
                "volume_24h": st.column_config.NumberColumn("Volume", format="$%.0f"),
                "turnover_ratio": st.column_config.NumberColumn("Turnover", format="%.3f"),
                "Flags": st.column_config.TextColumn("Flags"),
            },
        )


st.divider()
with st.expander("How tiers work"):
    st.markdown("""
**Tier 1 (CFTC):** 16 coins listed as digital commodities in SEC/CFTC Release 33-11412 (March 2026). Bitcoin, Ethereum, Solana, XRP, Cardano, Chainlink, Polkadot, Avalanche, Stellar, Hedera, Litecoin, Dogecoin, Shiba Inu, Tezos, Bitcoin Cash, Aptos.

**Tier S (Stablecoin):** Detected from price stability. A coin lands here if all snapshots in the last 24h stayed between $0.95 and $1.05.

**Tier 2:** Top 50 by market cap that aren't Tier 1 or S.

**Tier 3:** Ranks 51-200.

**Tier 4:** Below rank 200. NBER research suggests up to 70% of small-cap volume can be wash trading.

**Flag definitions**
- Stablecoin off-peg: price more than 3% off $1.00
- Extreme turnover: daily volume above 5x market cap
- High turnover: daily volume above 2x market cap
- Recently listed: first seen in our data less than 7 days ago
- Low history: fewer than 24 snapshots collected

Data comes from CoinGecko, refreshed hourly via GitHub Actions, stored in Turso.
[github.com/saisandhyak/crypto-pipeline](https://github.com/saisandhyak/crypto-pipeline)
    """)


st.caption("Built by Sai Sandhya Kurakula. Not financial advice.")