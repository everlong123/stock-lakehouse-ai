"""
Advanced Technical Indicators for Gold Layer

Bổ sung các indicators nâng cao:
- Volume Profile
- Candlestick Patterns
- Momentum Oscillators (Stochastic, CCI, Williams %R)
- Volatility Indicators (ATR, Keltner Channel)
- Trend Strength (ADX, Aroon)
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from app.indicators.service import IndicatorConfig


def add_advanced_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Add advanced technical indicators to the DataFrame."""
    result = frame.copy()
    close = result["close"]
    high = result["high"]
    low = result["low"]
    volume = result["volume"]
    
    # Momentum Oscillators
    result = pd.concat([result, stochastic_oscillator(high, low, close)], axis=1)
    result = pd.concat([result, cci(high, low, close)], axis=1)
    result = pd.concat([result, williams_r(high, low, close)], axis=1)
    
    # Volatility Indicators
    result = pd.concat([result, atr(high, low, close)], axis=1)
    result = pd.concat([result, keltner_channel(high, low, close)], axis=1)
    
    # Trend Strength
    result = pd.concat([result, adx(high, low, close)], axis=1)
    result = pd.concat([result, aroon(high, low)], axis=1)
    
    # Volume Indicators
    result = pd.concat([result, obv(volume, close)], axis=1)
    result = pd.concat([result, vwap(high, low, close, volume)], axis=1)
    result = pd.concat([result, mfi(high, low, close, volume)], axis=1)
    
    # Price-based Features
    result = pd.concat([result, ichimoku(high, low, close)], axis=1)
    result = pd.concat([result, supertrend(high, low, close)], axis=1)
    
    return result


# ─── Momentum Oscillators ────────────────────────────────────────────────────────


def stochastic_oscillator(
    high: pd.Series, 
    low: pd.Series, 
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3
) -> pd.DataFrame:
    """Stochastic Oscillator %K and %D."""
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    
    stoch_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    stoch_d = stoch_k.rolling(window=d_period).mean()
    
    return pd.DataFrame({
        "stoch_k": stoch_k,
        "stoch_d": stoch_d,
    })


def cci(
    high: pd.Series, 
    low: pd.Series, 
    close: pd.Series,
    period: int = 20
) -> pd.DataFrame:
    """Commodity Channel Index."""
    typical_price = (high + low + close) / 3
    sma_tp = typical_price.rolling(window=period).mean()
    mean_deviation = typical_price.rolling(window=period).apply(
        lambda x: np.mean(np.abs(x - np.mean(x))), raw=True
    )
    
    cci = (typical_price - sma_tp) / (0.015 * mean_deviation)
    
    return pd.DataFrame({"cci": cci})


def williams_r(
    high: pd.Series, 
    low: pd.Series, 
    close: pd.Series,
    period: int = 14
) -> pd.DataFrame:
    """Williams %R."""
    highest_high = high.rolling(window=period).max()
    lowest_low = low.rolling(window=period).min()
    
    wr = -100 * (highest_high - close) / (highest_high - lowest_low)
    
    return pd.DataFrame({"williams_r": wr})


# ─── Volatility Indicators ──────────────────────────────────────────────────────


def atr(
    high: pd.Series, 
    low: pd.Series, 
    close: pd.Series,
    period: int = 14
) -> pd.DataFrame:
    """Average True Range."""
    high_low = high - low
    high_close = np.abs(high - close.shift())
    low_close = np.abs(low - close.shift())
    
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()
    
    return pd.DataFrame({"atr": atr, "atr_percent": atr / close * 100})


def keltner_channel(
    high: pd.Series, 
    low: pd.Series, 
    close: pd.Series,
    period: int = 20,
    multiplier: float = 2.0
) -> pd.DataFrame:
    """Keltner Channel."""
    ema_close = close.ewm(span=period, adjust=False).mean()
    true_range = pd.concat([
        high - low,
        np.abs(high - close.shift()),
        np.abs(low - close.shift())
    ], axis=1).max(axis=1)
    atr = true_range.ewm(span=period, adjust=False).mean()
    
    kc_upper = ema_close + multiplier * atr
    kc_lower = ema_close - multiplier * atr
    kc_middle = ema_close
    
    return pd.DataFrame({
        "kc_upper": kc_upper,
        "kc_middle": kc_middle,
        "kc_lower": kc_lower,
        "kc_width": (kc_upper - kc_lower) / kc_middle * 100,
    })


# ─── Trend Strength ─────────────────────────────────────────────────────────────


def adx(
    high: pd.Series, 
    low: pd.Series, 
    close: pd.Series,
    period: int = 14
) -> pd.DataFrame:
    """Average Directional Index."""
    high_diff = high.diff()
    low_diff = -low.diff()
    
    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)
    
    tr1 = high - low
    tr2 = np.abs(high - close.shift())
    tr3 = np.abs(low - close.shift())
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr = true_range.rolling(window=period).mean()
    
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
    
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean()
    
    return pd.DataFrame({
        "adx": adx,
        "plus_di": plus_di,
        "minus_di": minus_di,
    })


def aroon(high: pd.Series, low: pd.Series, period: int = 25) -> pd.DataFrame:
    """Aroon Indicator."""
    aroon_up = high.rolling(window=period + 1).apply(
        lambda x: float(np.argmax(x)) / period * 100, raw=True
    )
    aroon_down = low.rolling(window=period + 1).apply(
        lambda x: float(np.argmin(x)) / period * 100, raw=True
    )
    aroon_oscillator = aroon_up - aroon_down
    
    return pd.DataFrame({
        "aroon_up": aroon_up,
        "aroon_down": aroon_down,
        "aroon_osc": aroon_oscillator,
    })


# ─── Volume Indicators ──────────────────────────────────────────────────────────


def obv(volume: pd.Series, close: pd.Series) -> pd.DataFrame:
    """On-Balance Volume."""
    obv_values = [0]
    for i in range(1, len(close)):
        if close.iloc[i] > close.iloc[i - 1]:
            obv_values.append(obv_values[-1] + volume.iloc[i])
        elif close.iloc[i] < close.iloc[i - 1]:
            obv_values.append(obv_values[-1] - volume.iloc[i])
        else:
            obv_values.append(obv_values[-1])
    
    return pd.DataFrame({
        "obv": obv_values,
        "obv_change": pd.Series(obv_values).pct_change(),
    })


def vwap(
    high: pd.Series, 
    low: pd.Series, 
    close: pd.Series, 
    volume: pd.Series
) -> pd.DataFrame:
    """Volume Weighted Average Price."""
    typical_price = (high + low + close) / 3
    vwap = (typical_price * volume).cumsum() / volume.cumsum()
    
    return pd.DataFrame({
        "vwap": vwap,
        "vwap_deviation": (close - vwap) / vwap * 100,
    })


def mfi(
    high: pd.Series, 
    low: pd.Series, 
    close: pd.Series, 
    volume: pd.Series,
    period: int = 14
) -> pd.DataFrame:
    """Money Flow Index."""
    typical_price = (high + low + close) / 3
    money_flow = typical_price * volume
    
    positive_flow = money_flow.where(typical_price > typical_price.shift(), 0)
    negative_flow = money_flow.where(typical_price < typical_price.shift(), 0)
    
    positive_mf = positive_flow.rolling(window=period).sum()
    negative_mf = negative_flow.rolling(window=period).sum()
    
    mfi = 100 - (100 / (1 + positive_mf / negative_mf))
    
    return pd.DataFrame({"mfi": mfi})


# ─── Trend Detection ────────────────────────────────────────────────────────────


def ichimoku(
    high: pd.Series, 
    low: pd.Series, 
    close: pd.Series,
    tenkan_period: int = 9,
    kijun_period: int = 26,
    senkou_b_period: int = 52
) -> pd.DataFrame:
    """Ichimoku Cloud components."""
    tenkan_sen = (high.rolling(window=tenkan_period).max() + 
                  low.rolling(window=tenkan_period).min()) / 2
    kijun_sen = (high.rolling(window=kijun_period).max() + 
                 low.rolling(window=kijun_period).min()) / 2
    
    senkou_a = (tenkan_sen + kijun_sen) / 2
    senkou_b = (high.rolling(window=senkou_b_period).max() + 
                low.rolling(window=senkou_b_period).min()) / 2
    
    chikou_span = close.shift(-kijun_period)
    
    return pd.DataFrame({
        "ichimoku_tenkan": tenkan_sen,
        "ichimoku_kijun": kijun_sen,
        "ichimoku_senkou_a": senkou_a,
        "ichimoku_senkou_b": senkou_b,
        "ichimoku_chikou": chikou_span,
    })


def supertrend(
    high: pd.Series, 
    low: pd.Series, 
    close: pd.Series,
    period: int = 10,
    multiplier: float = 3.0
) -> pd.DataFrame:
    """Supertrend Indicator."""
    atr_values = atr(high, low, close, period)["atr"]
    
    hl2 = (high + low) / 2
    upper_band = hl2 + multiplier * atr_values
    lower_band = hl2 - multiplier * atr_values
    
    supertrend = [0] * len(close)
    direction = [1] * len(close)  # 1 = uptrend, -1 = downtrend
    
    for i in range(1, len(close)):
        if close.iloc[i] > upper_band.iloc[i - 1]:
            direction[i] = 1
        elif close.iloc[i] < lower_band.iloc[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]
            if direction[i] == 1 and lower_band.iloc[i] < lower_band.iloc[i - 1]:
                lower_band.iloc[i] = lower_band.iloc[i - 1]
            elif direction[i] == -1 and upper_band.iloc[i] > upper_band.iloc[i - 1]:
                upper_band.iloc[i] = upper_band.iloc[i - 1]
        
        if direction[i] == 1:
            supertrend[i] = lower_band.iloc[i]
        else:
            supertrend[i] = upper_band.iloc[i]
    
    return pd.DataFrame({
        "supertrend": supertrend,
        "trend_direction": direction,
    })


# ─── Pattern Recognition ───────────────────────────────────────────────────────


def detect_candlestick_patterns(
    open_prices: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series
) -> pd.DataFrame:
    """Detect common candlestick patterns."""
    body = close - open_prices
    body_size = np.abs(body)
    range_size = high - low
    upper_shadow = high - np.maximum(open_prices, close)
    lower_shadow = np.minimum(open_prices, close) - low
    
    # Large body patterns
    large_body = body_size > body_size.rolling(20).median()
    
    # Doji (small body)
    doji = body_size < range_size * 0.1
    
    # Hammer (bullish reversal)
    hammer = (
        (lower_shadow > body_size * 2) &
        (upper_shadow < body_size * 0.3) &
        (body > 0)
    )
    
    # Shooting star (bearish reversal)
    shooting_star = (
        (upper_shadow > body_size * 2) &
        (lower_shadow < body_size * 0.3) &
        (body < 0)
    )
    
    # Engulfing patterns
    bullish_engulfing = (
        (body.iloc[:-1] < 0) &  # Previous was bearish
        (body > 0) &  # Current is bullish
        (close > open_prices.shift(1)) &
        (open_prices < close.shift(1))
    )
    
    bearish_engulfing = (
        (body.iloc[:-1] > 0) &  # Previous was bullish
        (body < 0) &  # Current is bearish
        (close < open_prices.shift(1)) &
        (open_prices > close.shift(1))
    )
    
    return pd.DataFrame({
        "candle_doji": doji.astype(int),
        "candle_hammer": hammer.astype(int),
        "candle_shooting_star": shooting_star.astype(int),
        "candle_bullish_engulfing": bullish_engulfing.reindex(open_prices.index, fill_value=0).astype(int),
        "candle_bearish_engulfing": bearish_engulfing.reindex(open_prices.index, fill_value=0).astype(int),
        "candle_large_body": large_body.astype(int),
    })


def add_candlestick_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add candlestick pattern features."""
    patterns = detect_candlestick_patterns(
        frame["open"],
        frame["high"],
        frame["low"],
        frame["close"]
    )
    return pd.concat([frame, patterns], axis=1)


# ─── Volume Profile Features ────────────────────────────────────────────────────


def add_volume_profile_features(frame: pd.DataFrame, bins: int = 20) -> pd.DataFrame:
    """Add volume profile features."""
    result = frame.copy()
    
    # Volume bins (VWAP zones)
    typical_price = (result["high"] + result["low"] + result["close"]) / 3
    
    # Volume moving average
    result["volume_ma_5"] = result["volume"].rolling(5).mean()
    result["volume_ma_20"] = result["volume"].rolling(20).mean()
    result["volume_ratio"] = result["volume"] / result["volume_ma_20"]
    
    # Volume spike detection
    result["volume_spike"] = (result["volume"] > result["volume"].rolling(20).mean() * 2).astype(int)
    
    # Price in range
    result["price_in_range"] = (result["close"] - result["low"]) / (result["high"] - result["low"] + 1e-10)
    
    # VWAP position
    vwap = (typical_price * result["volume"]).cumsum() / result["volume"].cumsum()
    result["vwap_position"] = (result["close"] - vwap) / vwap * 100
    
    # POC (Point of Control) - simplified
    result["poc_proximity"] = np.abs(result["close"] - result["close"].rolling(20).mean()) / result["close"].rolling(20).std()
    
    return result


# ─── Composite Signals ─────────────────────────────────────────────────────────


def add_composite_signals(frame: pd.DataFrame) -> pd.DataFrame:
    """Add composite trading signals."""
    result = frame.copy()
    
    # Trend signal (combined SMA)
    sma_trend = (
        (result["close"] > result["sma_20"]) &
        (result["sma_20"] > result["sma_50"])
    ).astype(int) - (
        (result["close"] < result["sma_20"]) &
        (result["sma_20"] < result["sma_50"])
    ).astype(int)
    
    # RSI signal
    rsi_signal = (
        (result["rsi_14"] < 30).astype(int) * 1 +  # Oversold = buy
        (result["rsi_14"] > 70).astype(int) * -1   # Overbought = sell
    )
    
    # MACD signal
    macd_signal = (
        (result["macd"] > result["macd_signal"]).astype(int) * 1 +
        (result["macd"] < result["macd_signal"]).astype(int) * -1
    )
    
    # Combined momentum
    result["momentum_signal"] = (sma_trend + rsi_signal + macd_signal) / 3
    
    # Trend strength classification
    result["trend_strength"] = np.where(
        result.get("adx", pd.Series([50] * len(result))) > 25,
        np.where(result["close"] > result["sma_20"], "strong_uptrend", "strong_downtrend"),
        np.where(result["close"] > result["sma_20"], "weak_uptrend", "weak_downtrend")
    )
    
    return result
