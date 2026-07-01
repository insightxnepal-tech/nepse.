# src/analyze_stocks.py
"""Analyze all stock CSV files and generate simple buy/sell signals.

The script reads each CSV in `data/company-wise/`, computes short (5‑day) and long (20‑day)
simple moving averages (SMA) on the closing price, and decides a signal based on the
relationship between the SMAs and the latest close price.

Signal logic:
- **Buy**  – 5‑day SMA > 20‑day SMA AND latest close > 5‑day SMA
- **Sell** – 5‑day SMA < 20‑day SMA AND latest close < 5‑day SMA
- **Hold** – otherwise

Results are written to `data/analysis/recommendations.csv` with columns:
`Company, LatestClose, SMA_5, SMA_20, Signal`.
"""

import pandas as pd
from pathlib import Path
from constants.companyIdMap import companyIdMap

# Directory containing per‑company CSV files
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "company-wise"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "analysis"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

results = []

for symbol, _ in companyIdMap.items():
    csv_path = DATA_DIR / f"{symbol}.csv"
    if not csv_path.is_file():
        continue
# Read CSV with header row and normalize column names
    df = pd.read_csv(csv_path)
    # Standardize column names to lower case
    df.columns = [c.lower() for c in df.columns]
    # Ensure numeric columns are correct type
    numeric_cols = ["open", "high", "low", "close", "per_change", "traded_quantity", "traded_amount"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # Parse dates and sort
    df["published_date"] = pd.to_datetime(df["published_date"], errors="coerce")
    df = df.sort_values("published_date")
    # Compute SMAs on close price
    df["sma_5"] = df["close"].rolling(window=5).mean()
    df["sma_20"] = df["close"].rolling(window=20).mean()
    latest = df.iloc[-1]
    sma_5 = latest["sma_5"]
    sma_20 = latest["sma_20"]
    close = latest["close"]
    if pd.notna(sma_5) and pd.notna(sma_20):
        if sma_5 > sma_20 and close > sma_5:
            signal = "Buy"
        elif sma_5 < sma_20 and close < sma_5:
            signal = "Sell"
        else:
            signal = "Hold"
    else:
        signal = "Hold"
    results.append({
        "Company": symbol,
        "LatestClose": close,
        "SMA_5": round(sma_5, 2) if pd.notna(sma_5) else None,
        "SMA_20": round(sma_20, 2) if pd.notna(sma_20) else None,
        "Signal": signal,
    })

out_df = pd.DataFrame(results)
out_path = OUTPUT_DIR / "recommendations.csv"
out_df.to_csv(out_path, index=False)
print(f"Recommendations saved to {out_path}")
