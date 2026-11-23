"""Feature engineering untuk forecasting konsumsi energi (dipakai train + predict)."""
import pandas as pd

FEATURES = [
    "machine_code", "hour", "day_of_week", "is_weekend",
    "shift", "lag_1h", "lag_24h", "rolling_mean_6h",
]


TZ_WIB = "Asia/Jakarta"


def get_shift(wib_hour: int) -> int:
    """Shift sesuai database/schema.md (jam WIB): 1=07-15, 2=15-23, 3=23-07."""
    if 7 <= wib_hour < 15:
        return 1
    if 15 <= wib_hour < 23:
        return 2
    return 3


def to_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Data per menit -> per jam (jumlah kWh per jam per mesin)."""
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)  # timestamp di DB/CSV = UTC
    out = []
    for mid, g in df.sort_values("timestamp").groupby("machine_id"):
        h = (
            g.set_index("timestamp")["energy_kwh"]
            .resample("1h").sum(min_count=1)   # jam kosong -> NaN, bukan 0
            .interpolate(limit=3)              # isi gap kecil saja
        )
        out.append(h.rename("energy_kwh").reset_index().assign(machine_id=mid))
    return pd.concat(out, ignore_index=True)


def add_features(hourly: pd.DataFrame, machine_map: dict) -> pd.DataFrame:
    df = hourly.sort_values(["machine_id", "timestamp"]).copy()
    ts = df["timestamp"].dt.tz_convert(TZ_WIB)  # fitur waktu dihitung dalam WIB (shift & jam kerja)
    df["machine_code"] = df["machine_id"].map(machine_map)
    df["hour"] = ts.dt.hour
    df["day_of_week"] = ts.dt.dayofweek
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["shift"] = df["hour"].map(get_shift)
    g = df.groupby("machine_id")["energy_kwh"]
    df["lag_1h"] = g.shift(1)
    df["lag_24h"] = g.shift(24)
    # shift(1) dulu supaya rolling TIDAK mengintip nilai jam yang diprediksi (data leakage)
    df["rolling_mean_6h"] = g.transform(lambda s: s.shift(1).rolling(6).mean())
    return df
