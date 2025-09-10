import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import requests_cache


API_KEY = "738e1e551f9bd42ff77a8363da535a0f"
session = requests_cache.CachedSession("odds_cache", expire_after=timedelta(hours=1))

# ─── API CALL ────────────────────────────────────────────────────────────────────

def fetch_raw_odds(sport="americanfootball_nfl", market="h2h", region="us"):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {"regions": region, "markets": market, "apiKey": API_KEY}
    r = session.get(url, params=params)
    r.raise_for_status()
    return r.json()

# ─── CLEANING ─────────────────────────────────────────────────────────────────────

def normalize_games(games_json, take_first_n_books=None):
    rows = []
    for g in games_json:
        eid = g.get("id")
        start = g.get("commence_time")
        home, away = g.get("home_team"), g.get("away_team")
        books = g.get("bookmakers", [])
        if take_first_n_books:
            books = books[:take_first_n_books]
        for b in books:
            book = b.get("title")
            for m in b.get("markets", []):
                if m.get("key") != "h2h":
                    continue
                for o in m.get("outcomes", []):
                    rows.append({
                        "event_id": eid,
                        "event_start": start,
                        "home": home,
                        "away": away,
                        "selection": o.get("name"),
                        "book": book,
                        "price_decimal": float(o.get("price")),
                    })
    return pd.DataFrame(rows)

def decimal_to_american(d: float) -> int:
    return int(round((d - 1) * 100)) if d >= 2 else int(round(-100 / (d - 1)))

# ─── BEST ODDS + ARBITRAGE ────────────────────────────────────────────────────────

def compute_matchups(df: pd.DataFrame, max_hours=24):
    now_utc = datetime.now(timezone.utc)
    df["event_start"] = pd.to_datetime(df["event_start"], utc=True)

    df = df[
        (df["event_start"] >= now_utc - timedelta(hours=6)) &
        (df["event_start"] <= now_utc + timedelta(hours=max_hours))
    ]





    if df.empty:
        return pd.DataFrame()

    edges = []
    for (eid, team), grp in df.groupby(["event_id", "selection"]):
        grp = grp.sort_values("price_decimal", ascending=False).reset_index(drop=True)
        best_row = grp.iloc[0]
        best_price = best_row["price_decimal"]
        next_best_price = grp["price_decimal"].iloc[1] if len(grp) > 1 else None

        edges.append({
            "event_id": eid,
            "event_start": best_row["event_start"],
            "home": best_row["home"],
            "away": best_row["away"],
            "team": team,
            "best_book": best_row["book"],
            "best_decimal": best_price,
            "best_american": decimal_to_american(best_price),
            "implied_prob": 1.0 / best_price,
            "next_best_decimal": next_best_price,
            "gap_percent": ((best_price - next_best_price) / next_best_price * 100) if next_best_price else None
        })

    edge_df = pd.DataFrame(edges)

    rows = []
    for eid, grp in edge_df.groupby("event_id"):
        if grp.shape[0] < 2:
            continue

        home = grp.iloc[0]["home"]
        away = grp.iloc[0]["away"]
        start = grp.iloc[0]["event_start"]

        h = grp[grp["team"] == home].iloc[0]
        a = grp[grp["team"] == away].iloc[0]

        inv_sum = 1/h["best_decimal"] + 1/a["best_decimal"]
        arb_margin = (1 - inv_sum) * 100

        rows.append({
            "event_start": start,
            "home_team": home,
            "away_team": away,

            "home_book": h["best_book"],
            "home_odds": h["best_decimal"],
            "home_american": h["best_american"],
            "home_prob": h["implied_prob"],
            "home_gap_pct": h["gap_percent"],

            "away_book": a["best_book"],
            "away_odds": a["best_decimal"],
            "away_american": a["best_american"],
            "away_prob": a["implied_prob"],
            "away_gap_pct": a["gap_percent"],

            "arb_margin_pct": arb_margin,
        })

    df_final = pd.DataFrame(rows)
    df_final["max_gap_pct"] = df_final[["home_gap_pct", "away_gap_pct"]].max(axis=1)
    return df_final.sort_values("max_gap_pct", ascending=False).reset_index(drop=True)

# ─── BANKROLL SPLIT ───────────────────────────────────────────────────────────────

def add_bankroll_splits(df: pd.DataFrame, bankroll=100.0):
    d1 = df["home_odds"]
    d2 = df["away_odds"]
    denom = d1 + d2

    df["stake_home"] = bankroll * (d2 / denom)
    df["stake_away"] = bankroll * (d1 / denom)
    df["equal_payout"] = df["stake_home"] * d1
    df["profit_$"] = df["equal_payout"] - bankroll
    df["profit_%"] = (df["profit_$"] / bankroll) * 100

    return df
