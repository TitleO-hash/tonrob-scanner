"""
หุ้นต้นรอบ Scanner — Streamlit App
=====================================
วิธีใช้:
  1. pip install streamlit yfinance pandas
  2. streamlit run tonrob_app.py
"""

import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# ══════════════════════════════════════════════════════
#  PAGE CONFIG
# ══════════════════════════════════════════════════════
st.set_page_config(
    page_title="หุ้นต้นรอบ Scanner",
    page_icon="🚀",
    layout="wide"
)

st.title("🚀 หุ้นต้นรอบ Scanner")
st.caption(f"อัพเดทล่าสุด: {datetime.now().strftime('%d %b %Y %H:%M')}")

# ══════════════════════════════════════════════════════
#  SIDEBAR — SETTINGS
# ══════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ ตั้งค่า")

    st.subheader("📁 ไฟล์รายชื่อหุ้น")
    uploaded_file = st.file_uploader(
        "อัพโหลดไฟล์ CSV (ต้องมีคอลัมน์ Symbol)",
        type=["csv"]
    )

    st.divider()
    st.subheader("🔧 Parameters")

    ema_period = st.number_input(
        "EMA Period", min_value=50, max_value=500, value=200, step=10
    )
    downtrend_bars = st.number_input(
        "เงื่อนไข 1: ขาลงนานกี่ bars (นับจาก 52w Low)",
        min_value=100, max_value=500, value=252, step=10,
        help="252 bars = ~1 ปี"
    )
    buffer_pct = st.slider(
        "เงื่อนไข 1: ยอมให้แฉลบเหนือ EMA200 (%)",
        min_value=0.0, max_value=10.0, value=2.0, step=0.5,
        help="ยอมให้ราคาขึ้นเกิน EMA200 ได้กี่ % ก็ยังถือว่าขาลง"
    )
    min_above_low = st.slider(
        "เงื่อนไข 2: Close > 52w Low อย่างน้อย (%)",
        min_value=1.0, max_value=50.0, value=10.0, step=1.0
    )
    recent_break_short = st.number_input(
        "เงื่อนไข 3.1: Break EMA200 ใน N bars ล่าสุด",
        min_value=5, max_value=60, value=20, step=5,
        help="~1 เดือน = 20 bars"
    )
    recent_break_long = st.number_input(
        "เงื่อนไข 3.2: Pullback หลัง Break ใน N bars ล่าสุด",
        min_value=20, max_value=120, value=60, step=5,
        help="~3 เดือน = 60 bars"
    )

    st.divider()
    scan_btn = st.button("🔍 เริ่ม Scan", type="primary", use_container_width=True)

# ══════════════════════════════════════════════════════
#  LOAD SYMBOLS
# ══════════════════════════════════════════════════════
symbols = []
if uploaded_file:
    df_sym = pd.read_csv(uploaded_file)
    if "Symbol" in df_sym.columns:
        symbols = df_sym["Symbol"].dropna().astype(str).str.strip().tolist()
        st.sidebar.success(f"โหลดได้ {len(symbols)} หุ้น ✅")
    else:
        st.sidebar.error("❌ ไม่พบคอลัมน์ 'Symbol' ในไฟล์")

# ══════════════════════════════════════════════════════
#  SCAN FUNCTION
# ══════════════════════════════════════════════════════
def scan_symbol(symbol, ema_p, dt_bars, buf_pct, min_low, rb_s, rb_l):
    try:
        df = yf.download(symbol, period="3y", interval="1d",
                         progress=False, auto_adjust=True)
        if df is None or len(df) < 252 + dt_bars + ema_p:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df["EMA200"] = df["Close"].ewm(span=ema_p, adjust=False).mean()
        df = df.dropna(subset=["EMA200"]).reset_index(drop=True)

        if len(df) < 252 + dt_bars:
            return None

        close_now = float(df["Close"].iloc[-1])
        ema_now   = float(df["EMA200"].iloc[-1])

        # เงื่อนไขที่ 1
        window_52w    = df.iloc[-252:]
        low_52w_idx   = window_52w["Close"].idxmin()
        low_52w_price = float(df.loc[low_52w_idx, "Close"])
        pos_of_low    = df.index.get_loc(low_52w_idx)
        start_pos     = pos_of_low - dt_bars
        if start_pos < 0:
            return None

        downtrend_window = df.iloc[start_pos:pos_of_low + 1]
        buffer           = 1.0 + buf_pct / 100
        all_below = bool(
            (downtrend_window["Close"] <= downtrend_window["EMA200"] * buffer).all()
        )
        if not all_below:
            return None

        # เงื่อนไขที่ 2
        pct_above_low = (close_now - low_52w_price) / low_52w_price * 100
        if pct_above_low < min_low:
            return None

        # เงื่อนไขที่ 3
        window_s = df.iloc[-rb_s:]
        window_l = df.iloc[-rb_l:]
        broke_s  = bool((window_s["Close"] > window_s["EMA200"]).any())
        broke_l  = bool((window_l["Close"] > window_l["EMA200"]).any())
        cond_31  = broke_s and close_now > ema_now
        cond_32  = broke_l and close_now < ema_now

        if not (cond_31 or cond_32):
            return None

        pct_vs_ema = (close_now - ema_now) / ema_now * 100
        case       = "3.1 Break เหนือ EMA" if cond_31 else "3.2 Pullback"

        return {
            "Symbol"        : symbol,
            "Case"          : case,
            "Close"         : round(close_now, 2),
            "EMA200"        : round(ema_now, 2),
            "vs EMA200 (%)" : round(pct_vs_ema, 1),
            "52w Low"       : round(low_52w_price, 2),
            "vs 52wLow (%)" : round(pct_above_low, 1),
            "TradingView"   : f"https://www.tradingview.com/chart/?symbol={symbol}",
        }
    except Exception:
        return None

# ══════════════════════════════════════════════════════
#  MAIN — RUN SCAN
# ══════════════════════════════════════════════════════
if not uploaded_file:
    st.info("👈 เริ่มต้นด้วยการอัพโหลดไฟล์ CSV รายชื่อหุ้นที่ Sidebar ครับ")

elif scan_btn and symbols:
    st.divider()
    progress_bar = st.progress(0, text="กำลังเริ่ม scan...")
    status_text  = st.empty()
    results      = []

    for i, symbol in enumerate(symbols):
        pct = (i + 1) / len(symbols)
        progress_bar.progress(pct, text=f"กำลัง scan {symbol} [{i+1}/{len(symbols)}]")
        status_text.text(f"⏳ {symbol}...")

        result = scan_symbol(
            symbol, ema_period, downtrend_bars, buffer_pct,
            min_above_low, recent_break_short, recent_break_long
        )
        if result:
            results.append(result)

    progress_bar.progress(1.0, text="✅ Scan เสร็จแล้ว!")
    status_text.empty()

    # ── แสดงผล ──────────────────────────────────────────
    st.subheader(f"📊 ผลลัพธ์: พบ {len(results)} หุ้น จาก {len(symbols)} ตัว")

    if results:
        df_result = pd.DataFrame(results)
        df_31 = df_result[df_result["Case"] == "3.1 Break เหนือ EMA"].sort_values("vs EMA200 (%)", ascending=False).reset_index(drop=True)
        df_32 = df_result[df_result["Case"] == "3.2 Pullback"].sort_values("vs 52wLow (%)", ascending=False).reset_index(drop=True)

        # Case 3.1
        st.markdown("### 📈 Case 3.1 — Break เหนือ EMA200")
        if len(df_31):
            for _, row in df_31.iterrows():
                col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 2])
                col1.metric("Symbol", row["Symbol"])
                col2.metric("Close", f"${row['Close']}")
                col3.metric("vs EMA200", f"{row['vs EMA200 (%)']:+.1f}%")
                col4.metric("vs 52w Low", f"{row['vs 52wLow (%)']:+.1f}%")
                col5.link_button("📈 ดูกราฟ", row["TradingView"])
                st.divider()
        else:
            st.info("ไม่พบหุ้นใน Case 3.1")

        # Case 3.2
        st.markdown("### 🔄 Case 3.2 — Pullback (อุดมคติ)")
        if len(df_32):
            for _, row in df_32.iterrows():
                col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 2])
                col1.metric("Symbol", row["Symbol"])
                col2.metric("Close", f"${row['Close']}")
                col3.metric("vs EMA200", f"{row['vs EMA200 (%)']:+.1f}%")
                col4.metric("vs 52w Low", f"{row['vs 52wLow (%)']:+.1f}%")
                col5.link_button("📈 ดูกราฟ", row["TradingView"])
                st.divider()
        else:
            st.info("ไม่พบหุ้นใน Case 3.2")

        # Download CSV
        csv = df_result.drop(columns=["TradingView"]).to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="💾 ดาวน์โหลดผลลัพธ์ CSV",
            data=csv,
            file_name=f"tonrob_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.warning("ไม่พบหุ้นที่ผ่านเงื่อนไขในวันนี้ ลองปรับ parameters ใน Sidebar ครับ")

elif scan_btn and not symbols:
    st.error("กรุณาอัพโหลดไฟล์ CSV ก่อนครับ")
