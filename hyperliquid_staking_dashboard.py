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

# User-scoped helpers
def fetch_delegator_summary(address: str):
    return fetch_info({"type": "delegatorSummary", "user": address})

def fetch_pending_withdrawals(address: str):
    """
    Primary: try detailed queue via 'pendingWithdrawals'
    Fallbacks: return None if not available.

    Expected shapes (we normalize them):
    - {"withdrawals": [ ... ]}
    - {"items": [ ... ]}
    - {"pending": [ ... ]}
    - {"rows": [ ... ]}
    - {"pendingWithdrawals": [ ... ]}
    - or a bare list [ ... ]
    """
    try:
        data = fetch_info({"type": "pendingWithdrawals", "user": address})
        if isinstance(data, dict):
            for k in ("withdrawals", "items", "pending", "rows", "pendingWithdrawals"):
                if k in data and isinstance(data[k], list):
                    return data[k]
        elif isinstance(data, list):
            return data
    except Exception:
        pass
    return None

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

def ms_to_datetime(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ms)

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
# Foundation settings (NEW)
# ---------------------------
# Heuristic flag for foundation validators
df_val["is_foundation"] = df_val["name"].str.contains("foundation", case=False, na=False)
# Placeholder for per-validator foundation delegation amounts (tokens)
df_val["foundationDelegation"] = 0.0

with st.expander("⚙️ Foundation delegation settings", expanded=False):
    st.caption("Optional: Upload a CSV with columns: `validator, foundationDelegation` (amounts in native tokens).")
    up = st.file_uploader("Upload CSV (validator,foundationDelegation)", type=["csv"])
    if up is not None:
        try:
            _f = pd.read_csv(up)
            _f.columns = [c.strip() for c in _f.columns]
            vcol = None
            for cand in ["validator", "address", "signer"]:
                if cand in _f.columns:
                    vcol = cand
                    break
            if vcol is None or "foundationDelegation" not in _f.columns:
                st.error("CSV must include columns: `validator` (or `address`/`signer`) and `foundationDelegation`.")
            else:
                _f["validator_lc"] = _f[vcol].astype(str).str.lower()
                _map = dict(zip(_f["validator_lc"], _f["foundationDelegation"].astype(float)))
                df_val["validator_lc"] = df_val["validator"].str.lower()
                df_val["foundationDelegation"] = df_val["validator_lc"].map(_map).fillna(0.0)
                st.success("Loaded foundation delegation CSV.")
        except Exception as e:
            st.error(f"Could not read CSV: {e}")

    cfd1, cfd2 = st.columns([1.1, 1])
    with cfd1:
        st.session_state["hide_foundation_validators"] = st.checkbox(
            "Hide Foundation validators (name contains 'foundation')", value=False
        )
    with cfd2:
        st.session_state["subtract_foundation_delegation"] = st.checkbox(
            "Subtract Foundation delegation from stake (show organic stake)", value=False,
            help="Uses uploaded CSV if provided; otherwise subtraction = 0."
        )

def stake_adjusted_column(frame: pd.DataFrame) -> pd.Series:
    """Return the column to use for charts/sorting based on toggles."""
    if st.session_state.get("subtract_foundation_delegation"):
        s = frame["stake"] - frame.get("foundationDelegation", 0.0)
        return s.clip(lower=0)
    return frame["stake"]

if st.session_state.get("subtract_foundation_delegation"):
    st.info("Showing **organic stake** (raw stake minus known Foundation delegation). Upload/update CSV in ⚙️ to refine numbers.")

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

# Hide Foundation validators if requested
if st.session_state.get("hide_foundation_validators"):
    view = view[~view["is_foundation"]]

# commission filter (slider is %)
view = view[view["commission_raw"] * 100.0 <= commission_max]

# uptime filter
uptime_col_map = {"day": "_uptime_day_num", "week": "_uptime_week_num", "month": "_uptime_month_num"}
view = view[view[uptime_col_map[uptime_window]] >= min_uptime]

# Adjusted stake for current view
view["stake_display"] = stake_adjusted_column(view)

# Sort
sort_map = {
    "stake": ("stake_display", False),     # use adjusted stake for sorting
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
        "name", "validator", "commission", "isActive", "isJailed", "nRecentBlocks",
        "uptime_day", "uptime_week", "uptime_month",
        "apr_day", "apr_week", "apr_month",
    ]
    if st.session_state.get("subtract_foundation_delegation"):
        tbl = view[show_cols + ["stake_display", "stake", "foundationDelegation", "is_foundation"]].copy()
        tbl.rename(columns={
            "stake_display": "stake (adj)",
            "stake": "stake (raw)"
        }, inplace=True)
    else:
        tbl = view[show_cols + ["stake", "is_foundation"]].copy()
        tbl.rename(columns={"stake": "stake (raw)"}, inplace=True)

    st.dataframe(tbl, use_container_width=True, height=520)

# ---------------------------
# Spotlight (by NAME)
# ---------------------------
st.subheader("📌 Validator spotlight")

if df_val.empty:
    st.info("No validator data available.")
else:
    # Choose by name (sorted by adjusted stake for nicer UX)
    stake_display_all = stake_adjusted_column(df_val)
    df_names = df_val[["name", "validator"]].copy()
    df_names["stake_display"] = stake_display_all.values
    df_names["display"] = df_names.apply(lambda r: f"{r['name']} ({short_addr(r['validator'])})", axis=1)
    df_names = df_names.sort_values("stake_display", ascending=False)

    chosen_display = st.selectbox("Select validator", df_names["display"].tolist())
    chosen_validator = df_names.loc[df_names["display"] == chosen_display, "validator"].iloc[0]
    r = df_val[df_val["validator"] == chosen_validator].iloc[0].to_dict()

    # compute adjusted stake for the chosen validator
    stake_adj = float(r["stake"]) - float(r.get("foundationDelegation", 0.0))
    stake_adj = max(stake_adj, 0.0)

    cA, cB = st.columns([1.2, 1])
    with cA:
        st.markdown(f"""
**{r.get('name','(unnamed)')}**  
`{r.get('validator','')}`

- Commission: **{r.get('commission','')}**
- Uptime (day / week / month): **{r.get('uptime_day','')} / {r.get('uptime_week','')} / {r.get('uptime_month','')}**
- Predicted APR (day / week / month): **{r.get('apr_day','')} / {r.get('apr_week','')} / {r.get('apr_month','')}**
- Recent blocks: **{r.get('nRecentBlocks',0)}**
- Active: **{r.get('isActive',False)}**, Jailed: **{r.get('isJailed',False)}**
""")
        if st.session_state.get("subtract_foundation_delegation"):
            st.markdown(
                f"- Stake (adj): **{stake_adj:,.0f}**  •  Stake (raw): **{r.get('stake',0):,}**"
                f"  •  Foundation Delegation: **{float(r.get('foundationDelegation',0)):,.0f}**"
            )
        else:
            st.markdown(f"- Stake: **{r.get('stake',0):,}**")

        st.write(r.get('description',''))

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
    # APR vs Uptime bar (top N by adjusted stake)
    top_n_bar = st.slider("Top N for comparison charts", min_value=5, max_value=30, value=12, step=1)
    ranked = view.sort_values("stake_display", ascending=False).head(top_n_bar).copy()

    # Melt to long format for grouped bars
    long_apr = ranked.melt(
        id_vars=["name", "stake_display"],
        value_vars=["_apr_day_num", "_apr_week_num", "_apr_month_num"],
        var_name="APR Window",
        value_name="APR (%)"
    ).replace({"_apr_day_num": "APR Day", "_apr_week_num": "APR Week", "_apr_month_num": "APR Month"})

    long_uptime = ranked.melt(
        id_vars=["name", "stake_display"],
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
            hover_data={"stake_display": True},
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
            hover_data={"stake_display": True},
            title="Uptime comparison (by window)"
        )
        fig_up.update_layout(xaxis_title=None, legend_title=None, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_up, use_container_width=True, theme="streamlit")

# ---------------------------
# Donut: stake distribution (top-N, optional active filter)
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
    if st.session_state.get("hide_foundation_validators"):
        chart_df = chart_df[~chart_df["is_foundation"]]

    chart_df["stake_display"] = stake_adjusted_column(chart_df)
    chart_df = chart_df.sort_values("stake_display", ascending=False)

    top = chart_df.head(top_n).copy()
    others_stake = chart_df["stake_display"].iloc[top_n:].sum()
    if others_stake > 0:
        top = pd.concat(
            [top, pd.DataFrame([{"name": "Others", "stake_display": others_stake, "validator": "others"}])],
            ignore_index=True
        )

    fig_donut = px.pie(
        top,
        names="name",
        values="stake_display",
        hole=0.55,
        title=f"Stake distribution{' (organic)' if st.session_state.get('subtract_foundation_delegation') else ''}",
        hover_data={"validator": True, "stake_display": True}
    )
    fig_donut.update_traces(textposition="inside", textinfo="percent+label")
    fig_donut.update_layout(margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig_donut, use_container_width=True, theme="streamlit")

# ---------------------------
# All Active Non-Foundation stake distribution (uses adjusted stake)
# ---------------------------
st.subheader("🥧 Active Non-Foundation Stake Distribution")

if df_val.empty:
    st.info("No validator data available for chart.")
else:
    nf_mask = (df_val["isActive"] == True) & (~df_val["is_foundation"])
    non_foundation = df_val.loc[nf_mask, ["name", "stake", "foundationDelegation"]].copy()
    non_foundation["stake_display"] = stake_adjusted_column(df_val).loc[non_foundation.index]

    if non_foundation.empty:
        st.info("No active non-foundation validators found.")
    else:
        fig_nonf = px.pie(
            non_foundation,
            names="name",
            values="stake_display",
            hole=0.45,
            title=f"All Active Validators (excluding Foundation){' - organic' if st.session_state.get('subtract_foundation_delegation') else ''}",
        )
        fig_nonf.update_traces(textposition="inside", textinfo="percent+label")
        fig_nonf.update_layout(margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_nonf, use_container_width=True, theme="streamlit")

# ============================================================
# 🔎 Unstaking queue lookup (by address)
# ============================================================
st.header("🔎 Unstaking queue lookup")

addr_col1, addr_col2 = st.columns([1.4, 1])
with addr_col1:
    lookup_addr = st.text_input(
        "Paste wallet address to inspect pending withdrawals",
        value="0xCeaD893b162D38e714D82d06a7fe0b0dc3c38E0b",
        help="Shows items currently waiting in the 7-day unstaking queue (if any)."
    )
with addr_col2:
    if st.button("Lookup"):
        st.session_state["_do_lookup_unstaking"] = True

if st.session_state.get("_do_lookup_unstaking") and lookup_addr:
    with st.spinner("Fetching pending withdrawals…"):
        detailed = fetch_pending_withdrawals(lookup_addr)
        summary = None
        try:
            summary = fetch_delegator_summary(lookup_addr)
        except Exception:
            pass

    if detailed and isinstance(detailed, list) and len(detailed) > 0:
        norm_rows = []
        for item in detailed:
            amt = item.get("amount") or item.get("wei") or item.get("value") or item.get("qty")
            req = item.get("requestedAt") or item.get("time") or item.get("requested") or item.get("createdAt")
            eli = item.get("eligibleAt") or item.get("unlockAt") or item.get("availableAt")
            txh = item.get("txHash") or item.get("hash") or item.get("tx")
            try:
                amt_f = float(amt)
            except Exception:
                amt_f = None
            norm_rows.append({
                "Amount": amt_f if amt_f is not None else str(amt),
                "Requested At": ms_to_datetime(req) if req else "",
                "Eligible At": ms_to_datetime(eli) if eli else "",
                "Tx Hash": txh or "",
            })
        df_pending = pd.DataFrame(norm_rows)
        st.success(f"Found {len(df_pending)} pending withdrawal(s) for {short_addr(lookup_addr)}")
        st.dataframe(df_pending, use_container_width=True)
    else:
        if summary:
            n = summary.get("nPendingWithdrawals", 0)
            total = summary.get("totalPendingWithdrawal", 0)
            try:
                total_f = float(total)
                total_str = f"{total_f:,.4f}"
            except Exception:
                total_str = str(total)
            st.info(
                f"No detailed queue rows returned. "
                f"Summary indicates **{n}** pending withdrawal(s) totaling **{total_str}** tokens."
            )
        else:
            st.warning("No pending withdrawals found or endpoint didn’t return details for this address.")

# ============================================================
# 🧮 What If I Staked? Calculator
# ============================================================
st.header("🧮 What If I Staked?")

if df_val.empty:
    st.info("No validator data available.")
else:
    calc_left, calc_right = st.columns([1.2, 1])

    with calc_left:
        # Choose validator by NAME (disambiguate with short address), sorted by adjusted stake
        stake_display_all = stake_adjusted_column(df_val)
        df_names2 = df_val[["name", "validator"]].copy()
        df_names2["stake_display"] = stake_display_all.values
        df_names2["display"] = df_names2.apply(lambda r: f"{r['name']} ({short_addr(r['validator'])})", axis=1)
        df_names2 = df_names2.sort_values("stake_display", ascending=False)

        selected_display = st.selectbox("Validator", df_names2["display"].tolist(), key="calc_val_pick")
        sel_validator = df_names2.loc[df_names2["display"] == selected_display, "validator"].iloc[0]
        sel_row = df_val[df_val["validator"] == sel_validator].iloc[0]

        amount = st.number_input(
            "Amount to stake (native token)",
            min_value=0.0, value=1000.0, step=10.0,
            help="Enter the amount of the chain's native token you plan to stake."
        )
        days = st.number_input("Duration (days)", min_value=1, value=30, step=1)
        apr_window = st.selectbox("APR window to use", ["Day", "Week", "Month"], index=1)
        compound = st.checkbox(
            "Compound daily",
            value=False,
            help="If enabled, compounds rewards daily using the APR window selected."
        )

    with calc_right:
        apr_map = {"Day": "_apr_day_num", "Week": "_apr_week_num", "Month": "_apr_month_num"}
        apr_pct = float(sel_row[apr_map[apr_window]])            # 0..100
        apr_dec = apr_pct / 100.0                                # 0..1
        commission_dec = float(sel_row["commission_raw"])        # 0..1
        effective_apr = apr_dec * (1.0 - commission_dec)         # assume APR is gross before commission

        # Reward math
        if compound:
            rewards = amount * ((1.0 + effective_apr / 365.0) ** days - 1.0)
        else:
            rewards = amount * effective_apr * (days / 365.0)

        total_end = amount + rewards

        st.metric("Chosen APR (gross)", f"{apr_pct:.2f}%")
        st.metric("Commission", f"{commission_dec*100:.2f}%")
        st.metric("Effective APR (net)", f"{effective_apr*100:.2f}%")
        st.metric("Projected Rewards", f"{rewards:,.4f}")
        st.metric("Projected Total Value", f"{total_end:,.4f}")

    # Compare the same stake across top validators (by adjusted stake)
    st.subheader("Compare the same stake across top validators")
    top_n_compare = st.slider("Compare Top N by stake", min_value=5, max_value=30, value=10, step=1, key="comp_topn")

    comp_df = df_val.copy()
    comp_df["stake_display"] = stake_adjusted_column(comp_df)
    comp_df = comp_df.sort_values("stake_display", ascending=False).head(top_n_compare).copy()

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
        title=f"Projected rewards for {int(days)} days on {int(amount):,} tokens "
              f"({apr_window} APR window, {'compounding' if compound else 'simple'})"
    )
    fig_comp.update_layout(yaxis_title="Projected rewards (tokens)", xaxis_title=None, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig_comp, use_container_width=True, theme="streamlit")

    st.caption("Notes: Rewards are estimates. APR and uptime can change. We assume predicted APR is gross and subtract commission to get net APR. Compounding is simulated daily.")

# ---------------------------
# Pie: Non-Foundation validator stake weights (net of foundation delegation)
# ---------------------------
st.subheader("🥧 Non-Foundation Validator Stake Weight (Net of Foundation Delegation)")

if df_val.empty:
    st.info("No validator data available for chart.")
else:
    chart_df = df_val.copy()

    # Filter out foundation validators
    chart_df = chart_df[~chart_df["is_foundation"]].copy()

    # Net stake calculation
    chart_df["net_stake"] = chart_df["stake"] - chart_df["foundationDelegation"]
    chart_df["net_stake"] = chart_df["net_stake"].clip(lower=0)  # avoid negatives

    if chart_df["net_stake"].sum() <= 0:
        st.warning("All net stakes are zero or negative after subtraction.")
    else:
        fig_net = px.pie(
            chart_df,
            names="name",
            values="net_stake",
            hole=0.45,
            title="Non-Foundation Validator Stake Weight (Net)",
            hover_data={
                "validator": True,
                "stake": True,
                "foundationDelegation": True,
                "net_stake": True
            }
        )
        fig_net.update_traces(textposition="inside", textinfo="percent+label")
        fig_net.update_layout(margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_net, use_container_width=True, theme="streamlit")
