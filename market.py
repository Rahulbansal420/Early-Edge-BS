from pathlib import Path
import pandas as pd

def load_market_csvs(folder="market_data"):
    paths=sorted(Path(folder).glob("*.csv"))
    frames=[]
    for p in paths:
        try:
            x=pd.read_csv(p)
            if {"timestamp","symbol","close","volume"}.issubset(x.columns):
                frames.append(x)
        except Exception:
            pass
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

def market_confirmation(symbol, df):
    if df.empty:
        return {"price_confirmation":"UNCONFIRMED","volume_confirmation":"UNCONFIRMED"}
    x=df[df.symbol.eq(symbol)].sort_values("timestamp")
    if len(x)<21:
        return {"price_confirmation":"UNCONFIRMED","volume_confirmation":"UNCONFIRMED"}
    last=x.iloc[-1]
    prev=x.iloc[-21:-1]
    return {
        "price_confirmation":"CONFIRMED" if last.close > prev.close.max() else "UNCONFIRMED",
        "volume_confirmation":"CONFIRMED" if last.volume > prev.volume.mean()*1.5 else "UNCONFIRMED"
    }
