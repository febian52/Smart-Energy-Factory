"""Fitur untuk forecasting konsumsi energi per jam (strategi DIRECT, tanpa rekursi).

Satu prediksi = satu baris fitur: "dari titik asal (origin) = jam terakhir yang
terobservasi, berapa kWh pada jam T = origin + h?" (h = 1..168).
Semua fitur hanya memakai data yang sudah diketahui saat origin, jadi tidak ada
error yang menumpuk seperti pada prediksi rekursif.

Semua nilai kWh dinormalisasi dengan rated_power_kw mesin (rasio terhadap kapasitas),
supaya skala model tidak terikat ke satu mesin/DB tertentu.
"""
import numpy as np
import pandas as pd

TZ_OFFSET_H = 7   # WIB = UTC+7 (Asia/Jakarta tidak pakai DST)
MAX_H = 168       # horizon maksimum (7 hari)
HISTORY_H = 192   # history ideal: 8 hari (butuh lag 168 jam)

FEATURES = [
    "machine_code", "hour", "day_of_week", "is_weekend", "shift",
    "horizon", "lag_same_hour", "lag_168h", "mean_24h", "last_1h", "mean_6h",
]


def get_shift(wib_hour):
    """Shift sesuai database/schema.md (jam WIB): 1=07-15, 2=15-23, 3=23-07."""
    wib_hour = np.asarray(wib_hour)
    return np.where((wib_hour >= 7) & (wib_hour < 15), 1,
                    np.where((wib_hour >= 15) & (wib_hour < 23), 2, 3))


def to_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Data per 5 menit -> per jam (jumlah kWh per jam per mesin). Timestamp = UTC."""
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    out = []
    for mid, g in df.sort_values("timestamp").groupby("machine_id"):
        h = (
            g.set_index("timestamp")["energy_kwh"]
            .resample("1h").sum(min_count=1)   # jam kosong -> NaN, bukan 0
            .interpolate(limit=3)              # isi gap kecil saja
        )
        out.append(h.rename("energy_kwh").reset_index().assign(machine_id=mid))
    return pd.concat(out, ignore_index=True)


def _wib_parts(t_hours):
    """array datetime64[h] (UTC) -> (hour, day_of_week) dalam WIB, murni numpy."""
    h = t_hours.astype("datetime64[h]").astype("int64") + TZ_OFFSET_H
    hour = h % 24
    dow = (h // 24 + 3) % 7   # 1 Jan 1970 = Kamis; Senin = 0
    return hour, dow


def build_features(y, ts, origins, machine_code, horizons=None):
    """Bangun fitur untuk banyak origin sekaligus.

    y       : array 1D kWh/rated per jam (tanpa NaN), berurutan tiap 1 jam
    ts      : array datetime64[h] (UTC), sepanjang y
    origins : indeks origin (posisi jam terakhir yang diketahui) di y
    Return  : (X DataFrame, T) dengan T = indeks target di y (bisa >= len(y) saat inferensi).
    Bila history pendek, lag yang jatuh sebelum awal data diganti lag_same_hour.
    """
    y = np.asarray(y, dtype="float64")
    horizons = np.arange(1, MAX_H + 1) if horizons is None else np.asarray(horizons)
    O = np.asarray(origins)[:, None]
    Hh = horizons[None, :]
    T = O + Hh

    k = np.ceil(Hh / 24).astype(int)
    lag_same = y[np.clip(T - 24 * k, 0, len(y) - 1)]      # jam yg sama pada hari terakhir yg diketahui
    l168 = T - 168
    lag168 = np.where(l168 >= 0, y[np.clip(l168, 0, len(y) - 1)], lag_same)

    cs = np.concatenate([[0.0], np.cumsum(y)])
    lo = np.maximum(O - 23, 0)
    mean24 = np.broadcast_to((cs[O + 1] - cs[lo]) / (O + 1 - lo), T.shape)

    last1 = np.broadcast_to(y[O], T.shape)                  # nilai jam terakhir yang diketahui
    lo6 = np.maximum(O - 5, 0)
    mean6 = np.broadcast_to((cs[O + 1] - cs[lo6]) / (O + 1 - lo6), T.shape)

    t_target = ts[O.ravel()][:, None] + Hh.astype("timedelta64[h]")
    hour, dow = _wib_parts(t_target)

    X = pd.DataFrame({
        "machine_code": np.full(T.size, machine_code, dtype="int32"),
        "hour": hour.ravel().astype("int8"),
        "day_of_week": dow.ravel().astype("int8"),
        "is_weekend": (dow.ravel() >= 5).astype("int8"),
        "shift": get_shift(hour.ravel()).astype("int8"),
        "horizon": np.broadcast_to(Hh, T.shape).ravel().astype("int16"),
        "lag_same_hour": lag_same.ravel().astype("float32"),
        "lag_168h": lag168.ravel().astype("float32"),
        "mean_24h": mean24.ravel().astype("float32"),
        "last_1h": last1.ravel().astype("float32"),
        "mean_6h": mean6.ravel().astype("float32"),
    })[FEATURES]
    return X, T
