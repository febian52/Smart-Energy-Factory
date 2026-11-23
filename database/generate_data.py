#!/usr/bin/env python3
"""
generate_data.py - Generator data simulasi Smart Factory Energy Management.
Pemilik: Lae (branch feature/db).

Reproducible: --seed sama (+ versi numpy yang sama) -> data identik di semua laptop.
Alternatif bila numpy beda versi: pakai mongodump/mongorestore (lihat README_DB.md).

Contoh:
  python generate_data.py --dry-run --days 7                # tanpa MongoDB, hanya cek logika
  python generate_data.py --days 7 --db smart_energy_test --drop   # uji kecil
  python generate_data.py --drop                            # run penuh (622.080 energy_readings)

DESAIN WAKTU (penting, lihat schema.md):
- Data dimulai pukul 07:00 WIB (= 00:00 UTC) pada --start-date dan mencakup N hari penuh,
  sehingga setiap blok shift lengkap. 1 hari data = 3 shift WIB:
  shift 1 = 07-15, shift 2 = 15-23, shift 3 = 23-07 WIB (hari berikutnya).
- production_logs.date = tanggal WIB saat shift DIMULAI (shift 3 tetap bertanggal hari mulainya).
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional

import numpy as np

import db as dbm

try:
    from tqdm import tqdm
except ImportError:  # tqdm opsional
    tqdm = None

RUN, IDLE, OFF = 0, 1, 2
STATUS_NAMES = np.array(["running", "idle", "off"])
WASTE_NAMES = {1: "idle_high_power", 2: "spike", 3: "running_no_production"}
POWER_FACTOR = 0.85

# Perkiraan libur nasional 2026 (untuk simulasi saja, tidak perlu akurat resmi)
HOLIDAYS = {
    "2026-01-01", "2026-01-16", "2026-02-17", "2026-03-19", "2026-03-21", "2026-03-22",
    "2026-04-03", "2026-05-01", "2026-05-14", "2026-05-27", "2026-05-31", "2026-06-01",
}

# id, nama, line, type, rated_kw, kategori, unit/jam
MACHINE_CATALOG = [
    ("M01", "CNC Milling 1", "Line A", "CNC", 45.0, "production", 12),
    ("M02", "CNC Lathe 1", "Line A", "CNC", 30.0, "production", 15),
    ("M03", "Conveyor A", "Line A", "conveyor", 5.5, "production", 300),
    ("M04", "Hydraulic Press", "Line A", "press", 90.0, "production", 60),
    ("M05", "Industrial Oven", "Line B", "oven", 75.0, "production", 40),
    ("M06", "Conveyor B", "Line B", "conveyor", 7.5, "production", 280),
    ("M07", "Chiller 1", "Line B", "chiller", 55.0, "utility", 30),
    ("M08", "Cooling Pump", "Line B", "pump", 15.0, "utility", 100),
    ("M09", "Air Compressor", "Line C", "compressor", 90.0, "utility", 80),
    ("M10", "CNC Milling 2", "Line C", "CNC", 37.0, "production", 10),
    ("M11", "Packaging Machine", "Line C", "packaging", 11.0, "production", 150),
    ("M12", "Conveyor C", "Line C", "conveyor", 5.0, "production", 260),
]


@dataclass
class GenParams:
    machines: int = 12
    months: int = 6
    interval_min: int = 5
    seed: int = 42
    waste_rate: float = 0.04
    start_date: str = "2026-01-01"
    days: Optional[int] = None  # override months (bulan = 30 hari)

    @property
    def total_days(self) -> int:
        return self.days if self.days else self.months * 30


def build_machines(n: int) -> List[dict]:
    out = []
    for i in range(n):
        mid, name, line, mtype, rated, cat, uph = MACHINE_CATALOG[i % len(MACHINE_CATALOG)]
        cycle = i // len(MACHINE_CATALOG)
        if cycle:
            mid, name, rated = f"M{i + 1:02d}", f"{name} #{cycle + 1}", round(rated * (1 + 0.03 * cycle), 1)
        out.append({"machine_id": mid, "name": name, "line": line, "type": mtype,
                    "rated_power_kw": rated, "category": cat, "units_per_hour": uph})
    return out


# --------------------------------------------------------------------------
# Sumbu waktu
# --------------------------------------------------------------------------
@dataclass
class Axis:
    n: int
    days: int
    block_len: int
    ts: list
    dates: List[str]
    wib_hour: np.ndarray
    shift_idx: np.ndarray
    block_id: np.ndarray
    weekday_i: np.ndarray
    offday_i: np.ndarray
    doy_i: np.ndarray
    block_shift: np.ndarray
    block_weekday: np.ndarray
    block_offday: np.ndarray


def make_axis(p: GenParams) -> Axis:
    if 480 % p.interval_min != 0:
        raise ValueError("--interval-min harus pembagi 480 (1, 2, 5, 10, 15, 20, 30, ...)")
    days = p.total_days
    per_day = 1440 // p.interval_min
    n = days * per_day
    idx = np.arange(n, dtype=np.int64)
    day_idx = idx // per_day
    utc_hour = ((idx % per_day) * p.interval_min) // 60  # 00:00 UTC = 07:00 WIB

    start_d = date.fromisoformat(p.start_date)
    day_dates = [start_d + timedelta(days=i) for i in range(days)]
    day_weekday = np.array([d.weekday() for d in day_dates])
    day_off = np.array([d.weekday() == 6 or d.isoformat() in HOLIDAYS for d in day_dates])
    day_doy = np.array([d.timetuple().tm_yday for d in day_dates])

    start64 = np.datetime64(f"{start_d.isoformat()}T00:00:00")
    ts = (start64 + (idx * p.interval_min * 60).astype("timedelta64[s]")).tolist()

    nb = days * 3
    b = np.arange(nb)
    return Axis(
        n=n, days=days, block_len=480 // p.interval_min, ts=ts,
        dates=[d.isoformat() for d in day_dates],
        wib_hour=(utc_hour + 7) % 24, shift_idx=utc_hour // 8, block_id=day_idx * 3 + utc_hour // 8,
        weekday_i=day_weekday[day_idx], offday_i=day_off[day_idx], doy_i=day_doy[day_idx],
        block_shift=b % 3, block_weekday=day_weekday[b // 3], block_offday=day_off[b // 3],
    )


# --------------------------------------------------------------------------
# Simulasi satu mesin
# --------------------------------------------------------------------------
def simulate_machine(spec: dict, ax: Axis, p: GenParams, rng: np.random.Generator) -> dict:
    n, nb, bl = ax.n, ax.days * 3, ax.block_len
    rated = spec["rated_power_kw"]
    is_prod = spec["category"] == "production"
    shift = ax.block_shift

    # 1) mode operasi per blok shift (aktif / idle / off)
    if is_prod:
        p_wd = np.array([0.97, 0.90, 0.08])[shift]
        p_sat = np.array([0.70, 0.30, 0.0])[shift]
        p_off = np.array([0.03, 0.0, 0.0])[shift]
    else:  # utilitas (chiller/pompa/kompresor) hampir selalu menyala
        p_wd = np.array([0.99, 0.99, 0.98])[shift]
        p_sat = np.array([0.93, 0.93, 0.92])[shift]
        p_off = np.array([0.88, 0.88, 0.85])[shift]
    prob = np.where(ax.block_offday, p_off, np.where(ax.block_weekday == 5, p_sat, p_wd))
    active = rng.random(nb) < prob
    alt = np.where(rng.random(nb) < 0.25, IDLE, OFF)
    mode = np.where(active, RUN, alt).astype(np.int8)
    status = mode[ax.block_id]

    # 2) jeda idle singkat di dalam blok aktif (~20 menit)
    k = max(1, int(round(20 / p.interval_min)))
    starts = (rng.random(n) < 0.012 * p.interval_min / 5) & (status == RUN)
    brk = np.convolve(starts.astype(np.int8), np.ones(k, dtype=np.int8))[:n] > 0
    status = np.where(brk & (status == RUN), IDLE, status).astype(np.int8)

    # 3) daya per status
    dow = np.where(ax.weekday_i == 5, 0.90, np.where(ax.offday_i, 0.80, 1.0))
    if is_prod:
        base = np.array([0.80, 0.70, 0.45])[ax.shift_idx]
    else:
        base = 0.55 + 0.25 * np.cos(2 * np.pi * (ax.wib_hour - 14) / 24)
    blk_off = rng.uniform(-0.08, 0.08, nb)[ax.block_id]
    load = np.clip(base * dow + blk_off + rng.normal(0, 0.06, n), 0.0, 1.0)
    amp = 0.03 if is_prod else 0.08  # drift musiman
    drift = 1.0 + amp * np.sin(2 * np.pi * (ax.doy_i - 80) / 365.0)
    frac = np.clip((0.60 + 0.35 * load) * drift, 0.58, 0.96)
    power = np.where(
        status == RUN, rated * frac,
        np.where(status == IDLE, rated * rng.uniform(0.05, 0.15, n),
                 rated * rng.uniform(0.0, 0.004, n)))
    # "umpan" normal: lonjakan kecil yang BUKAN pemborosan (agar deteksi tidak terlalu mudah)
    decoy = (status == RUN) & (rng.random(n) < 0.003)
    power = np.where(decoy, np.minimum(power * rng.uniform(1.05, 1.12, n), rated * 0.99), power)

    # 4) injeksi pemborosan tipe 1 dan 2
    labels = np.zeros(n, dtype=np.int8)
    target = int(round(p.waste_rate * n))
    shares = {1: 0.40, 2: 0.20, 3: 0.40} if is_prod else {1: 0.65, 2: 0.35}

    def place(kind, quota, dmin, dmax, ok, apply):
        placed = tries = 0
        max_tries = 500 + 50 * (quota // max(dmin, 1) + 1)
        while placed < quota and tries < max_tries:
            tries += 1
            d = min(int(rng.integers(dmin, dmax + 1)), quota - placed)
            s = int(rng.integers(0, n - d))
            sl = slice(s, s + d)
            if labels[sl].any() or not ok(sl):
                continue
            apply(sl, d)
            labels[sl] = kind
            placed += d

    def apply_idle_high(sl, d):
        status[sl] = IDLE
        power[sl] = rated * rng.uniform(0.40, 0.80) * (1 + rng.normal(0, 0.03, d))

    def apply_spike(sl, d):
        power[sl] = power[sl] * rng.uniform(1.25, 1.60)

    im = p.interval_min
    d1min = max(2, 30 // im)
    place(1, int(target * shares[1]), d1min, max(d1min, 180 // im),
          lambda sl: (status[sl] != OFF).all(), apply_idle_high)
    d2min = max(1, 5 // im)
    place(2, int(target * shares[2]), d2min, max(d2min, 15 // im),
          lambda sl: (status[sl] == RUN).all(), apply_spike)

    # 5) production_logs per blok (dari status SETELAH tipe 1-2)
    run_cnt = np.bincount(ax.block_id, weights=(status == RUN).astype(float), minlength=nb)
    expected = run_cnt * im / 60.0 * spec["units_per_hour"]
    units = np.clip(np.rint(expected * rng.normal(1.0, 0.04, nb)), 0, None).astype(np.int64)

    # 6) pemborosan tipe 3: mesin menyala tapi produksi nol/rendah pada satu shift
    if 3 in shares:
        quota3 = int(target * shares[3])
        placed = 0
        for b in rng.permutation(nb):
            if placed >= quota3:
                break
            sl = slice(int(b) * bl, (int(b) + 1) * bl)
            runmask = (status[sl] == RUN) & (labels[sl] == 0)
            cnt = int(runmask.sum())
            if cnt < 0.6 * bl:
                continue
            labels[sl][runmask] = 3
            units[b] = 0 if rng.random() < 0.5 else int(round(expected[b] * rng.uniform(0.0, 0.05)))
            placed += cnt

    # 7) tegangan, arus, energi (konsisten dengan daya)
    voltage = np.round(np.clip(rng.normal(392.0, 2.5, n), 380.0, 400.0), 1)
    power = np.round(np.maximum(power, 0.0), 3)
    current = np.round(power * 1000.0 / (math.sqrt(3) * voltage * POWER_FACTOR), 2)
    energy = np.round(power * im / 60.0, 5)
    return {"power": power, "voltage": voltage, "current": current, "energy": energy,
            "status": status, "labels": labels, "units": units}


# --------------------------------------------------------------------------
# Pembuat dokumen
# --------------------------------------------------------------------------
def energy_docs(mid: str, ax: Axis, r: dict) -> List[dict]:
    st = STATUS_NAMES[r["status"]].tolist()
    return [
        {"machine_id": mid, "timestamp": t, "power_kw": pw, "energy_kwh": e,
         "voltage": v, "current": c, "status": s}
        for t, pw, e, v, c, s in zip(ax.ts, r["power"].tolist(), r["energy"].tolist(),
                                     r["voltage"].tolist(), r["current"].tolist(), st)
    ]


def production_docs(mid: str, ax: Axis, units: np.ndarray) -> List[dict]:
    return [{"machine_id": mid, "shift": int(b % 3) + 1, "date": ax.dates[b // 3],
             "units_produced": int(units[b])} for b in range(ax.days * 3)]


def label_docs(mid: str, ax: Axis, labels: np.ndarray) -> List[dict]:
    return [{"machine_id": mid, "timestamp": ax.ts[i], "is_waste": True,
             "waste_type": WASTE_NAMES[int(labels[i])]} for i in np.nonzero(labels)[0].tolist()]


# --------------------------------------------------------------------------
# Orkestrasi
# --------------------------------------------------------------------------
def generate(p: GenParams, uri: Optional[str] = None, db_name: Optional[str] = None,
             drop: bool = False, dry_run: bool = False, show_progress: bool = True) -> dict:
    t_all = time.perf_counter()
    ax = make_axis(p)
    machines = build_machines(p.machines)
    stats: dict = {"params": p, "n_per_machine": ax.n, "days": ax.days,
                   "first_ts_utc": ax.ts[0], "last_ts_utc": ax.ts[-1],
                   "docs": {c: 0 for c in dbm.COLLECTIONS}, "insert_seconds": {c: 0.0 for c in dbm.COLLECTIONS},
                   "waste": {1: 0, 2: 0, 3: 0}, "status": {RUN: 0, IDLE: 0, OFF: 0},
                   "kwh": {}, "gen_seconds": 0.0, "index_seconds": 0.0, "dry_run": dry_run}
    db = None
    if not dry_run:
        dbm.ping(uri)
        db = dbm.get_db(db_name, uri)
        stats["db_name"] = db.name
        if drop:
            for c in dbm.COLLECTIONS:
                db[c].drop()
        elif db["energy_readings"].estimated_document_count() > 0:
            raise RuntimeError("Koleksi energy_readings sudah berisi data. Tambahkan --drop untuk reset.")
        mdocs = [{k: m[k] for k in ("machine_id", "name", "line", "type", "rated_power_kw")} for m in machines]
        res = dbm.bulk_insert(db["machines"], mdocs)
        stats["docs"]["machines"] = res.inserted
        stats["insert_seconds"]["machines"] += res.seconds
    else:
        stats["docs"]["machines"] = len(machines)

    bar = None
    if show_progress and not dry_run and tqdm is not None:
        bar = tqdm(total=len(machines) * (ax.n + ax.days * 3), unit="dok", desc="Insert")

    for i, spec in enumerate(machines):
        t0 = time.perf_counter()
        rng = np.random.default_rng([p.seed, i])
        r = simulate_machine(spec, ax, p, rng)
        for k in (1, 2, 3):
            stats["waste"][k] += int((r["labels"] == k).sum())
        for k in (RUN, IDLE, OFF):
            stats["status"][k] += int((r["status"] == k).sum())
        stats["kwh"][spec["machine_id"]] = float(r["energy"].sum())
        if dry_run:
            stats["docs"]["energy_readings"] += ax.n
            stats["docs"]["production_logs"] += ax.days * 3
            stats["docs"]["waste_labels"] += int((r["labels"] > 0).sum())
            stats["gen_seconds"] += time.perf_counter() - t0
            continue
        batches = (("energy_readings", energy_docs(spec["machine_id"], ax, r), bar),
                   ("production_logs", production_docs(spec["machine_id"], ax, r["units"]), bar),
                   ("waste_labels", label_docs(spec["machine_id"], ax, r["labels"]), None))
        stats["gen_seconds"] += time.perf_counter() - t0
        for coll, docs, b in batches:
            res = dbm.bulk_insert(db[coll], docs, 10_000, b)
            stats["docs"][coll] += res.inserted
            stats["insert_seconds"][coll] += res.seconds
    if bar is not None:
        bar.close()

    if not dry_run:
        t0 = time.perf_counter()
        dbm.create_indexes(db)
        stats["index_seconds"] = time.perf_counter() - t0
    stats["total_seconds"] = time.perf_counter() - t_all
    return stats


def print_summary(s: dict, uri: Optional[str]) -> None:
    p: GenParams = s["params"]
    n_energy = s["docs"]["energy_readings"]
    waste_total = sum(s["waste"].values())
    line = "=" * 64
    print(f"\n{line}\nRINGKASAN {'(DRY-RUN, tidak ada data ditulis)' if s['dry_run'] else 'GENERATE DATA'}\n{line}")
    if not s["dry_run"]:
        print(f"Database        : {s['db_name']}  ({uri or dbm.DEFAULT_URI})")
    print(f"Parameter       : machines={p.machines} days={s['days']} interval={p.interval_min} menit "
          f"seed={p.seed} waste_rate={p.waste_rate}")
    f, l = s["first_ts_utc"], s["last_ts_utc"]
    wib = timedelta(hours=7)
    print(f"Rentang (UTC)   : {f:%Y-%m-%d %H:%M} s/d {l:%Y-%m-%d %H:%M}")
    print(f"Rentang (WIB)   : {f + wib:%Y-%m-%d %H:%M} s/d {l + wib:%Y-%m-%d %H:%M}")
    print("Jumlah dokumen  :")
    for c in dbm.COLLECTIONS:
        print(f"  {c:16s} {s['docs'][c]:>12,d}")
    pct = 100.0 * waste_total / max(n_energy, 1)
    print(f"Baris pemborosan: {waste_total:,d} ({pct:.2f}% dari energy_readings)")
    for k, nm in WASTE_NAMES.items():
        print(f"  {nm:24s} {s['waste'][k]:>8,d}")
    tot = max(sum(s["status"].values()), 1)
    print("Distribusi status: " + ", ".join(
        f"{STATUS_NAMES[k]}={100 * v / tot:.1f}%" for k, v in s["status"].items()))
    print(f"Total energi     : {sum(s['kwh'].values()):,.0f} kWh")
    print(f"Waktu generate   : {s['gen_seconds']:.1f} s")
    if not s["dry_run"]:
        ins = sum(s["insert_seconds"].values())
        e_sec = s["insert_seconds"]["energy_readings"]
        print(f"Waktu insert     : {ins:.1f} s (energy_readings {n_energy / max(e_sec, 1e-9):,.0f} dok/s)")
        print(f"Waktu bikin index: {s['index_seconds']:.1f} s")
    print(f"Total waktu      : {s['total_seconds']:.1f} s\n{line}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generator data simulasi Smart Factory Energy")
    ap.add_argument("--machines", type=int, default=12)
    ap.add_argument("--months", type=int, default=6, help="1 bulan = 30 hari")
    ap.add_argument("--days", type=int, default=None, help="override --months (mis. 7 untuk uji kecil)")
    ap.add_argument("--interval-min", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--waste-rate", type=float, default=0.04)
    ap.add_argument("--start-date", default="2026-01-01", help="tanggal WIB awal, data mulai 07:00 WIB")
    ap.add_argument("--drop", action="store_true", help="reset koleksi sebelum insert")
    ap.add_argument("--uri", default=None, help="default: env MONGO_URI atau mongodb://localhost:27017")
    ap.add_argument("--db", default=None, help="nama database (default smart_energy)")
    ap.add_argument("--dry-run", action="store_true", help="simulasi tanpa MongoDB")
    a = ap.parse_args()
    p = GenParams(a.machines, a.months, a.interval_min, a.seed, a.waste_rate, a.start_date, a.days)
    try:
        s = generate(p, uri=a.uri, db_name=a.db, drop=a.drop, dry_run=a.dry_run)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # koneksi gagal dll.
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print_summary(s, a.uri)
    return 0


if __name__ == "__main__":
    sys.exit(main())
