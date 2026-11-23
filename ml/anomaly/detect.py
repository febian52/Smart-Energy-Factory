from pathlib import Path
from typing import Any, Optional
import joblib
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT_DIR / "ml" / "models" / "anomaly.pkl"

STATUS_MAP = {
    "off": 0,
    "idle": 1,
    "running": 2,
}


def _load_artifact() -> dict[str, Any]:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model tidak ditemukan di {MODEL_PATH}. Jalankan ml/anomaly/train.py terlebih dahulu."
        )
    return joblib.load(MODEL_PATH)


def _derive_shift(hour_series: pd.Series) -> pd.Series:
    return np.where(
        (hour_series >= 6) & (hour_series <= 13),
        1,
        np.where((hour_series >= 14) & (hour_series <= 21), 2, 3),
    )


def _fetch_from_db(machine_id: str, start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> pd.DataFrame:
    try:
        from database.db import get_db
    except Exception:
        return pd.DataFrame()

    db = get_db()
    readings = list(
        db["energy_readings"].find(
            {
                "machine_id": machine_id,
                "timestamp": {
                    "$gte": start_ts.to_pydatetime(),
                    "$lte": end_ts.to_pydatetime(),
                },
            }
        )
    )
    if not readings:
        return pd.DataFrame()

    df = pd.DataFrame(readings)
    machine_doc = db["machines"].find_one({"machine_id": machine_id}) or {}
    if "rated_power_kw" not in df.columns:
        df["rated_power_kw"] = machine_doc.get("rated_power_kw", 0.0)
    if "name" not in df.columns:
        df["name"] = machine_doc.get("name", machine_id)

    if "units_produced" not in df.columns:
        ts = pd.to_datetime(df["timestamp"], utc=True)
        df["date"] = ts.dt.strftime("%Y-%m-%d")
        df["shift"] = _derive_shift(ts.dt.hour)
        logs = list(db["production_logs"].find({"machine_id": machine_id}))
        if logs:
            logs_df = pd.DataFrame(logs)
            if {"date", "shift", "units_produced"}.issubset(logs_df.columns):
                logs_df["date"] = pd.to_datetime(logs_df["date"]).dt.strftime("%Y-%m-%d")
                agg = logs_df.groupby(["date", "shift"], as_index=False)["units_produced"].sum()
                df = df.merge(agg, on=["date", "shift"], how="left")
                df["units_produced"] = df["units_produced"].fillna(0)
            else:
                df["units_produced"] = 0
        else:
            df["units_produced"] = 0

    return df


def _build_recommendation(row: pd.Series) -> tuple[str, str, str]:
    status = str(row.get("status", "unknown")).lower()
    power_kw = float(row.get("power_kw", 0.0))
    rated_power = float(row.get("rated_power_kw", 0.0))
    units = float(row.get("units_produced", 0.0))
    ratio_pct = (power_kw / rated_power * 100.0) if rated_power > 0 else 0.0
    machine_label = row.get("name") or row.get("machine_id")

    if status == "idle" and ratio_pct >= 25.0:
        severity = "high" if ratio_pct >= 40.0 else "medium"
        waste_type = "idle_high_power"
        note = (
            f"Mesin {machine_label} idle dengan daya {power_kw:.2f} kW "
            f"({ratio_pct:.1f}% dari daya terukur). Matikan atau turunkan ke mode standby saat jeda."
        )
    elif status == "running" and units <= 0:
        severity = "medium"
        waste_type = "running_no_production"
        note = (
            f"Mesin {machine_label} beroperasi ({power_kw:.2f} kW) tanpa output produksi tercatat. "
            f"Cek jadwal shift atau matikan mesin bila tidak ada antrean kerja."
        )
    else:
        severity = "high" if ratio_pct > 100.0 else "medium"
        waste_type = "spike"
        note = (
            f"Terdeteksi lonjakan konsumsi daya tidak wajar ({power_kw:.2f} kW, "
            f"{ratio_pct:.1f}% dari daya terukur) pada mesin {machine_label}. Periksa kondisi beban/mesin."
        )

    return waste_type, severity, note


def detect_waste(
    machine_id: str,
    start: Any,
    end: Any,
    df: Optional[pd.DataFrame] = None,
) -> list[dict[str, Any]]:
    start_ts = pd.to_datetime(start, utc=True)
    end_ts = pd.to_datetime(end, utc=True)

    if df is None:
        filtered = _fetch_from_db(machine_id, start_ts, end_ts)
    else:
        if df.empty:
            return []
        data = df.copy()
        data["_ts"] = pd.to_datetime(data["timestamp"], utc=True)
        mask = (
            (data["machine_id"] == machine_id)
            & (data["_ts"] >= start_ts)
            & (data["_ts"] <= end_ts)
        )
        filtered = data.loc[mask].copy()

    if filtered.empty:
        return []

    filtered["_ts"] = pd.to_datetime(filtered["timestamp"], utc=True)
    filtered["hour"] = filtered["_ts"].dt.hour

    if "rated_power_kw" not in filtered.columns:
        filtered["rated_power_kw"] = filtered["power_kw"].max() or 1.0
    if "units_produced" not in filtered.columns:
        filtered["units_produced"] = 0
    filtered["units_produced"] = filtered["units_produced"].fillna(0)
    if "status" not in filtered.columns:
        filtered["status"] = "running"

    status_lower = filtered["status"].astype(str).str.lower()
    filtered["power_ratio"] = np.where(
        filtered["rated_power_kw"] > 0,
        filtered["power_kw"] / filtered["rated_power_kw"],
        0.0,
    )
    filtered["status_encoded"] = status_lower.map(STATUS_MAP).fillna(1)

    status_med = filtered.groupby(["machine_id", "status"])["power_ratio"].transform("median")
    filtered["ratio_excess"] = filtered["power_ratio"] - status_med
    filtered["idle_excess"] = np.where(
        (status_lower == "idle") & (filtered["power_ratio"] > 0.25),
        filtered["power_ratio"] - 0.10,
        0.0,
    )
    filtered["spike_excess"] = np.where(
        filtered["power_ratio"] > 1.0,
        filtered["power_ratio"] - 1.0,
        0.0,
    )
    filtered["no_prod_running"] = np.where(
        (status_lower == "running") & (filtered["units_produced"] <= 0),
        1.0,
        0.0,
    )

    artifact = _load_artifact()
    model = artifact["model"]
    feature_cols: list[str] = artifact["feature_cols"]

    X = filtered[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
    preds = model.predict(X)
    anomalies = filtered[preds == -1]

    results: list[dict[str, Any]] = []
    for _, row in anomalies.iterrows():
        waste_type, severity, note = _build_recommendation(row)
        results.append(
            {
                "machine_id": row["machine_id"],
                "timestamp": row["_ts"].isoformat(),
                "type": waste_type,
                "severity": severity,
                "note": note,
            }
        )

    return results