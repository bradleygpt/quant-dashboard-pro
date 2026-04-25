"""
Pro Charts Module
Professional Plotly candlestick charting plus live monitoring features.

Components:
1. Candlestick chart with VWAP, EMAs, volume, RSI subplot
2. Live watchlist monitor (auto-refresh, key metrics)
3. Pre-market / post-market indicators
4. Multi-timeframe analysis
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf


def fetch_chart_data(ticker, period="3mo", interval="1d"):
    """Fetch OHLCV data for the chart."""
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval, auto_adjust=False)
        return df if not df.empty else None
    except Exception:
        return None


def compute_indicators(df):
    """Compute technical indicators on OHLCV data."""
    if df is None or df.empty:
        return df

    df = df.copy()

    # EMAs
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()

    # VWAP (cumulative)
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    cumulative_vp = (typical_price * df["Volume"]).cumsum()
    cumulative_vol = df["Volume"].cumsum()
    df["VWAP"] = cumulative_vp / cumulative_vol

    # RSI (14)
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    sma20 = df["Close"].rolling(20).mean()
    std20 = df["Close"].rolling(20).std()
    df["BB_upper"] = sma20 + 2 * std20
    df["BB_lower"] = sma20 - 2 * std20
    df["BB_mid"] = sma20

    # Average volume
    df["Vol_avg20"] = df["Volume"].rolling(20).mean()

    return df


def build_candlestick_chart(df, ticker, show_vwap=True, show_emas=True, show_bb=False, show_volume=True, show_rsi=True):
    """
    Build a professional candlestick chart with optional indicators.
    Returns a Plotly figure.
    """
    if df is None or df.empty:
        return None

    # Determine subplot rows
    rows = 1
    row_heights = [1.0]
    if show_volume:
        rows += 1
        row_heights.append(0.2)
    if show_rsi:
        rows += 1
        row_heights.append(0.2)

    if rows == 1:
        row_heights = [1.0]
    else:
        # Main chart should be 60-70%
        main_h = 0.7 if rows == 3 else 0.8
        rest = (1.0 - main_h) / (rows - 1)
        row_heights = [main_h] + [rest] * (rows - 1)

    fig = make_subplots(
        rows=rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=row_heights,
    )

    # ── Candlesticks (main chart) ──
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name=ticker,
            increasing=dict(line=dict(color="#22C55E"), fillcolor="#22C55E"),
            decreasing=dict(line=dict(color="#EF4444"), fillcolor="#EF4444"),
            showlegend=False,
        ),
        row=1, col=1,
    )

    # ── EMAs / SMAs ──
    if show_emas:
        if "EMA9" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["EMA9"], mode="lines",
                name="EMA9", line=dict(color="#FBBF24", width=1)), row=1, col=1)
        if "EMA21" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["EMA21"], mode="lines",
                name="EMA21", line=dict(color="#F97316", width=1.2)), row=1, col=1)
        if "SMA50" in df.columns and df["SMA50"].notna().any():
            fig.add_trace(go.Scatter(x=df.index, y=df["SMA50"], mode="lines",
                name="SMA50", line=dict(color="#00A3FF", width=1, dash="dot")), row=1, col=1)
        if "SMA200" in df.columns and df["SMA200"].notna().any():
            fig.add_trace(go.Scatter(x=df.index, y=df["SMA200"], mode="lines",
                name="SMA200", line=dict(color="#A855F7", width=1, dash="dot")), row=1, col=1)

    # ── VWAP ──
    if show_vwap and "VWAP" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["VWAP"], mode="lines",
            name="VWAP", line=dict(color="#00D4AA", width=1.5)), row=1, col=1)

    # ── Bollinger Bands ──
    if show_bb and "BB_upper" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["BB_upper"], mode="lines",
            name="BB Upper", line=dict(color="#666", width=1, dash="dash"),
            showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["BB_lower"], mode="lines",
            name="BB Lower", line=dict(color="#666", width=1, dash="dash"),
            fill="tonexty", fillcolor="rgba(102,102,102,0.1)",
            showlegend=False), row=1, col=1)

    # ── Volume subplot ──
    current_row = 2 if show_volume else None
    if show_volume:
        # Color volume bars by candle direction
        colors = ["#22C55E" if df["Close"].iloc[i] >= df["Open"].iloc[i] else "#EF4444"
                  for i in range(len(df))]
        fig.add_trace(
            go.Bar(x=df.index, y=df["Volume"], name="Volume",
                marker_color=colors, opacity=0.6, showlegend=False),
            row=current_row, col=1,
        )
        if "Vol_avg20" in df.columns:
            fig.add_trace(
                go.Scatter(x=df.index, y=df["Vol_avg20"], mode="lines",
                    name="20-day Avg Volume", line=dict(color="#FBBF24", width=1.5),
                    showlegend=False),
                row=current_row, col=1,
            )

    # ── RSI subplot ──
    if show_rsi and "RSI" in df.columns:
        rsi_row = (3 if show_volume else 2)
        fig.add_trace(
            go.Scatter(x=df.index, y=df["RSI"], mode="lines",
                name="RSI", line=dict(color="#A855F7", width=1.5),
                showlegend=False),
            row=rsi_row, col=1,
        )
        # Overbought / oversold lines
        fig.add_hline(y=70, line_dash="dot", line_color="#EF4444", opacity=0.5, row=rsi_row, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#22C55E", opacity=0.5, row=rsi_row, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color="#666", opacity=0.3, row=rsi_row, col=1)

    # ── Layout ──
    fig.update_layout(
        height=800 if rows == 3 else (650 if rows == 2 else 500),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e0e0e0"),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="top", y=1.05, xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=60, r=60, t=40, b=40),
        hovermode="x unified",
    )

    # Style all axes
    for i in range(1, rows + 1):
        fig.update_xaxes(gridcolor="#2a2f3e", showgrid=True, row=i, col=1)
        fig.update_yaxes(gridcolor="#2a2f3e", showgrid=True, row=i, col=1)

    # Y-axis titles
    fig.update_yaxes(title_text="Price ($)", tickformat="$,.2f", row=1, col=1)
    if show_volume:
        fig.update_yaxes(title_text="Volume", row=2, col=1)
    if show_rsi:
        rsi_row = 3 if show_volume else 2
        fig.update_yaxes(title_text="RSI", range=[0, 100], row=rsi_row, col=1)

    return fig


def get_quick_quote(ticker):
    """Get current price snapshot with key intraday metrics."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        hist = t.history(period="5d", interval="1d")
        if hist.empty:
            return None

        current = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
        day_high = float(hist["High"].iloc[-1])
        day_low = float(hist["Low"].iloc[-1])
        day_open = float(hist["Open"].iloc[-1])
        volume = float(hist["Volume"].iloc[-1])
        avg_vol = float(hist["Volume"].mean())

        change = current - prev_close
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0

        # Compute intraday VWAP from 1-day intraday data if possible
        try:
            intraday = t.history(period="1d", interval="5m")
            if not intraday.empty:
                tp = (intraday["High"] + intraday["Low"] + intraday["Close"]) / 3
                vwap = float((tp * intraday["Volume"]).sum() / intraday["Volume"].sum()) if intraday["Volume"].sum() > 0 else current
                vs_vwap_pct = (current - vwap) / vwap * 100 if vwap > 0 else 0
            else:
                vwap = None
                vs_vwap_pct = None
        except Exception:
            vwap = None
            vs_vwap_pct = None

        # Day range position (0=at low, 100=at high)
        day_range_pos = ((current - day_low) / (day_high - day_low) * 100) if day_high > day_low else 50

        # Volume vs average
        rel_volume = (volume / avg_vol * 100) if avg_vol > 0 else 100

        return {
            "ticker": ticker,
            "name": info.get("shortName", ticker),
            "price": round(current, 2),
            "prev_close": round(prev_close, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "day_open": round(day_open, 2),
            "day_high": round(day_high, 2),
            "day_low": round(day_low, 2),
            "day_range_pos": round(day_range_pos, 1),
            "volume": int(volume),
            "avg_volume": int(avg_vol),
            "rel_volume_pct": round(rel_volume, 1),
            "vwap": round(vwap, 2) if vwap else None,
            "vs_vwap_pct": round(vs_vwap_pct, 2) if vs_vwap_pct is not None else None,
        }
    except Exception:
        return None


def get_watchlist_quotes(tickers):
    """Get quotes for a list of tickers (for live watchlist view)."""
    quotes = []
    for t in tickers:
        q = get_quick_quote(t)
        if q:
            quotes.append(q)
    return quotes


def get_market_movers(scored_df, top_n=10):
    """Identify today's biggest movers from the scored universe."""
    try:
        if "momentum_1m" not in scored_df.columns:
            return {"gainers": [], "losers": []}

        # Sort by 1-day or 1-week momentum
        df = scored_df[scored_df["sector"] != "ETF"].copy()
        df = df.dropna(subset=["momentum_1m"])
        df["m_1m_pct"] = df["momentum_1m"] * 100

        gainers = df.nlargest(top_n, "m_1m_pct")[["shortName", "sector", "m_1m_pct", "composite_score", "overall_rating", "marketCapB"]]
        losers = df.nsmallest(top_n, "m_1m_pct")[["shortName", "sector", "m_1m_pct", "composite_score", "overall_rating", "marketCapB"]]

        return {
            "gainers": gainers.reset_index().to_dict("records"),
            "losers": losers.reset_index().to_dict("records"),
        }
    except Exception:
        return {"gainers": [], "losers": []}
