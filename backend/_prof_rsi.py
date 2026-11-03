import pandas as pd, numpy as np, sys
print("pandas", pd.__version__)

def rsi(series, period=14):
    close = series.astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    result = result.mask(avg_loss.eq(0) & avg_gain.gt(0), 100.0)
    result = result.mask(avg_gain.eq(0) & avg_loss.gt(0), 0.0)
    return result.astype(float)

# simulate a flat/edge series where RSI hits exactly the thresholds
close = pd.Series([100.0]*30 + [95.0]*30 + [105.0]*30)
frame = pd.DataFrame({"close": close})
values = rsi(frame["close"], 14)
signal = pd.Series(0, index=frame.index, dtype=float)
signal.loc[values < 30] = 1
signal.loc[values > 70] = -1
previous = signal.replace(0, pd.NA).ffill().shift(1)
print("previous dtype:", previous.dtype)
print("previous head:", previous.head(20).tolist())
try:
    crossings = signal.where(signal != previous, 0).fillna(0)
    print("OK crossings:", crossings.value_counts().to_dict())
except Exception as e:
    print("REPRO:", type(e).__name__, e)
