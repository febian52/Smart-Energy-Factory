#!/usr/bin/env python3
"""
export_csv.py - Ekspor CSV sample (30 hari pertama) atau CSV penuh dari MongoDB.

  python export_csv.py                      -> sample/ : machines.csv, energy_readings_sample.csv,
                                              production_logs_sample.csv
  python export_csv.py --days 60           -> sample 60 hari
  python export_csv.py --full              -> full_export/ : *_full.csv (jangan di-commit!)

Kolom energy_readings: machine_id,timestamp,power_kw,energy_kwh,voltage,current,status,is_waste,waste_type
  timestamp = ISO-8601 UTC (2026-01-01T00:00:00Z); is_waste = 0/1; waste_type = 'none' bila 0.
"""
from __future__ import annotations

import argparse
import os
from datetime import date, timedelta

import pandas as pd

import db as dbm

HERE = os.path.dirname(os.path.abspath(__file__))
COLS = ["machine_id", "timestamp", "power_kw", "energy_kwh", "voltage", "current", "status",
        "is_waste", "waste_type"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri", default=None)
    ap.add_argument("--db", default=None)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args()
    db = dbm.get_db(a.db, a.uri)
    out = a.out_dir or os.path.join(HERE, "full_export" if a.full else "sample")
    os.makedirs(out, exist_ok=True)
    sfx = "_full" if a.full else "_sample"

    machines = pd.DataFrame(list(db["machines"].find({}, {"_id": 0}).sort("machine_id", 1)))
    machines.to_csv(os.path.join(out, "machines.csv"), index=False)

    labels = pd.DataFrame(list(db["waste_labels"].find({}, {"_id": 0, "machine_id": 1, "timestamp": 1, "waste_type": 1})))
    first = db["energy_readings"].find_one(sort=[("timestamp", 1)])["timestamp"]
    flt = {} if a.full else {"timestamp": {"$lt": first + timedelta(days=a.days)}}

    path = os.path.join(out, f"energy_readings{sfx}.csv")
    if os.path.exists(path):
        os.remove(path)
    total = 0
    for i, mid in enumerate(machines["machine_id"]):
        df = pd.DataFrame(list(db["energy_readings"].find({"machine_id": mid, **flt}, {"_id": 0}).sort("timestamp", 1)))
        if df.empty:
            continue
        lab = labels[labels["machine_id"] == mid][["timestamp", "waste_type"]] if not labels.empty else None
        df = df.merge(lab, on="timestamp", how="left") if lab is not None else df.assign(waste_type=None)
        df["is_waste"] = df["waste_type"].notna().astype(int)
        df["waste_type"] = df["waste_type"].fillna("none")
        df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        df[COLS].to_csv(path, mode="a", header=(i == 0), index=False)
        total += len(df)

    pflt = {}
    if not a.full:
        first_d = db["production_logs"].find_one(sort=[("date", 1)])["date"]
        pflt = {"date": {"$lt": (date.fromisoformat(first_d) + timedelta(days=a.days)).isoformat()}}
    prod = pd.DataFrame(list(db["production_logs"].find(pflt, {"_id": 0}).sort([("machine_id", 1), ("date", 1), ("shift", 1)])))
    prod = prod[["machine_id", "shift", "date", "units_produced"]]
    prod.to_csv(os.path.join(out, f"production_logs{sfx}.csv"), index=False)

    print(f"Selesai -> {out}")
    for f in sorted(os.listdir(out)):
        print(f"  {f:34s} {os.path.getsize(os.path.join(out, f)) / 1024 ** 2:8.2f} MB")
    print(f"  baris energy_readings: {total:,d}; production_logs: {len(prod):,d}")


if __name__ == "__main__":
    main()
