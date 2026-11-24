"""Fungsi forecast() untuk diserahkan ke Wowok (FastAPI).

Pakai:
    from ml.forecast.predict import forecast
    forecast("M01", 24)    # 24 jam ke depan
    forecast("M01", 168)   # 7 hari ke depan (maksimum)
-> list of {machine_id, forecast_time (UTC, ...Z), predicted_kwh}

Strategi DIRECT: seluruh horizon diprediksi sekaligus dari history yang sudah diketahui
(tanpa rekursi), jadi cepat (puluhan ms) dan error tidak menumpuk.
Prediksi dibatasi ke rentang 0 .. rated_power_kw mesin.
"""
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.forecast.features import HISTORY_H, MAX_H, build_features

MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "forecast.pkl"
_bundle = None


def _load():
    global _bundle
    if _bundle is None:
        _bundle = joblib.load(MODEL_PATH)
        try:
            _bundle["model"].set_params(n_jobs=1)  # inferensi baris sedikit: tanpa overhead thread
        except Exception:
            pass
    return _bundle


def _history_from_db(machine_id: str, hours: int = HISTORY_H):
    """Ambil `hours` jam data TERAKHIR mesin dari MongoDB (pakai database/db.py Lae)
    beserta rated_power_kw dari koleksi machines (None bila tidak ada).

    Patokannya data terakhir di DB, bukan jam sekarang, karena data disimulasi.
    """
    from database.db import get_db

    db = get_db()
    n = hours * 12  # interval data 5 menit -> 12 baris per jam
    docs = list(
        db["energy_readings"]
        .find({"machine_id": machine_id}, {"_id": 0, "timestamp": 1, "energy_kwh": 1})
        .sort("timestamp", -1)
        .limit(n)
    )
    m = db["machines"].find_one({"machine_id": machine_id}, {"_id": 0, "rated_power_kw": 1})
    rated = float(m["rated_power_kw"]) if m and m.get("rated_power_kw") else None
    return pd.DataFrame(docs[::-1]), rated


def forecast(machine_id: str, hours_ahead: int = 24, history: pd.DataFrame | None = None,
             rated_kw: float | None = None) -> list[dict]:
    """Prediksi kWh per jam untuk `hours_ahead` jam ke depan (maks 168).

    history : opsional, DataFrame (timestamp UTC, energy_kwh) data terbaru mesin tsb,
              idealnya >= 192 jam. Kalau kosong, diambil dari MongoDB.
    rated_kw: opsional, kapasitas mesin. Default: dari koleksi machines (jalur DB),
              kalau tidak ada dipakai nilai saat training.
    """
    b = _load()
    if machine_id not in b["machine_map"]:
        raise ValueError(f"machine_id '{machine_id}' tidak dikenal model")
    if not 1 <= hours_ahead <= MAX_H:
        raise ValueError(f"hours_ahead harus 1..{MAX_H}")

    if history is None:
        history, db_rated = _history_from_db(machine_id)
        rated_kw = rated_kw or db_rated
    rated = float(rated_kw or b["rated_kw"][machine_id])

    s = (
        history.assign(timestamp=pd.to_datetime(history["timestamp"], utc=True))
        .set_index("timestamp")["energy_kwh"]
        .resample("1h").sum(min_count=1)
        .interpolate(limit=3)
        .dropna()
    )
    if len(s) < 24:
        raise ValueError("History minimal 24 jam terakhir")

    y = s.values / rated                       # normalisasi ke rasio kapasitas
    ts = s.index.tz_convert("UTC").tz_localize(None).values.astype("datetime64[h]")
    horizons = np.arange(1, hours_ahead + 1)
    X, _ = build_features(y, ts, [len(y) - 1], b["machine_map"][machine_id], horizons)
    pred = np.clip(b["model"].predict(X[b["features"]]), 0.0, 1.0) * rated

    last = s.index[-1]
    return [
        {
            "machine_id": machine_id,
            "forecast_time": (last + pd.Timedelta(hours=int(h))).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "predicted_kwh": round(float(v), 4),
        }
        for h, v in zip(horizons, pred)
    ]
