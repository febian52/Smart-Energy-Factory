"""Fungsi forecast() untuk diserahkan ke Wowok (FastAPI).

Pakai:
    from ml.forecast.predict import forecast
    forecast("M01", 24)  # -> list of {machine_id, forecast_time, predicted_kwh}
"""
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.forecast.features import TZ_WIB, get_shift

MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "forecast.pkl"
_bundle = None


def _load():
    global _bundle
    if _bundle is None:
        _bundle = joblib.load(MODEL_PATH)
    return _bundle


def _history_from_db(machine_id: str, hours: int = 72) -> pd.DataFrame:
    """Ambil `hours` jam data TERAKHIR mesin dari MongoDB (pakai database/db.py Lae).

    Patokannya data terakhir di DB, bukan jam sekarang, karena data disimulasi
    (Jan-Jun 2026) dan bukan real-time.
    """
    from database.db import get_db

    n = hours * 12  # interval data 5 menit -> 12 baris per jam
    docs = list(
        get_db()["energy_readings"]
        .find({"machine_id": machine_id}, {"_id": 0, "timestamp": 1, "energy_kwh": 1})
        .sort("timestamp", -1)
        .limit(n)
    )
    return pd.DataFrame(docs[::-1])


def forecast(machine_id: str, hours_ahead: int = 24, history: pd.DataFrame | None = None) -> list[dict]:
    """Prediksi kWh per jam untuk `hours_ahead` jam ke depan (24 = 24 jam, 168 = 7 hari).

    history: opsional, DataFrame (timestamp, energy_kwh) data terbaru mesin tsb.
             Kalau kosong, diambil dari MongoDB.
    """
    b = _load()
    if machine_id not in b["machine_map"]:
        raise ValueError(f"machine_id '{machine_id}' tidak dikenal model")

    if history is None:
        history = _history_from_db(machine_id)
    s = (
        history.assign(timestamp=pd.to_datetime(history["timestamp"], utc=True))
        .set_index("timestamp")["energy_kwh"]
        .resample("1h").sum(min_count=1)
        .interpolate(limit=3)
        .dropna()
    )
    if len(s) < 24:
        raise ValueError("History minimal 24 jam terakhir")

    vals = list(s.values)
    last = s.index[-1]
    out = []
    # Recursive forecasting: hasil prediksi jam ke-t dipakai sebagai lag buat jam t+1
    for i in range(1, hours_ahead + 1):
        t = last + pd.Timedelta(hours=i)   # UTC
        w = t.tz_convert(TZ_WIB)           # fitur dihitung dalam WIB
        row = {
            "machine_code": b["machine_map"][machine_id],
            "hour": w.hour,
            "day_of_week": w.dayofweek,
            "is_weekend": int(w.dayofweek >= 5),
            "shift": get_shift(w.hour),
            "lag_1h": vals[-1],
            "lag_24h": vals[-24],
            "rolling_mean_6h": float(np.mean(vals[-6:])),
        }
        y = max(float(b["model"].predict(pd.DataFrame([row])[b["features"]])[0]), 0.0)
        vals.append(y)
        out.append({
            "machine_id": machine_id,
            "forecast_time": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "predicted_kwh": round(y, 4),
        })
    return out
