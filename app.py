import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

from nse_client import fetch_announcements
from filing_parser import enrich_event
from scoring import score_event
from storage import EventStore
from market import load_market_csvs, market_confirmation

st.set_page_config(page_title="EARLY EDGE // V5", page_icon="⚡", layout="wide")
st.title("⚡ EARLY EDGE // V5")
st.caption("NSE-first public-information intelligence • no dummy events • no UPSI")

store = EventStore("data/edge.db")

with st.sidebar:
    st.header("Scanner")
    lookback = st.slider("NSE lookback (days)", 1, 7, 2)
    threshold = st.slider("High-impact threshold", 50, 95, 70)
    auto = st.toggle("Auto-refresh", value=False)
    refresh = st.slider("Refresh seconds", 60, 900, 300, 60)
    st.divider()
    st.write("Sources: official NSE public filings/RSS. Market confirmation is optional local data.")

if auto:
    st.markdown(f'<meta http-equiv="refresh" content="{refresh}">', unsafe_allow_html=True)

if st.button("🔄 SCAN NOW", type="primary"):
    with st.spinner("Pulling public NSE announcements and parsing available filings..."):
        events = fetch_announcements(days=lookback)
        rows = []
        for e in events:
            e = enrich_event(e)
            e["score_components"] = score_event(e)
            e["edge_score"] = e["score_components"]["total"]
            rows.append(e)
            store.upsert(e)
    st.success(f"Processed {len(rows)} public NSE announcements.")

events = store.recent(limit=500)
if not events:
    st.info("No stored events yet. Click SCAN NOW. The app does not fabricate market/news data.")
    st.stop()

df = pd.DataFrame(events)
df["published"] = pd.to_datetime(df["published"], errors="coerce")
df = df.sort_values(["edge_score", "published"], ascending=[False, False])

c1,c2,c3,c4 = st.columns(4)
c1.metric("Events", len(df))
c2.metric("High impact", int((df.edge_score >= threshold).sum()))
c3.metric("Median score", f"{df.edge_score.median():.0f}")
c4.metric("Last scan event", df.published.max().strftime("%d %b %H:%M") if pd.notna(df.published.max()) else "—")

tabs = st.tabs(["🔥 HIGH IMPACT", "🆕 NEW FILINGS", "🕵️ UNEXPLAINED", "📊 ANALOGUES"])

with tabs[0]:
    high = df[df.edge_score >= threshold].copy()
    st.dataframe(high[["symbol","event_type","subject","edge_score","published","materiality","price_confirmation"]], use_container_width=True, hide_index=True)

with tabs[1]:
    st.dataframe(df[["symbol","event_type","subject","edge_score","published","source"]].head(150), use_container_width=True, hide_index=True)

with tabs[2]:
    unexplained = df[(df.edge_score >= 55) & (df.price_confirmation == "UNCONFIRMED")].copy()
    st.caption("Public catalyst exists but price confirmation is unavailable; this is a watchlist, not a claim of hidden information.")
    st.dataframe(unexplained[["symbol","event_type","subject","edge_score","published"]].head(100), use_container_width=True, hide_index=True)

with tabs[3]:
    analog = df.groupby("event_type", dropna=False).agg(
        events=("symbol","count"), avg_score=("edge_score","mean"), max_score=("edge_score","max")
    ).sort_values("avg_score", ascending=False)
    st.dataframe(analog.round(1), use_container_width=True)

st.divider()
selected = st.selectbox("Inspect event", df.index, format_func=lambda i: f"{df.loc[i,'symbol']} • {df.loc[i,'event_type']} • {df.loc[i,'subject'][:100]}")
r = df.loc[selected]
st.subheader(f"{r['symbol']} — {r['event_type']} — Edge {r['edge_score']:.0f}/100")
st.write(r["details"])
st.json({
    "published": str(r["published"]),
    "source": r["source"],
    "attachment": r.get("attachment"),
    "materiality": r.get("materiality"),
    "financial_figures": r.get("financial_figures", []),
    "score_components": r.get("score_components", {}),
})
