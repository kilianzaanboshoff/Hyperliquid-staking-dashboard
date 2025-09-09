import streamlit as st
import requests
import pandas as pd
import plotly.express as px

API_URL = "https://api.hyperliquid.xyz/info"
HEADERS = {"Content-Type": "application/json"}

# =========================
# Static Foundation Delegations (TOKENS, not base units)
# =========================
FOUNDATION_DELEGATIONS = {
    "0x5ac99df645f3414876c816caa18b2d234024b487": 0,
    "0xdf35aee8ef5658686142acd1e5ab5dbcdf8c51e8": 0,
    "0x80f0cd23da5bf3a0101110cfd0f89c8a69a1384d": 0,
    "0xa82fe73bbd768bc15d1ef2f6142a21ff8bd762ad": 0,
    "0xb8f45222a3246a2b0104696a1df26842007c5bc5": 19563823,
    "0xabcdeff4b3727b83a23697500eef089020df2cd2": 33090774,
    "0xa23b4556090260828ff3f939d2dbdd4f318b5f1f": 18557470,
    "0x66be52ec79f829cc88e5778a255e2cb9492798fd": 0,
    "0x8b8c3966870321866e7b7091c382308a6a97e9b1": 0,
    "0xe45c96a6a32318e5df7347477963bf0de38ff7ff": 6315670,
    "0x3e5b2598a32ebf003ad5a7254faa3d04ff41d9fe": 2165992,
    "0x8a5dbdf69b282bf2e8fb9f29fd34891f79c5dfd4": 9029617,
    "0xeeee86f718f9da3e7250624a460f6ea710e9c006": 3165001,
    "0x000000000056f99d36b6f2e0c51fd41496bbacb8": 6315874,
    "0x48f1da3e3ec2814fbb3dcf57125001089b067402": 7315940,
    "0x4e256d24da830290d10f425b44f3e9439394385a": 3150001,
    "0xf8efb4cb844a8458114994203d7b0bfe2422a288": 2166001,
    "0x15458aed3c7a49b215fbfa863c6ff550c31e1a31": 6315724,
    "0x65baa675fa9e5f6c7ae4541ebdb16c526de06f1f": 6315942,
    "0x8f02ade62c1c1cf34daa855ccf1245aaf90d3056": 0,
    "0x497beec89958848126c2ea65934ce430e1410ad2": 0,
    "0xb00c116f72eb55f52ca80196b63014a42cc72de1": 2150000,
    "0x30c66ebc7f5ef4f340b424a26e4d944f60129815": 0,
    "0xc75a3fc98b0e1af7a95b6a720adf2e23806d2c7b": 0,
}

STAKE_DIVISOR = 1e8  # convert API base units -> tokens

# =========================
# Helpers
# =========================
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

# =========================
# Page config
# =========================
st.set_page_config(page_title="Hyperliquid Non-Foundation Stake", layout="wide")
st.title("🧭 Hyperliquid — Active Non-Foundation Stake")

# =========================
# Fetch & normalize
# =========================
with st.spinner("Fetching validator summaries…"):
    try:
        validators = fetch_validator_summaries()
    except Exception as e:
        st.error(f"Failed to fetch validator summaries: {e}")
        st.stop()

rows = []
if isinstance(validators, list):
    for v in validators:
        stats = norm_stats(v.get("stats", []))
        day = stats.get("day", {})
        rows.append({
            "validator": v.get("validator"),
            "name": v.get("name") or "(unnamed)",
            "description": v.get("description", ""),
            "isActive": bool(v.get("isActive")),
            "isJailed": bool(v.get("isJailed")),
            "stake_raw": pd.to_numeric(v.get("stake", 0), errors="coerce"),  # base units
            "uptime_day": fmt_pct(day.get("uptimeFraction", 0)),
        })

df = pd.DataFrame(rows)

# Convert stake to TOKENS
df["stake_tokens"] = (df["stake_raw"].fillna(0) / STAKE_DIVISOR).astype(float)

# Keep Active, Non-Foundation only (exclude names containing "foundation")
df_nf = df[
    (df["isActive"] == True) &
    (~df["name"].str.contains("foundation", case=False, na=False))
].copy()

if df_nf.empty:
    st.info("No active non-foundation validators found.")
    st.stop()

# Attach static Foundation delegation (tokens) and compute net (tokens)
df_nf["foundationDelegation_tokens"] = df_nf["validator"].map(FOUNDATION_DELEGATIONS).fillna(0).astype(float)
df_nf["net_stake_tokens"] = (df_nf["stake_tokens"] - df_nf["foundationDelegation_tokens"]).clip(lower=0)

# =========================
# Charts
# =========================
st.subheader("🥧 Active Non-Foundation Stake Distribution (Raw)")
fig_raw = px.pie(
    df_nf.sort_values("stake_tokens", ascending=False),
    names="name",
    values="stake_tokens",
    hover_data={"validator": True, "stake_tokens": ":,"},
)
fig_raw.update_traces(textposition="inside", textinfo="percent+label")
fig_raw.update_layout(margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(fig_raw, use_container_width=True)

st.subheader("🥧 Active Non-Foundation Stake Distribution (Net of Foundation Delegations)")
df_net = df_nf[df_nf["net_stake_tokens"] > 0].sort_values("net_stake_tokens", ascending=False)

if df_net.empty:
    st.info("After subtracting Foundation delegations, no non-foundation stake remains.")
else:
    fig_net = px.pie(
        df_net,
        names="name",
        values="net_stake_tokens",
        hover_data={
            "validator": True,
            "stake_tokens": ":,",
            "foundationDelegation_tokens": ":,",
            "net_stake_tokens": ":,"
        },
    )
    fig_net.update_traces(textposition="inside", textinfo="percent+label")
    fig_net.update_layout(margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_net, use_container_width=True)

# =========================
# Table
# =========================
st.subheader("📋 Active Non-Foundation Validators")
show_cols = [
    "name", "validator",
    "stake_tokens", "foundationDelegation_tokens", "net_stake_tokens",
    "isJailed", "uptime_day"
]

# Pretty formatting
df_show = df_nf[show_cols].copy()
for col in ["stake_tokens", "foundationDelegation_tokens", "net_stake_tokens"]:
    df_show[col] = pd.to_numeric(df_show[col], errors="coerce").fillna(0.0)

st.dataframe(
    df_show.sort_values("net_stake_tokens", ascending=False),
    use_container_width=True,
    height=540
)

st.caption(
    "Notes: API stake is divided by 1e8 to convert to tokens. "
    "Net = stake_tokens − foundationDelegation_tokens. "
    "Foundation delegation values are static by validator address."
)
