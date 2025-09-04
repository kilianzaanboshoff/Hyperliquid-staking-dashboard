import streamlit as st
import requests
import pandas as pd
import math
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go

API_URL = "https://api.hyperliquid.xyz/info"
HEADERS = {"Content-Type": "application/json"}

# ---------------------------
# Helpers
# ---------------------------
def fetch_info(payload: dict):
    r = requests.post(API_URL, headers=HEADERS, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()

def fetch_validator_summaries():
    return fetch_info({"type": "validatorSummaries"})

def norm_stats(stats_list):
    out = {}
    if isinstance(stats_list, list):
        for pair in stats_list:
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                k, v = pair
                out[k] = v
    return out

def fmt_pct(x):
    try:
        v = float(x)
        return f"{v * 100:.2f}%"
    except Exception:
        return str(x)

def pct_to_float_0_100(pct_str):
    try:
        return float(str(pct_str).replace("%", ""))
    except Exception:
        return math.nan

def fmt_rate_str(rate_str):
    try:
        return f"{float(rate_str) * 100:.2f}%"
    except Exception:
        return str(rate_str)

def short_addr(addr: str):
    if not isinstance(addr, str) or len(addr) < 10:
        return addr
    return addr[:6] + "…" + addr[-4:]

# ---------------------------
# Page
# ---------------------------
st.set_page_config(page_title="Hyperliquid Validator Dashboard", layout="wide")
st.title("🧭 Hyperliquid Validator Dashboard")

with st.spinner("Fetching validator summaries…"):
    validators = fetch_validator_summaries()

# Normalize into DataFrame
rows = []
if isinstance(validators, list):
    for v in validators:
        stats = norm_stats(v.get("stats", []))
        day = stats.get("day", {})
        week = stats.get("week", {})
        month = stats.get("month", {})
        rows.append({
            "validator": v.get("validator"),
            "name": v.get("name") or "(unnamed)",
            "description": v.get("description", ""),
            "signer": v.get("signer"),
            "commission": fmt_rate_str(v.get("commission", "0")),
            "commission_raw": float(v.get("commission", 0.0)),  # decimal 0..1
            "isActive": bool(v.get("isActive")),
            "isJailed": bool(v.get("isJailed")),
            "stake": int(v.get("stake", 0)),
            "nRecentBlocks": int(v.get("nRecentBlocks", 0)),
            # uptime + apr (strings for display)
            "uptime_day": fmt_pct(day.get("uptimeFraction", 0)),
            "uptime_week": fmt_pct(week.get("uptimeFraction", 0)),
            "uptime_month": fmt_pct(month.get("uptimeFraction", 0)),
            "apr_day": fmt_pct(day.get("predictedApr", 0)),
            "apr_week": fmt_pct(week.get("predictedApr", 0)),
            "apr_month": fmt_pct(month.get("predictedApr", 0)),
            # numeric helpers (0..100 for charts/sorting)
            "_uptime_day_num": pct_to_float_0_100(fmt_pct(day.get("uptimeFraction", 0))),
            "_uptime_week_num": pct_to_float_0_100(fmt_pct(week.get("uptimeFraction", 0))),
            "_uptime_month_num": pct_to_float_0_100(fmt_pct(month.get("uptimeFraction", 0))),
            "_apr_day_num": pct_to_float_0_100(fmt_pct(day.get("predictedApr", 0))),
            "_apr_week_num": pct_to_float_0_100(fmt_pct(week.get("predictedApr", 0))),
            "_apr_month_num": pct_to_float_0_100(fmt_pct(month.get("predictedApr", 0))),
        })

df_val = pd.DataFrame(rows)

# ---------------------------
# Controls
# ---------------------------
with st.expander("Filters & Sort", expanded=True):
    c1, c2, c3, c4 = st.columns([2, 1.2, 1.2, 1.6])

    with c1:
        search = st.text_input("Search (name or address)", value="")
    with c2:
        active_filter = st.selectbox("Active filter", ["All", "Only active", "Only inactive"], index=0)
    with c3:
        jailed_filter = st.selectbox("Jailed filter", ["All", "Only not jailed", "Only jailed"], index=0)
    with c4:
        commission_max = st.slider("Max commission (%)", min_value=0.0, max_value=10.0, value=10.0, step=0.1)

    c5, c6, c7 = st.columns([1.3, 1.7, 1.2])
    with c5:
        sort_by = st.selectbox(
            "Sort by",
            ["stake", "apr_day", "apr_week", "apr_month", "uptime_day", "uptime_week", "uptime_month", "commission", "nRecentBlocks"],
            index=0
        )
    with c6:
        uptime_window = st.selectbox("Uptime window for filter", ["day", "week", "month"], index=1)
    with c7:
        min_uptime = st.slider("Min uptime (%)", min_value=0.0, max_value=100.0, value=0.0, step=0.5)

# Apply filters
view = df_val.copy()

if search.strip() and not view.empty:
    s = search.lower()
    mask = view["name"].fillna("").str.lower().str.contains(s) | view["validator"].str.lower().str.contains(s)
    view = view[mask]

if active_filter == "Only active":
    view = view[view["isActive"] == True]
elif active_filter == "Only inactive":
    view = view[view["isActive"] == False]

if jailed_filter == "Only not jailed":
    view = view[view["isJailed"] == False]
elif jailed_filter == "Only jailed":
    view = view[view["isJailed"] == True]

# commission filter (slider is %)
view = view[view["commission_raw"] * 100.0 <= commission_max]

# uptime filter
uptime_col_map = {"day": "_uptime_day_num", "week": "_uptime_week_num", "month": "_uptime_month_num"}
view = view[view[uptime_col_map[uptime_window]] >= min_uptime]

# Sort
sort_map = {
    "stake": ("stake", False),
    "apr_day": ("_apr_day_num", False),
    "apr_week": ("_apr_week_num", False),
    "apr_month": ("_apr_month_num", False),
    "uptime_day": ("_uptime_day_num", False),
    "uptime_week": ("_uptime_week_num", False),
    "uptime_month": ("_uptime_month_num", False),
    "commission": ("commission_raw", True),   # ascending for lower commission
    "nRecentBlocks": ("nRecentBlocks", False),
}
if not view.empty:
    col, ascending = sort_map[sort_by]
    view = view.sort_values(col, ascending=ascending, kind="mergesort")

# ---------------------------
# Main table
# ---------------------------
st.subheader("📋 Validator comparison table")

if view.empty:
    st.info("No validators match your filters.")
else:
    show_cols = [
        "name", "validator", "commission", "isActive", "isJailed", "stake", "nRecentBlocks",
        "uptime_day", "uptime_week", "uptime_month",
        "apr_day", "apr_week", "apr_month"
    ]
    st.dataframe(view[show_cols], use_container_width=True, height=520)

# ---------------------------
# Spotlight (by NAME)
# ---------------------------
st.subheader("📌 Validator spotlight")

if df_val.empty:
    st.info("No validator data available.")
else:
    # Disambiguate duplicates with short address
    df_names = df_val[["name", "validator"]].copy()
    df_names["display"] = df_names.apply(lambda r: f"{r['name']} ({short_addr(r['validator'])})", axis=1)
    df_names = df_names.merge(df_val[["validator", "stake"]], on="validator", how="left").sort_values("stake", ascending=False)

    chosen_display = st.selectbox("Select validator", df_names["display"].tolist())
    chosen_validator = df_names.loc[df_names["display"] == chosen_display, "validator"].iloc[0]
    r = df_val[df_val["validator"] == chosen_validator].iloc[0].to_dict()

    cA, cB = st.columns([1.2, 1])
    with cA:
        st.markdown(f"""
**{r.get('name','(unnamed)')}**  
`{r.get('validator','')}`

- Commission: **{r.get('commission','')}**
- Uptime (day / week / month): **{r.get('uptime_day','')} / {r.get('uptime_week','')} / {r.get('uptime_month','')}**
- Predicted APR (day / week / month): **{r.get('apr_day','')} / {r.get('apr_week','')} / {r.get('apr_month','')}**
- Stake: **{r.get('stake',0):,}**
- Recent blocks: **{r.get('nRecentBlocks',0)}**
- Active: **{r.get('isActive',False)}**, Jailed: **{r.get('isJailed',False)}**

{r.get('description','')}
""")
    with cB:
        # Radar (polar) for a quick profile feel (normalized to 0..100)
        radar_df = pd.DataFrame({
            "Metric": ["Uptime Day", "Uptime Week", "Uptime Month", "APR Day", "APR Week", "APR Month"],
            "Value": [
                r["_uptime_day_num"], r["_uptime_week_num"], r["_uptime_month_num"],
                r["_apr_day_num"], r["_apr_week_num"], r["_apr_month_num"]
            ]
        })
        fig_radar = go.Figure(data=go.Scatterpolar(
            r=radar_df["Value"],
            theta=radar_df["Metric"],
            fill='toself'
        ))
        fig_radar.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            polar=dict(radialaxis=dict(visible=True, range=[0, 100]))
        )
        st.plotly_chart(fig_radar, use_container_width=True)

# ---------------------------
# Visual comparisons
# ---------------------------
st.subheader("📈 Visual comparisons")

if not view.empty:
    # 1) APR vs Uptime bar (top N by stake)
    top_n_bar = st.slider("Top N for comparison charts", min_value=5, max_value=30, value=12, step=1)
    ranked = view.sort_values("stake", ascending=False).head(top_n_bar).copy()

    # Melt to long format for grouped bars
    long_apr = ranked.melt(
        id_vars=["name", "stake"],
        value_vars=["_apr_day_num", "_apr_week_num", "_apr_month_num"],
        var_name="APR Window",
        value_name="APR (%)"
    ).replace({"_apr_day_num": "APR Day", "_apr_week_num": "APR Week", "_apr_month_num": "APR Month"})

    long_uptime = ranked.melt(
        id_vars=["name", "stake"],
        value_vars=["_uptime_day_num", "_uptime_week_num", "_uptime_month_num"],
        var_name="Uptime Window",
        value_name="Uptime (%)"
    ).replace({"_uptime_day_num": "Uptime Day", "_uptime_week_num": "Uptime Week", "_uptime_month_num": "Uptime Month"})

    c1, c2 = st.columns(2)
    with c1:
        fig_apr = px.bar(
            long_apr,
            x="name",
            y="APR (%)",
            color="APR Window",
            barmode="group",
            hover_data={"stake": True},
            title="APR comparison (by window)"
        )
        fig_apr.update_layout(xaxis_title=None, legend_title=None, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_apr, use_container_width=True, theme="streamlit")
    with c2:
        fig_up = px.bar(
            long_uptime,
            x="name",
            y="Uptime (%)",
            color="Uptime Window",
            barmode="group",
            hover_data={"stake": True},
            title="Uptime comparison (by window)"
        )
        fig_up.update_layout(xaxis_title=None, legend_title=None, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_up, use_container_width=True, theme="streamlit")

# ---------------------------
# Donut: stake distribution
# ---------------------------
st.subheader("🧩 Stake distribution")

if df_val.empty:
    st.info("No validator data available for chart.")
else:
    cpie1, cpie2 = st.columns([1.2, 1])
    with cpie1:
        top_n = st.slider("Show top N validators", min_value=5, max_value=30, value=12, step=1)
    with cpie2:
        include_only_active = st.checkbox("Only active validators", value=True)

    chart_df = df_val.copy()
    if include_only_active:
        chart_df = chart_df[chart_df["isActive"] == True]

    chart_df = chart_df.sort_values("stake", ascending=False)
    top = chart_df.head(top_n).copy()
    others_stake = chart_df["stake"].iloc[top_n:].sum()
    if others_stake > 0:
        top = pd.concat([top, pd.DataFrame([{"name": "Others", "stake": others_stake, "validator": "others"}])], ignore_index=True)

    fig_donut = px.pie(
        top,
        names="name",
        values="stake",
        hole=0.55,
        title="Stake distribution",
        hover_data={"validator": True, "stake": True}
    )
    fig_donut.update_traces(textposition="inside", textinfo="percent+label")
    fig_donut.update_layout(
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig_donut, use_container_width=True, theme="streamlit")

# ============================================================
# NEW: "What If I Staked?" Calculator
# ============================================================
st.header("🧮 What If I Staked?")

if df_val.empty:
    st.info("No validator data available.")
else:
    calc_left, calc_right = st.columns([1.2, 1])

    with calc_left:
        # Choose validator by NAME (disambiguate with short address)
        df_names2 = df_val[["name", "validator", "stake"]].copy()
        df_names2["display"] = df_names2.apply(lambda r: f"{r['name']} ({short_addr(r['validator'])})", axis=1)
        df_names2 = df_names2.sort_values("stake", ascending=False)

        selected_display = st.selectbox("Validator", df_names2["display"].tolist(), key="calc_val_pick")
        sel_validator = df_names2.loc[df_names2["display"] == selected_display, "validator"].iloc[0]
        sel_row = df_val[df_val["validator"] == sel_validator].iloc[0]

        amount = st.number_input("Amount to stake (native token)", min_value=0.0, value=1000.0, step=10.0, help="Enter the amount of the chain's native token you plan to stake.")
        days = st.number_input("Duration (days)", min_value=1, value=30, step=1)
        apr_window = st.selectbox("APR window to use", ["Day", "Week", "Month"], index=1)
        compound = st.checkbox("Compound daily", value=False, help="If enabled, compounds rewards daily using the APR window selected.")

    with calc_right:
        # Pull APR and commission based on chosen window
        apr_map = {"Day": "_apr_day_num", "Week": "_apr_week_num", "Month": "_apr_month_num"}
        apr_pct = float(sel_row[apr_map[apr_window]])  # 0..100
        apr_dec = apr_pct / 100.0                       # 0..1
        commission_dec = float(sel_row["commission_raw"])  # 0..1
        effective_apr = apr_dec * (1.0 - commission_dec)   # assume APR is gross before commission

        # Reward math
        if compound:
            # daily compounding on effective APR
            rewards = amount * ((1.0 + effective_apr / 365.0) ** days - 1.0)
        else:
            rewards = amount * effective_apr * (days / 365.0)

        total_end = amount + rewards

        st.metric("Chosen APR (gross)", f"{apr_pct:.2f}%")
        st.metric("Commission", f"{commission_dec*100:.2f}%")
        st.metric("Effective APR (net)", f"{effective_apr*100:.2f}%")
        st.metric("Projected Rewards", f"{rewards:,.4f}")
        st.metric("Projected Total Value", f"{total_end:,.4f}")

    # Optional: compare top N validators with the same inputs
    st.subheader("Compare the same stake across top validators")
    top_n_compare = st.slider("Compare Top N by stake", min_value=5, max_value=30, value=10, step=1, key="comp_topn")

    # Prepare comparison
    comp_df = df_val.sort_values("stake", ascending=False).head(top_n_compare).copy()
    # Use selected APR window
    comp_df["gross_apr_dec"] = comp_df[apr_map[apr_window]] / 100.0
    comp_df["net_apr_dec"] = comp_df["gross_apr_dec"] * (1.0 - comp_df["commission_raw"])

    if compound:
        comp_df["projected_rewards"] = amount * ((1.0 + comp_df["net_apr_dec"] / 365.0) ** days - 1.0)
    else:
        comp_df["projected_rewards"] = amount * comp_df["net_apr_dec"] * (days / 365.0)

    comp_df["projected_total"] = amount + comp_df["projected_rewards"]

    fig_comp = px.bar(
        comp_df,
        x="name",
        y="projected_rewards",
        hover_data={"projected_total": ":,.4f", "gross_apr_dec": ":.2%", "net_apr_dec": ":.2%"},
        title=f"Projected rewards for {int(days)} days on {int(amount):,} tokens ({apr_window} APR window, {'compounding' if compound else 'simple'})"
    )
    fig_comp.update_layout(yaxis_title="Projected rewards (tokens)", xaxis_title=None, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig_comp, use_container_width=True, theme="streamlit")

    st.caption("Notes: Rewards are estimates. APR and uptime can change. We assume predicted APR is gross and subtract commission to get net APR. Compounding is simulated daily.")
