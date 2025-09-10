import streamlit as st
from odds_utils import fetch_raw_odds, normalize_games, compute_matchups, add_bankroll_splits

st.set_page_config(page_title="Best Odds & Arbitrage", page_icon="", layout="wide")

# Header 

st.title("NFL Best Odds + Arbitrage Finder")
st.markdown("Get the best moneyline prices and real-time arbitrage opportunities across sportsbooks.")

# User Inputs 

bankroll = st.sidebar.number_input("Your Bankroll ($)", min_value=10.0, value=100.0, step=10.0)
min_arb = st.sidebar.slider("Minimum Arbitrage Margin (%)", min_value=0.0, max_value=10.0, value=0.0, step=0.1)
max_hours = st.sidebar.slider("Show games starting in next ___ hours", min_value=6, max_value=168, value=72)


# Fetch + Process Data 

with st.spinner("Fetching current odds..."):
    raw = fetch_raw_odds(sport="americanfootball_nfl", market="h2h", region="us")
    df_long = normalize_games(raw)
    matchups = compute_matchups(df_long, max_hours=max_hours)


    with st.expander("🔍 View All Raw Odds (Normalized)"):
        st.dataframe(df_long.head(100), use_container_width=True)

    matchups = compute_matchups(df_long)
    if not matchups.empty:
        matchups = matchups[matchups["arb_margin_pct"] >= min_arb]
        matchups = add_bankroll_splits(matchups, bankroll=bankroll)


# Display Table 

if matchups.empty:
    st.warning("No arbitrage opportunities found at the moment.")
else:
    st.success(f"Found {len(matchups)} matchups")
    st.dataframe(matchups.style.format({
        "event_start": lambda x: x.strftime("%Y-%m-%d %H:%M"),
        "home_odds": "{:.2f}",
        "away_odds": "{:.2f}",
        "home_american": "{:+d}",
        "away_american": "{:+d}",
        "home_prob": "{:.2%}",
        "away_prob": "{:.2%}",
        "home_gap_pct": "{:.1f}%",
        "away_gap_pct": "{:.1f}%",
        "arb_margin_pct": "{:.2f}%",
        "stake_home": "${:.2f}",
        "stake_away": "${:.2f}",
        "equal_payout": "${:.2f}",
        "profit_$": "${:.2f}",
        "profit_%": "{:.2f}%",
    }), use_container_width=True)
