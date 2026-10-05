"""Replace _extract_symbol with noise-aware version."""

from pathlib import Path

p = Path("app/agent/agent.py")
content = p.read_text(encoding="utf-8")

OLD = '''def _extract_symbol(text: str, default_symbol: str | None) -> str:
    upper = text.upper()
    for symbol in SUPPORTED_SYMBOLS:
        if re.search(rf"\\b{symbol}\\b", upper):
            return symbol
    match = re.search(r"\\b([A-Z]{1,5})\\b", upper)
    if match and match.group(1) not in {"RSI", "MACD", "SMA", "EMA", "LSTM", "MA"}:
        return match.group(1)
    return (default_symbol or "AAPL").upper()'''

NEW = '''def _extract_symbol(text: str, default_symbol: str | None) -> str:
    """Extract ticker from a Vietnamese / English user question.

    Strategy:
    1. Match against SUPPORTED_SYMBOLS first (highest confidence).
    2. Fallback: scan all 2-5 char uppercase tokens, skip common Vietnamese
       syllables and indicator / model names to avoid mis-extraction.
       Example: "PHAN tich VCB" should resolve to VCB, not PHAN.
    """
    upper = text.upper()

    # 1. Exact match against known symbols
    for symbol in SUPPORTED_SYMBOLS:
        if re.search(rf"\\b{symbol}\\b", upper):
            return symbol

    # 2. Fallback with noise filter
    NOISE = {
        # Vietnamese syllables without diacritics
        "PHAN", "TICH", "PHANTICH", "THANG", "NAM", "NGAY", "TUAN",
        "GAN", "NHAT", "QUA", "MOT", "HAI", "BA", "BON", "TAM",
        "TU", "SAU", "BAY", "CHIN", "MUOI",
        "CHO", "CO", "TOI", "BAN", "MINH", "EM",
        # Technical indicators / models
        "RSI", "MACD", "SMA", "EMA", "LSTM", "ARIMA", "MA", "BB",
        "ATR", "ADX", "OBV", "VWAP", "STOCH",
    }
    tokens = re.findall(r"\\b[A-Z]{2,5}\\b", upper)
    for token in tokens:
        if token not in NOISE:
            return token

    return (default_symbol or "AAPL").upper()'''

if OLD not in content:
    print("ERROR: OLD block not found exactly")
    raise SystemExit(1)

new_content = content.replace(OLD, NEW, 1)
p.write_text(new_content, encoding="utf-8")
print("OK replaced _extract_symbol")