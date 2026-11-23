from pathlib import Path
import argparse
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT_DIR / "ml" / "models" / "anomaly.pkl"
DEFAULT_DATA_DIR = ROOT_DIR / "ml" / "anomaly" / "data"

FEATURE_COLS = [
    "power_ratio",
    "status_encoded",
    "units_produced",
    "ratio_excess",
    "idle_excess",
    "spike_excess",
    "no_prod_running",
    "hour",
]

STATUS_MAP = {
    "off": 0,
    "idle": 1,
    "running": 2,
}


def derive_shift(hour_series: pd.Series) -> pd.Series:
    # Shift 1: 06-13, Shift 2: 14-21, Shift 3: 22-05
    return np.where(
        (hour_series >= 6) & (hour_series <= 13),
        1,
        np.where((hour_series >= 14) & (hour_series <= 21), 2, 3),
    )


def load_and_merge_dataset(
    energy_csv: Path,
    machines_csv: Path | None = None,
    prod_csv: Path | None = None,
) -> pd.DataFrame:
    df = pd.read_csv(energy_csv)
    ts = pd.to_datetime(df["timestamp"], utc=True)
    df["_ts"] = ts
    df["date"] = ts.dt.strftime("%Y-%m-%d")
    df["hour"] = ts.dt.hour
    df["shift"] = derive_shift(df["hour"])

    if machines_csv and machines_csv.exists():
        machines = pd.read_csv(machines_csv)
        keep_m = [
            c
            for c in ["machine_id", "name", "line", "type", "rated_power_kw"]
            if c in machines.columns
        ]
        df = df.merge(machines[keep_m], on="machine_id", how="left")

    if prod_csv and prod_csv.exists():
        prod = pd.read_csv(prod_csv)
        if {"machine_id", "date", "shift", "units_produced"}.issubset(prod.columns):
            prod_agg = (
                prod.groupby(["machine_id", "date", "shift"], as_index=False)["units_produced"]
                .sum()
            )
            df = df.merge(prod_agg, on=["machine_id", "date", "shift"], how="left")

    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    if "_ts" not in data.columns:
        data["_ts"] = pd.to_datetime(data["timestamp"], utc=True)
    if "hour" not in data.columns:
        data["hour"] = data["_ts"].dt.hour

    if "rated_power_kw" not in data.columns:
        max_p = data.groupby("machine_id")["power_kw"].transform("max").replace(0, np.nan)
        data["rated_power_kw"] = max_p.fillna(data["power_kw"].max() or 1.0)

    if "units_produced" not in data.columns:
        data["units_produced"] = 0
    data["units_produced"] = data["units_produced"].fillna(0)

    if "status" not in data.columns:
        data["status"] = "running"
    status_lower = data["status"].astype(str).str.lower()

    data["power_ratio"] = np.where(
        data["rated_power_kw"] > 0,
        data["power_kw"] / data["rated_power_kw"],
        0.0,
    )
    data["status_encoded"] = status_lower.map(STATUS_MAP).fillna(1)

    status_med = data.groupby(["machine_id", "status"])["power_ratio"].transform("median")
    data["ratio_excess"] = data["power_ratio"] - status_med
    data["idle_excess"] = np.where(
        (status_lower == "idle") & (data["power_ratio"] > 0.25),
        data["power_ratio"] - 0.10,
        0.0,
    )
    data["spike_excess"] = np.where(
        data["power_ratio"] > 1.0,
        data["power_ratio"] - 1.0,
        0.0,
    )
    data["no_prod_running"] = np.where(
        (status_lower == "running") & (data["units_produced"] <= 0),
        1.0,
        0.0,
    )

    data[FEATURE_COLS] = (
        data[FEATURE_COLS]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0)
    )
    return data


def run_eda(df: pd.DataFrame) -> dict:
    print("=== RINGKASAN EDA ===")
    print(f"Total baris       : {len(df)}")
    print(f"Jumlah mesin      : {df['machine_id'].nunique()}")
    print(f"Rentang waktu     : {df['timestamp'].min()} s/d {df['timestamp'].max()}")
    print(f"Missing values    : {int(df[FEATURE_COLS].isna().sum().sum())} (pada fitur utama)")

    status_counts = df["status"].value_counts().to_dict()
    print(f"Distribusi status : {status_counts}")

    eda_summary: dict = {
        "total_rows": int(len(df)),
        "unique_machines": int(df["machine_id"].nunique()),
        "start_time": str(df["timestamp"].min()),
        "end_time": str(df["timestamp"].max()),
        "status_counts": {str(k): int(v) for k, v in status_counts.items()},
    }

    if "is_waste" in df.columns:
        waste_count = int(df["is_waste"].sum())
        waste_rate = float(df["is_waste"].mean() * 100)
        print(f"Proporsi is_waste : {waste_count} baris ({waste_rate:.2f}%)")
        eda_summary["waste_count"] = waste_count
        eda_summary["waste_rate_pct"] = round(waste_rate, 2)

    if "waste_type" in df.columns:
        wtype_counts = df["waste_type"].value_counts().to_dict()
        print(f"Jenis waste_type  : {wtype_counts}")
        eda_summary["waste_type_counts"] = {str(k): int(v) for k, v in wtype_counts.items()}

    print("\nStatistik power_kw & power_ratio per status:")
    stat_table = (
        df.groupby("status")[["power_kw", "power_ratio"]]
        .agg(["count", "mean", "median", "max"])
        .round(3)
    )
    print(stat_table)
    print("=====================\n")

    return eda_summary


def train_model(
    energy_csv: Path,
    machines_csv: Path | None = None,
    prod_csv: Path | None = None,
    contamination: float = 0.04,
    eval_out_path: str | None = "ml/anomaly/eval_summary.json",
) -> None:
    merged = load_and_merge_dataset(energy_csv, machines_csv, prod_csv)
    featured = build_features(merged)
    eda_info = run_eda(featured)

    X = featured[FEATURE_COLS]

    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X)

    # IsolationForest: -1 = anomali, 1 = normal
    pred_anomaly = (model.predict(X) == -1).astype(int)

    label_col = next(
        (c for c in ["is_waste", "is_anomaly", "anomaly_label", "label"] if c in featured.columns),
        None,
    )

    summary: dict = {
        "energy_csv": str(energy_csv),
        "total_rows": int(len(featured)),
        "contamination": contamination,
        "detected_anomalies": int(pred_anomaly.sum()),
        "eda": eda_info,
    }

    if label_col is not None:
        y_true = featured[label_col].astype(int)
        prec = float(precision_score(y_true, pred_anomaly, zero_division=0))
        rec = float(recall_score(y_true, pred_anomaly, zero_division=0))
        f1 = float(f1_score(y_true, pred_anomaly, zero_division=0))
        cm = confusion_matrix(y_true, pred_anomaly)

        print(f"=== Evaluasi terhadap '{label_col}' (n={len(featured)}) ===")
        print(f"Precision : {prec:.4f}")
        print(f"Recall    : {rec:.4f}")
        print(f"F1-Score  : {f1:.4f}")
        print("Confusion Matrix [TN FP; FN TP]:")
        print(cm)
        print("\nClassification Report:")
        print(classification_report(y_true, pred_anomaly, digits=4, zero_division=0))

        summary.update(
            {
                "label_col": label_col,
                "precision": round(prec, 4),
                "recall": round(rec, 4),
                "f1_score": round(f1, 4),
                "confusion_matrix": cm.tolist(),
            }
        )
    else:
        pct = (pred_anomaly.sum() / len(pred_anomaly) * 100) if len(pred_anomaly) else 0.0
        print(f"Anomali terdeteksi: {int(pred_anomaly.sum())}/{len(pred_anomaly)} ({pct:.2f}%)")

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "feature_cols": FEATURE_COLS,
            "status_map": STATUS_MAP,
        },
        MODEL_PATH,
    )
    print(f"\nModel tersimpan di: {MODEL_PATH}")

    if eval_out_path:
        out = Path(eval_out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Ringkasan evaluasi tersimpan di: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EDA + Train Isolation Forest untuk deteksi pemborosan")
    parser.add_argument(
        "--energy-csv",
        type=Path,
        default=DEFAULT_DATA_DIR / "energy_readings_sample.csv",
    )
    parser.add_argument(
        "--machines-csv",
        type=Path,
        default=DEFAULT_DATA_DIR / "machines.csv",
    )
    parser.add_argument(
        "--prod-csv",
        type=Path,
        default=DEFAULT_DATA_DIR / "production_logs_sample.csv",
    )
    parser.add_argument("--contamination", type=float, default=0.04)
    parser.add_argument("--output-eval", type=str, default="ml/anomaly/eval_summary.json")
    args = parser.parse_args()

    train_model(
        energy_csv=args.energy_csv,
        machines_csv=args.machines_csv,
        prod_csv=args.prod_csv,
        contamination=args.contamination,
        eval_out_path=args.output_eval,
    )