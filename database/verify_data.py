#!/usr/bin/env python3
"""
verify_data.py - Verifikasi kualitas data hasil generate_data.py.
Contoh:  python verify_data.py --db smart_energy_test
         python verify_data.py                      (database utama)
Keluar dengan kode 1 bila ada pemeriksaan GAGAL.
"""
from __future__ import annotations

import argparse
import math
import statistics
import sys
from datetime import date, timedelta

import db as dbm

VALID_STATUS = ["running", "idle", "off"]
FAILS = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global FAILS
    FAILS += 0 if ok else 1
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def shift_of(wib_date: str, wib_hour: int):
    """Hitung (tanggal_shift, shift) dari tanggal+jam WIB, independen dari generator."""
    if 7 <= wib_hour < 15:
        return wib_date, 1
    if 15 <= wib_hour < 23:
        return wib_date, 2
    if wib_hour >= 23:
        return wib_date, 3
    prev = (date.fromisoformat(wib_date) - timedelta(days=1)).isoformat()
    return prev, 3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri", default=None)
    ap.add_argument("--db", default=None)
    ap.add_argument("--waste-rate", type=float, default=0.04)
    a = ap.parse_args()
    dbm.ping(a.uri)
    db = dbm.get_db(a.db, a.uri)
    print(f"Verifikasi database: {db.name}\n")

    # 1) count per koleksi
    counts = {c: db[c].count_documents({}) for c in dbm.COLLECTIONS}
    for c, n in counts.items():
        print(f"  {c:16s} {n:>10,d}")
    n_energy = counts["energy_readings"]
    check("energy_readings tidak kosong", n_energy > 0)
    if n_energy == 0:
        return 1
    machines = list(db["machines"].find({}, {"_id": 0}).sort("machine_id", 1))
    rated = {m["machine_id"]: m["rated_power_kw"] for m in machines}
    check("jumlah mesin > 0", len(machines) > 0, f"({len(machines)})")

    # 2) rentang timestamp + interval
    first = db["energy_readings"].find_one(sort=[("timestamp", 1)])["timestamp"]
    last = db["energy_readings"].find_one(sort=[("timestamp", -1)])["timestamp"]
    mid0 = machines[0]["machine_id"]
    two = list(db["energy_readings"].find({"machine_id": mid0}, {"timestamp": 1}).sort("timestamp", 1).limit(2))
    interval = int((two[1]["timestamp"] - two[0]["timestamp"]).total_seconds() // 60)
    wib = timedelta(hours=7)
    print(f"\nRentang UTC: {first} s/d {last}\nRentang WIB: {first + wib} s/d {last + wib}\nInterval   : {interval} menit")
    per_machine = int((last - first).total_seconds() // 60 // interval) + 1
    grp = {r["_id"]: r["n"] for r in db["energy_readings"].aggregate(
        [{"$group": {"_id": "$machine_id", "n": {"$sum": 1}}}], allowDiskUse=True)}
    check("tiap mesin punya jumlah baris lengkap (tanpa celah)",
          all(grp.get(m) == per_machine for m in rated), f"(harapan {per_machine}/mesin)")
    dup = list(db["energy_readings"].aggregate(
        [{"$group": {"_id": {"m": "$machine_id", "t": "$timestamp"}, "n": {"$sum": 1}}},
         {"$match": {"n": {"$gt": 1}}}, {"$limit": 1}], allowDiskUse=True))
    check("tidak ada duplikat (machine_id, timestamp)", not dup)
    days = per_machine * interval // 1440
    check("production_logs = mesin x hari x 3", counts["production_logs"] == len(machines) * days * 3,
          f"({counts['production_logs']} vs {len(machines) * days * 3})")

    # 3) persentase pemborosan
    pct = 100.0 * counts["waste_labels"] / n_energy
    lo, hi = a.waste_rate * 100 - 1.0, a.waste_rate * 100 + 1.0
    print()
    check("persentase pemborosan sesuai target (+-1 poin)", lo <= pct <= hi, f"({pct:.2f}%)")
    for r in db["waste_labels"].aggregate([{"$group": {"_id": "$waste_type", "n": {"$sum": 1}}}, {"$sort": {"_id": 1}}]):
        print(f"      {r['_id']:24s} {r['n']:>8,d}")
    check("waste_labels tersebar di semua mesin",
          len(db["waste_labels"].distinct("machine_id")) == len(machines))

    # 4) nilai tidak masuk akal
    print()
    er = db["energy_readings"]
    check("tidak ada power_kw negatif", er.count_documents({"power_kw": {"$lt": 0}}) == 0)
    check("tidak ada status tidak valid", er.count_documents({"status": {"$nin": VALID_STATUS}}) == 0)
    check("voltage dalam 370-410 V", er.count_documents({"$or": [{"voltage": {"$lt": 370}}, {"voltage": {"$gt": 410}}]}) == 0)
    check("tidak ada current negatif", er.count_documents({"current": {"$lt": 0}}) == 0)
    bad_e = er.count_documents({"$expr": {"$gt": [{"$abs": {"$subtract": [
        "$energy_kwh", {"$multiply": ["$power_kw", interval / 60.0]}]}}, 1e-4]}})
    check(f"energy_kwh = power_kw x {interval}/60", bad_e == 0, f"(menyimpang: {bad_e})")
    bad_i = er.count_documents({"$expr": {"$gt": [{"$abs": {"$subtract": ["$current", {"$divide": [
        {"$multiply": ["$power_kw", 1000]}, {"$multiply": [math.sqrt(3), "$voltage", 0.85]}]}]}}, 0.02]}})
    check("current konsisten dengan daya (pf 0,85)", bad_i == 0, f"(menyimpang: {bad_i})")
    over = sum(er.count_documents({"machine_id": m, "power_kw": {"$gt": 1.6 * r}}) for m, r in rated.items())
    check("daya tidak melebihi 160% rated", over == 0, f"({over})")
    low_run = sum(er.count_documents({"machine_id": m, "status": "running", "power_kw": {"$lt": 0.5 * r}})
                  for m, r in rated.items())
    check("status running selalu berdaya >= 50% rated", low_run == 0, f"({low_run})")

    # 5) konsistensi production_logs vs status (shift dihitung ulang dari jam WIB)
    print()
    agg = er.aggregate([{"$group": {
        "_id": {"m": "$machine_id",
                "d": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp", "timezone": "+07:00"}},
                "h": {"$hour": {"date": "$timestamp", "timezone": "+07:00"}}},
        "n": {"$sum": 1}, "run": {"$sum": {"$cond": [{"$eq": ["$status", "running"]}, 1, 0]}}}}],
        allowDiskUse=True)
    blocks: dict = {}
    for r in agg:
        k = (r["_id"]["m"],) + shift_of(r["_id"]["d"], r["_id"]["h"])
        b = blocks.setdefault(k, [0, 0])
        b[0] += r["n"]
        b[1] += r["run"]
    units = {(p["machine_id"], p["date"], p["shift"]): p["units_produced"]
             for p in db["production_logs"].find({}, {"_id": 0})}
    check("setiap production_logs punya data energi", all(k in blocks for k in units))
    full = 480 // interval
    check("setiap blok shift lengkap", all(v[0] == full for k, v in blocks.items() if k in units))
    viol = [k for k, u in units.items() if k in blocks and u > 0 and blocks[k][1] == 0]
    check("tidak ada produksi saat mesin tidak pernah running", not viol, f"({len(viol)})")
    med = {}
    for (m, _d, _s), u in units.items():
        if u > 0:
            med.setdefault(m, []).append(u)
    med = {m: statistics.median(v) for m, v in med.items()}
    t3 = db["waste_labels"].aggregate([{"$match": {"waste_type": "running_no_production"}},
        {"$group": {"_id": {"m": "$machine_id",
                            "d": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp", "timezone": "+07:00"}},
                            "h": {"$hour": {"date": "$timestamp", "timezone": "+07:00"}}}}}])
    t3_blocks = {(r["_id"]["m"],) + shift_of(r["_id"]["d"], r["_id"]["h"]) for r in t3}
    bad_t3 = [k for k in t3_blocks if units.get(k, 0) > 0.06 * med.get(k[0], 1)]
    check("label running_no_production: produksi shift itu nol/rendah", not bad_t3,
          f"({len(t3_blocks)} blok, melanggar {len(bad_t3)})")
    print(f"\nTotal pemeriksaan GAGAL: {FAILS}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
