"""
หุ้นต้นรอบ Scanner — Streamlit App v2
========================================
Logic:
  1. ขาลงยาวนาน: หา 52w Low → ย้อนหลัง 252 bars → อยู่ใต้ EMA200 (ยอมแฉลบ ±2%)
  2. ไม่สร้าง New Low: Close ปัจจุบัน > 52w Low อย่างน้อย 10%
  3. Break EMA200 แล้วยังไม่วิ่งไกล:
     - หาแท่งแรกที่ Break EMA200 (ย้อนจากปัจจุบัน)
     - Close ปัจจุบัน <= Break Price × (1 + X%)
"""

import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="หุ้นต้นรอบ Scanner", page_icon="🚀", layout="wide")

st.title("🚀 หุ้นต้นรอบ Scanner")
st.caption(f"อัพเดทล่าสุด: {datetime.now().strftime('%d %b %Y %H:%M')}")

# ══════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ ตั้งค่า")

    st.subheader("📁 ไฟล์รายชื่อหุ้น")
    uploaded_file = st.file_uploader(
        "อัพโหลดไฟล์ CSV (ต้องมีคอลัมน์ Symbol)", type=["csv"]
    )

    st.divider()
    st.subheader("🔧 Parameters")

    ema_period = st.number_input("EMA Period", min_value=50, max_value=500, value=200, step=10)

    st.markdown("**เงื่อนไขที่ 1 — ขาลงยาวนาน**")
    downtrend_bars = st.number_input(
        "นับย้อนหลังจาก 52w Low กี่ bars",
        min_value=100, max_value=500, value=252, step=10,
        help="252 bars = ~1 ปี"
    )
    buffer_pct = st.slider(
        "ยอมให้แฉลบเหนือ EMA200 ได้ (%)",
        min_value=0.0, max_value=10.0, value=2.0, step=0.5
    )

    st.markdown("**เงื่อนไขที่ 2 — ไม่สร้าง New Low**")
    min_above_low = st.slider(
        "Close > 52w Low อย่างน้อย (%)",
        min_value=1.0, max_value=50.0, value=10.0, step=1.0
    )

    st.markdown("**เงื่อนไขที่ 3 — Break EMA200 แล้วยังไม่วิ่งไกล**")
    max_run_pct = st.slider(
        "วิ่งจาก Break Price ได้ไม่เกิน (%)",
        min_value=5.0, max_value=100.0, value=25.0, step=5.0,
        help="ยิ่งน้อย = จับได้ Early มาก"
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
        st.sidebar.error("❌ ไม่พบคอลัมน์ 'Symbol'")

# ══════════════════════════════════════════════════════
#  SCAN FUNCTION
# ══════════════════════════════════════════════════════
def scan_symbol(symbol, ema_p, dt_bars, buf_pct, min_low, max_run):
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

        # ── เงื่อนไขที่ 1 ──────────────────────────────
        window_52w    = df.iloc[-252:]
        low_52w_idx   = window_52w["Close"].idxmin()
        low_52w_price = float(df.loc[low_52w_idx, "Close"])
        pos_of_low    = df.index.get_loc(low_52w_idx)
        start_pos     = pos_of_low - dt_bars
        if start_pos < 0:
            return None

        downtrend_window = df.iloc[start_pos:pos_of_low + 1]
        buffer = 1.0 + buf_pct / 100
        all_below = bool(
            (downtrend_window["Close"] <= downtrend_window["EMA200"] * buffer).all()
        )
        if not all_below:
            return None

        # ── เงื่อนไขที่ 2 ──────────────────────────────
        pct_above_low = (close_now - low_52w_price) / low_52w_price * 100
        if pct_above_low < min_low:
            return None

        # ── เงื่อนไขที่ 3 ──────────────────────────────
        # หาแท่งแรกที่ Break EMA200 ย้อนจากปัจจุบัน
        break_idx = None
        for i in range(len(df) - 1, pos_of_low, -1):
            if float(df["Close"].iloc[i]) > float(df["EMA200"].iloc[i]):
                break_idx = i
            else:
                if break_idx is not None:
                    break  # เจอแท่งแรกที่ Break แล้ว

        if break_idx is None:
            return None

        break_price = float(df["Close"].iloc[break_idx])
        max_price   = break_price * (1 + max_run / 100)

        if close_now > max_price:
            return None

        # ── ข้อมูลเพิ่มเติม ──────────────────────────
        pct_vs_ema      = (close_now - ema_now) / ema_now * 100
        pct_from_break  = (close_now - break_price) / break_price * 100
        bars_since_break = len(df) - 1 - break_idx

        return {
            "Symbol"           : symbol,
            "Close"            : round(close_now, 2),
            "EMA200"           : round(ema_now, 2),
            "vs EMA200 (%)"    : round(pct_vs_ema, 1),
            "Break Price"      : round(break_price, 2),
            "vs Break (%)"     : round(pct_from_break, 1),
            "Bars since Break" : bars_since_break,
            "52w Low"          : round(low_52w_price, 2),
            "vs 52wLow (%)"    : round(pct_above_low, 1),
            "TradingView"      : f"https://www.tradingview.com/chart/?symbol=SET:{symbol[:-3]}" if symbol.endswith(".BK") else f"https://www.tradingview.com/chart/?symbol={symbol}",
        }

    except Exception:
        return None

# ══════════════════════════════════════════════════════
#  MAIN
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
            min_above_low, max_run_pct
        )
        if result:
            results.append(result)

    progress_bar.progress(1.0, text="✅ Scan เสร็จแล้ว!")
    status_text.empty()

    st.subheader(f"📊 ผลลัพธ์: พบ {len(results)} หุ้น จาก {len(symbols)} ตัว")

    if results:
        # เรียงตาม Bars since Break น้อยสุด = Early ที่สุด
        df_result = pd.DataFrame(results).sort_values("Bars since Break")

        # ── Filter: เหนือ / ใต้ EMA200 ──────────────────
        st.markdown("**🔽 กรองผลลัพธ์**")
        filter_pos = st.radio(
            "แสดงเฉพาะหุ้นที่ตอนนี้อยู่",
            options=["ทั้งหมด", "เหนือ EMA200", "ใต้ EMA200"],
            horizontal=True
        )
        if filter_pos == "เหนือ EMA200":
            df_result = df_result[df_result["vs EMA200 (%)"] >= 0]
        elif filter_pos == "ใต้ EMA200":
            df_result = df_result[df_result["vs EMA200 (%)"] < 0]

        for _, row in df_result.iterrows():
            col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 2, 2, 2, 1])
            col1.metric("Symbol", row["Symbol"])
            col2.metric("Close", f"${row['Close']}", f"{row['vs EMA200 (%)']:+.1f}% vs EMA")
            col3.metric("Break Price", f"${row['Break Price']}", f"{row['vs Break (%)']:+.1f}% จาก Break")
            col4.metric("Bars since Break", f"{row['Bars since Break']} bars")
            col5.metric("vs 52w Low", f"{row['vs 52wLow (%)']:+.1f}%")
            col6.link_button("📈", row["TradingView"])
            st.divider()

        csv = df_result.drop(columns=["TradingView"]).to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="💾 ดาวน์โหลดผลลัพธ์ CSV",
            data=csv,
            file_name=f"tonrob_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.warning("ไม่พบหุ้นที่ผ่านเงื่อนไข ลองปรับ parameters ใน Sidebar ครับ")

elif scan_btn and not symbols:
    st.error("กรุณาอัพโหลดไฟล์ CSV ก่อนครับ")
