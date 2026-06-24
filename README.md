# crypto-pipeline

A live data platform that tracks the top 270 cryptocurrencies hourly and surfaces information about data quality that most aggregators don't show.

Live dashboard: https://crypto-intelligence.streamlit.app

## The problem

Existing crypto aggregators like CoinGecko and CoinMarketCap display every coin with the same level of visual authority. A regulated commodity like Bitcoin and an obscure small-cap project ranked 250th are shown side by side, with prices, market caps, and volumes presented as equally reliable data points.

That presentation is misleading.

Academic research from the NBER suggests up to 70% of unregulated small-cap trading volume may be wash trading. Stablecoins can drift away from their dollar peg without obvious warning. Newly listed coins have thin price history that makes any volatility metric unreliable. None of this is surfaced by mainstream aggregators because their business model favors engagement over caution.

## Who this is for

Retail crypto investors who want to make informed decisions, but don't have the time or background to assess data quality on their own. People who would benefit from a tool that says "this coin's daily volume is six times its market cap, treat with caution" instead of just showing the volume number without context.

Also, hiring managers and recruiters reviewing my work in financial data engineering. This project demonstrates an end-to-end pipeline (API ingestion, cloud database, scheduled orchestration, web dashboard) along with domain judgment about what data signals matter to a financial audience.

## What this dashboard does differently

Every coin is classified into one of five risk tiers based on regulatory status and market position. Stablecoins are detected automatically from price stability rather than maintained as a hardcoded list, which means new stablecoins enter the system without code changes. Quality flags are computed on every snapshot and surfaced directly in the UI, not buried in a methodology page. Each coin has an inspectable 7-day price history.

The goal is data trust, not investment advice. The dashboard surfaces signals about how reliable the underlying numbers are, so users can interpret them with appropriate skepticism.

## Tier system

| Tier | Description | Basis |
|------|-------------|-------|
| 1 | CFTC-classified digital commodities | SEC/CFTC Joint Release 33-11412, March 2026. 16 coins. |
| S | Stablecoins | Auto-detected: 24-hour price range stayed within $0.95 to $1.05 |
| 2 | Large-cap unclassified | Top 50 by market cap, not in tier 1 or S |
| 3 | Mid-cap | Ranks 51 to 200 |
| 4 | Small-cap | Below rank 200. Heightened risk per NBER wash trading research. |

## Quality flags

Each coin is evaluated against five conditions on every hourly snapshot:

- Stablecoin off peg: price more than 3% away from $1.00
- Extreme turnover: daily volume above 5x market cap (strong wash trading signal)
- High turnover: daily volume above 2x market cap (warrants investigation)
- Recently listed: first observed in our data fewer than 7 days ago
- Low history: fewer than 24 hourly snapshots collected so far

A coin with active flags is still shown, but with the flag visible inline so the user can decide what to do with that information.

## Architecture

CoinGecko API

|

v

GitHub Actions (hourly cron)

|

v

Python ETL: fetch_data.py -> clean_data.py -> load_data.py

|

v

Turso (cloud SQLite, edge-replicated)

|

v

SQL view v_coin_analytics (joins + tier rules + flag logic)

|

v

Streamlit dashboard (https://cryptocurrency-pipeline.streamlit.app/)

The classification logic and quality flags live in a SQL view, not in the Python application code. This means the database itself is the source of truth for tier assignment, and the dashboard becomes a thin presentation layer. New flag rules can be added by altering the view without touching the dashboard code.

## Stack

Python 3.13, Turso (libsql), GitHub Actions, Streamlit, Plotly, pandas.

## Repository structure

fetch_data.py                  CoinGecko API client

clean_data.py                  validation and shaping

load_data.py                   upsert to Turso

main.py                        ETL orchestrator

migrate_reliability_layer.py   schema migration: tier table and analytics view

dashboard.py                   Streamlit application

audit_db.py                    database inventory tool

.github/workflows/             hourly cron definition

requirements.txt               Python dependencies

## Running locally

git clone https://github.com/saisandhyak/crypto-pipeline.git

cd crypto-pipeline

pip install -r requirements.txt

## Disclaimer

This is a portfolio project and not financial advice. Data is sourced from CoinGecko on a best-effort basis. Tier assignments and quality flags reflect public research and regulatory guidance as of the project date; they are not endorsements or recommendations.

Built by Sai Sandhya Kurakula.
