#!/usr/bin/env python3
"""
benchmark.py - Volume, ukuran, kinerja insert, dan kinerja query (sebelum/sesudah index).
Menghasilkan laporan siap kutip di benchmark_report/ (CSV + Markdown).

  python benchmark.py                 # lengkap: volume, ukuran, insert test, query 100k/300k/penuh x5
  python benchmark.py --quick         # cepat: hanya data penuh, 1x ulang, tanpa insert test (demo explain)
  python benchmark.py --bench-1min    # + uji skalabilitas interval 1 menit di DB smart_energy_bench
  python benchmark.py --skip-insert   # lewati insert test (butuh regenerasi data ~1-2 menit)

Catatan:
- Database utama TIDAK diubah. Subset data disalin ke DB sementara smart_energy_bench_tmp
  (butuh MongoDB >= 4.4 untuk $out ke DB lain; ada fallback salin lewat Python).
- Query 'top5_waste_kwh' tanpa index sangat lambat (ribuan $lookup x COLLSCAN) -> dibatasi
  --timeout-sec dan dilaporkan sebagai 'timeout'.
"""
from __future__ import annotations

import argparse
import csv
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timedelta

import pymongo
from pymongo.errors import ExecutionTimeout, OperationFailure

import db as dbm
import generate_data as gd

HERE = os.path.dirname(os.path.abspath(__file__))
TMP_DB, INS_DB, BIG_DB = "smart_energy_bench_tmp", "smart_energy_bench_insert", "smart_energy_bench"
MB = 1024.0 ** 2


# ----------------------------------------------------------------------------- util
def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def sys_info(client):
    cpu = platform.processor()
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    try:
        import psutil
        ram = f"{psutil.virtual_memory().total / 1024 ** 3:.1f} GB"
        cores = f"{psutil.cpu_count(logical=False)} fisik / {psutil.cpu_count(logical=True)} logis"
    except ImportError:
        ram, cores = "n/a (pip install psutil)", f"{os.cpu_count()} logis"
    return [("OS", f"{platform.system()} {platform.release()}"), ("CPU", cpu or "n/a"), ("Core", cores),
            ("RAM", ram), ("MongoDB", client.server_info()["version"]),
            ("Python", platform.python_version()), ("PyMongo", pymongo.version)]


def infer_interval(db):
    mid = db["machines"].find_one(sort=[("machine_id", 1)])["machine_id"]
    two = list(db["energy_readings"].find({"machine_id": mid}, {"timestamp": 1}).sort("timestamp", 1).limit(2))
    return int((two[1]["timestamp"] - two[0]["timestamp"]).total_seconds() // 60)


# ----------------------------------------------------------------------------- volume & ukuran
def volume_section(db):
    counts = {c: db[c].estimated_document_count() for c in dbm.COLLECTIONS}
    first = db["energy_readings"].find_one(sort=[("timestamp", 1)])["timestamp"]
    last = db["energy_readings"].find_one(sort=[("timestamp", -1)])["timestamp"]
    wib = timedelta(hours=7)
    interval = infer_interval(db)
    n_e = max(counts["energy_readings"], 1)
    vol = [("Jumlah mesin", counts["machines"]), ("Interval (menit)", interval),
           ("Rentang UTC", f"{first:%Y-%m-%d %H:%M} s/d {last:%Y-%m-%d %H:%M}"),
           ("Rentang WIB", f"{first + wib:%Y-%m-%d %H:%M} s/d {last + wib:%Y-%m-%d %H:%M}"),
           ("Jumlah hari", round((last - first).total_seconds() / 86400 + interval / 1440)),
           ("Persentase pemborosan", f"{100.0 * counts['waste_labels'] / n_e:.2f}%")]
    vol += [(f"Dokumen {c}", f"{n:,d}") for c, n in counts.items()]
    sizes = []
    for c in dbm.COLLECTIONS:
        try:
            s = db.command("collStats", c)
        except OperationFailure:
            continue
        sizes.append({"collection": c, "docs": s.get("count", 0), "dataSize_MB": round(s["size"] / MB, 2),
                      "storageSize_MB": round(s["storageSize"] / MB, 2),
                      "indexSize_MB": round(s["totalIndexSize"] / MB, 2),
                      "avgDocSize_MB": round(s.get("avgObjSize", 0) / MB, 6),
                      "avgDocSize_bytes": s.get("avgObjSize", 0)})
    return vol, sizes


# ----------------------------------------------------------------------------- insert test
def insert_test(uri, p, client):
    print(f"[insert] regenerasi data ke {INS_DB} (batch 10.000)...")
    s = gd.generate(p, uri=uri, db_name=INS_DB, drop=True, show_progress=True)
    rows = []
    for c in ("energy_readings", "production_logs", "waste_labels", "machines"):
        sec, n = s["insert_seconds"][c], s["docs"][c]
        rows.append({"collection": c, "docs": n, "insert_seconds": round(sec, 2),
                     "docs_per_second": round(n / sec) if sec > 0 else 0})
    tot_n, tot_s = sum(r["docs"] for r in rows), sum(r["insert_seconds"] for r in rows)
    rows.append({"collection": "TOTAL", "docs": tot_n, "insert_seconds": round(tot_s, 2),
                 "docs_per_second": round(tot_n / tot_s) if tot_s else 0})
    extra = {"generate_seconds": round(s["gen_seconds"], 1), "index_seconds": round(s["index_seconds"], 1)}
    client.drop_database(INS_DB)
    return rows, extra


# ----------------------------------------------------------------------------- subset
def _copy(client, src, coll, dst, flt):
    try:
        list(src[coll].aggregate([{"$match": flt}, {"$out": {"db": dst, "coll": coll}}], allowDiskUse=True))
    except OperationFailure:
        dbm.bulk_insert(client[dst][coll], src[coll].find(flt, {"_id": 0}))


def build_subset(client, src, target, interval):
    client.drop_database(TMP_DB)
    first = src["energy_readings"].find_one(sort=[("timestamp", 1)])["timestamp"]
    last = src["energy_readings"].find_one(sort=[("timestamp", -1)])["timestamp"]
    n_m = max(src["machines"].count_documents({}), 1)
    if target == "full":
        cutoff = last + timedelta(minutes=interval)
    else:
        cutoff = first + timedelta(minutes=interval * max(1, int(target) // n_m))
    for coll in ("energy_readings", "waste_labels"):
        _copy(client, src, coll, TMP_DB, {"timestamp": {"$lt": cutoff}})
    _copy(client, src, "machines", TMP_DB, {})
    dbm.drop_indexes(client[TMP_DB])
    return client[TMP_DB]


# ----------------------------------------------------------------------------- query + explain
def make_queries(db, interval):
    mid = db["machines"].find_one(sort=[("machine_id", 1)])["machine_id"]
    first = db["energy_readings"].find_one(sort=[("timestamp", 1)])["timestamp"]
    ws = first + timedelta(days=min(30, 1))  # minggu setelah hari pertama (aman utk subset kecil)
    flt = {"machine_id": mid, "timestamp": {"$gte": ws, "$lt": ws + timedelta(days=7)}}
    qs = [{"key": "energy_1machine_1week", "kind": "find", "coll": "energy_readings", "filter": flt}]
    for key, (coll, pl) in (("daily_kwh_per_machine", dbm.pipeline_daily_kwh_per_machine()),
                            ("avg_kwh_per_hour", dbm.pipeline_avg_kwh_per_hour(per_machine=True)),
                            ("top5_kwh", dbm.pipeline_top_machines_by_kwh(5)),
                            ("top5_waste_kwh", dbm.pipeline_top_machines_by_waste_energy(5))):
        qs.append({"key": key, "kind": "agg", "coll": coll, "pipeline": pl})
    return qs


def run_query(db, q, timeout_ms):
    t0 = time.perf_counter()
    if q["kind"] == "find":
        n = len(list(db[q["coll"]].find(q["filter"], {"_id": 0}).sort("timestamp", 1).max_time_ms(timeout_ms)))
    else:
        n = len(list(db[q["coll"]].aggregate(q["pipeline"], allowDiskUse=True, maxTimeMS=timeout_ms)))
    return (time.perf_counter() - t0) * 1000.0, n


def explain_query(db, q, timeout_ms):
    if q["kind"] == "find":
        inner = {"find": q["coll"], "filter": q["filter"], "sort": {"timestamp": 1}, "maxTimeMS": timeout_ms}
    else:
        inner = {"aggregate": q["coll"], "pipeline": q["pipeline"], "cursor": {}, "allowDiskUse": True,
                 "maxTimeMS": timeout_ms}
    return db.command({"explain": inner, "verbosity": "executionStats"})


def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def summarize_explain(ex):
    stats, stages, lookup = None, set(), None
    for d in _walk(ex):
        if stats is None and isinstance(d.get("executionStats"), dict):
            stats = d["executionStats"]
        if isinstance(d.get("stage"), str):
            stages.add(d["stage"])
        if lookup is None and isinstance(d.get("$lookup"), dict):
            lookup = d["$lookup"]
    stats = stats or {}
    scan = "IXSCAN" if "IXSCAN" in stages else ("COLLSCAN" if "COLLSCAN" in stages else "/".join(sorted(stages)))
    out = {"scan_stage": scan, "docs_examined": stats.get("totalDocsExamined"),
           "keys_examined": stats.get("totalKeysExamined"), "n_returned": stats.get("nReturned"),
           "explain_ms": stats.get("executionTimeMillis"), "lookup_scan": "", "lookup_docs_examined": ""}
    if lookup:
        out["lookup_scan"] = "IXSCAN" if lookup.get("indexesUsed") else ("COLLSCAN" if lookup.get("collectionScans") else "")
        out["lookup_docs_examined"] = lookup.get("totalDocsExamined", "")
    return out


def bench_queries(db, label, indexed, repeats, timeout_ms, interval):
    rows = []
    n_docs = db["energy_readings"].estimated_document_count()
    for q in make_queries(db, interval):
        row = {"dataset": label, "dataset_docs": n_docs, "query": q["key"], "indexed": "ya" if indexed else "tidak",
               "repeats": repeats, "avg_ms": "", "min_ms": "", "max_ms": "", "result_rows": "", "note": ""}
        try:
            run_query(db, q, timeout_ms)  # pemanasan (tidak dihitung)
            times = []
            for _ in range(repeats):
                ms, n = run_query(db, q, timeout_ms)
                times.append(ms)
            row.update(avg_ms=round(statistics.mean(times), 1), min_ms=round(min(times), 1),
                       max_ms=round(max(times), 1), result_rows=n)
        except ExecutionTimeout:
            row["note"] = f"timeout > {timeout_ms // 1000} s"
        try:
            row.update(summarize_explain(explain_query(db, q, timeout_ms)))
        except ExecutionTimeout:
            row["note"] = (row["note"] + "; explain timeout").strip("; ")
        except OperationFailure as e:
            row["note"] = (row["note"] + f"; explain gagal: {e.code}").strip("; ")
        rows.append(row)
        print(f"   {label:>9s} | index={row['indexed']:5s} | {q['key']:24s} | "
              f"{row['avg_ms'] if row['avg_ms'] != '' else row['note']} ms | {row.get('scan_stage', '')}")
    return rows


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri", default=None)
    ap.add_argument("--db", default=None)
    ap.add_argument("--sizes", default="100000,300000,full")
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--timeout-sec", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--waste-rate", type=float, default=0.04)
    ap.add_argument("--skip-insert", action="store_true")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--bench-1min", action="store_true")
    ap.add_argument("--bench-1min-months", type=int, default=3)
    ap.add_argument("--out-dir", default=os.path.join(HERE, "benchmark_report"))
    a = ap.parse_args()
    if a.quick:
        a.sizes, a.repeats, a.skip_insert = "full", 1, True
    os.makedirs(a.out_dir, exist_ok=True)
    timeout_ms = a.timeout_sec * 1000

    dbm.ping(a.uri)
    client = dbm.get_client(a.uri)
    db = dbm.get_db(a.db, a.uri)
    if db["energy_readings"].estimated_document_count() == 0:
        print("ERROR: energy_readings kosong. Jalankan generate_data.py dulu.", file=sys.stderr)
        return 1
    interval = infer_interval(db)
    md = [f"# Laporan Benchmark Smart Energy ({datetime.now():%Y-%m-%d %H:%M})\n"]

    print("[1/4] Volume & ukuran")
    vol, sizes = volume_section(db)
    md += ["## 1. Volume data\n", md_table(["Metrik", "Nilai"], vol), ""]
    write_csv(os.path.join(a.out_dir, "benchmark_volume.csv"), [{"metric": k, "value": v} for k, v in vol], ["metric", "value"])
    sz_fields = ["collection", "docs", "dataSize_MB", "storageSize_MB", "indexSize_MB", "avgDocSize_MB", "avgDocSize_bytes"]
    write_csv(os.path.join(a.out_dir, "benchmark_size.csv"), sizes, sz_fields)
    md += ["## 2. Ukuran penyimpanan (MB)\n", md_table(sz_fields, [[r[f] for f in sz_fields] for r in sizes]), ""]

    if not a.skip_insert:
        print("[2/4] Insert test")
        n_mach = db["machines"].count_documents({})
        days = round(vol[4][1]) if isinstance(vol[4][1], int) else 180
        p = gd.GenParams(machines=n_mach, interval_min=interval, seed=a.seed, waste_rate=a.waste_rate,
                         days=days, start_date=(db["energy_readings"].find_one(sort=[("timestamp", 1)])["timestamp"]
                                                + timedelta(hours=7)).date().isoformat())
        ins, extra = insert_test(a.uri, p, client)
        write_csv(os.path.join(a.out_dir, "benchmark_insert.csv"), ins, ["collection", "docs", "insert_seconds", "docs_per_second"])
        md += ["## 3. Kinerja insert (insert_many, batch 10.000)\n",
               md_table(["collection", "docs", "insert_seconds", "docs_per_second"],
                        [[r[k] for k in ("collection", "docs", "insert_seconds", "docs_per_second")] for r in ins]),
               f"\nWaktu generate di memori: {extra['generate_seconds']} s; waktu membuat index: {extra['index_seconds']} s.\n"]
    else:
        md += ["## 3. Kinerja insert\n\n(dilewati dengan --skip-insert)\n"]

    print("[3/4] Query sebelum/sesudah index")
    all_rows = []
    for s in [x.strip() for x in a.sizes.split(",") if x.strip()]:
        target = "full" if s == "full" else int(s)
        label = "penuh" if s == "full" else f"{int(s) // 1000}k"
        tdb = build_subset(client, db, target, interval)
        for indexed in (False, True):
            if indexed:
                dbm.create_indexes(tdb)
            all_rows += bench_queries(tdb, label, indexed, a.repeats, timeout_ms, interval)
    client.drop_database(TMP_DB)

    if a.bench_1min:
        print("[3b] Skalabilitas interval 1 menit")
        p1 = gd.GenParams(months=a.bench_1min_months, interval_min=1, seed=a.seed, waste_rate=a.waste_rate)
        s1 = gd.generate(p1, uri=a.uri, db_name=BIG_DB, drop=True, show_progress=True)
        n1 = s1["docs"]["energy_readings"]
        sec = s1["insert_seconds"]["energy_readings"]
        md += [f"## 3b. Skalabilitas (database `{BIG_DB}`, interval 1 menit, {a.bench_1min_months} bulan)\n",
               f"- energy_readings: {n1:,d} dokumen; insert {sec:.1f} s ({n1 / max(sec, 1e-9):,.0f} dok/s); index {s1['index_seconds']:.1f} s\n"]
        all_rows += bench_queries(client[BIG_DB], f"1menit-{n1 // 1000}k", True, a.repeats, timeout_ms, 1)

    fields = ["dataset", "dataset_docs", "query", "indexed", "repeats", "avg_ms", "min_ms", "max_ms", "result_rows",
              "scan_stage", "docs_examined", "keys_examined", "n_returned", "explain_ms", "lookup_scan",
              "lookup_docs_examined", "note"]
    write_csv(os.path.join(a.out_dir, "benchmark_query.csv"), all_rows, fields)

    md += ["## 4. Kinerja query (rata-rata ms dari %d kali ulang, setelah 1x pemanasan)\n" % a.repeats]
    piv = {}
    for r in all_rows:
        piv.setdefault((r["dataset"], r["dataset_docs"], r["query"]), {})[r["indexed"]] = r
    trs = []
    for (lab, nd, qk), v in piv.items():
        b, i = v.get("tidak"), v.get("ya")
        fb = b["avg_ms"] if b and b["avg_ms"] != "" else (b["note"] if b else "-")
        fi = i["avg_ms"] if i and i["avg_ms"] != "" else (i["note"] if i else "-")
        sp = round(b["avg_ms"] / i["avg_ms"], 1) if b and i and b["avg_ms"] != "" and i["avg_ms"] not in ("", 0) else "-"
        trs.append([lab, f"{nd:,d}", qk, fb, fi, sp])
    md += [md_table(["data", "docs", "query", "tanpa index (ms)", "dengan index (ms)", "percepatan (x)"], trs), ""]
    md += ["## 5. Hasil explain('executionStats')\n",
           "`nReturned` pada agregasi = dokumen yang keluar dari tahap pembacaan koleksi (bukan jumlah hasil akhir). "
           "Kolom lookup menunjukkan pemindaian koleksi dalam `$lookup`.\n"]
    ex_f = ["dataset", "query", "indexed", "scan_stage", "docs_examined", "n_returned", "explain_ms", "lookup_scan", "lookup_docs_examined"]
    md += [md_table(ex_f, [[r.get(f, "") for f in ex_f] for r in all_rows]), ""]
    md += ["## 6. Spesifikasi mesin uji\n", md_table(["Item", "Nilai"], sys_info(client)), ""]
    path = os.path.join(a.out_dir, "benchmark_summary.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"[4/4] Selesai. Laporan: {a.out_dir}")
    for fn in sorted(os.listdir(a.out_dir)):
        print("  -", fn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
