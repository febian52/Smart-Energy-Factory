"""
frontend/test_api_client.py
===========================
Tes integrasi untuk api_client.py.
Memerlukan backend FastAPI berjalan di API_BASE_URL (default :8000).
USE_MOCK harus FALSE (default) agar tes mengenai backend asli.

Jalankan dari root proyek:
  python -m frontend.test_api_client
"""

import os
import sys
import json
import importlib
from datetime import datetime
from pathlib import Path

# ── Pastikan USE_MOCK=false saat tes ─────────────────────────────────────────
# Tolak jika seseorang menjalankan dengan USE_MOCK=true
if os.environ.get("USE_MOCK", "false").lower() in ("true", "1", "yes"):
    print("ERROR: Jalankan tes ini tanpa USE_MOCK=true. Backend harus aktif.")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import frontend.api_client as ac

# Reload agar env var USE_MOCK=false terbaca bersih
importlib.reload(ac)

SEP = "─" * 60
PASS_TOTAL = 0
FAIL_TOTAL = 0

def hr(label):
    print(f"\n{SEP}\n  {label}\n{SEP}")

def dump(obj, indent=2):
    if isinstance(obj, (dict, list)):
        print(json.dumps(obj, ensure_ascii=False, indent=indent, default=str))
    else:
        print(repr(obj))

def ok(msg):
    global PASS_TOTAL
    PASS_TOTAL += 1
    print(f"  ✓ {msg}")

def fail(msg):
    global FAIL_TOTAL
    FAIL_TOTAL += 1
    print(f"  ✗ GAGAL: {msg}")

# Rentang data seed
SEED_START = datetime(2026, 11, 1)
SEED_END   = datetime(2026, 11, 3, 23, 0)
ALL_MACHINES = ["M01", "M02", "M03"]

# Nilai referensi terverifikasi dari backend hidup
EXPECTED_TOTAL_KWH       = 3569.5
EXPECTED_COST_RP         = 5_354_250
EXPECTED_LINE_A          = 1779.33
EXPECTED_LINE_B          = 1790.17
TOLERANCE                = 0.5   # toleransi pembulatan float

# ── Tes 0: check_api() ────────────────────────────────────────────────────────
hr("0. check_api() – indikator status backend")
alive = ac.check_api()
print(f"  Backend tersedia: {alive}")
assert alive is True, "Backend tidak terjangkau – pastikan uvicorn berjalan di :8000"
ok("check_api() mengembalikan True saat backend hidup")

# ── Tes 1: get_machines() ─────────────────────────────────────────────────────
hr("1. get_machines()")
machines = ac.get_machines()
dump(machines)
assert isinstance(machines, list), "Harus list"
assert len(machines) == 3, f"Harus 3 mesin, dapat {len(machines)}"
required_keys = ("machine_id", "name", "line", "type", "rated_power_kw")
assert all(k in machines[0] for k in required_keys), "Field kurang"
machine_ids = [m["machine_id"] for m in machines]
assert sorted(machine_ids) == sorted(ALL_MACHINES), f"Machine IDs tidak cocok: {machine_ids}"
ok("get_machines OK – 3 mesin, semua field hadir, dari backend asli")

# ── Tes 2: get_energy() ───────────────────────────────────────────────────────
hr("2. get_energy('M01', 2026-11-01, 2026-11-01T23:00)")
rows = ac.get_energy("M01", SEED_START, datetime(2026, 11, 1, 23, 0))
dump(rows[:3])
print(f"  ... (total {len(rows)} baris)")
assert isinstance(rows, list) and len(rows) > 0, "Harus ada data"
energy_keys = ("machine_id", "timestamp", "power_kw", "energy_kwh", "voltage", "current", "status")
assert all(k in rows[0] for k in energy_keys), f"Field kurang: {list(rows[0].keys())}"
assert all(r["machine_id"] == "M01" for r in rows), "machine_id harus M01 semua"
assert len(rows) == 24, f"Harus 24 jam, dapat {len(rows)}"
ok("get_energy OK – 24 baris, semua field hadir, dari backend asli")

# ── Tes 3: aggregate_hourly() ─────────────────────────────────────────────────
hr("3. aggregate_hourly()")
df_h = ac.aggregate_hourly(rows)
print(df_h.to_string(index=False))
assert list(df_h.columns) == ["timestamp", "machine_id", "energy_kwh", "power_kw"]
assert len(df_h) == 24
ok("aggregate_hourly OK – 24 baris, kolom benar")

# ── Tes 4: aggregate_daily() ──────────────────────────────────────────────────
hr("4. aggregate_daily() – 3 hari data M01")
rows3 = ac.get_energy("M01", SEED_START, SEED_END, limit=10_000)
df_d  = ac.aggregate_daily(rows3)
print(df_d.to_string(index=False))
assert len(df_d) == 3, f"Harusnya 3 hari, dapat {len(df_d)}"
ok("aggregate_daily OK – 3 hari")

# ── Tes 5: get_summary() – nilai divalidasi terhadap get_energy ───────────────
hr("5. get_summary() – divalidasi silang dengan penjumlahan get_energy")
summary = ac.get_summary()
dump(summary)

# Cek field
assert all(k in summary for k in ("total_kwh", "estimated_cost_rp", "per_line", "alert_count"))
assert isinstance(summary["per_line"], dict)

# Hitung total_kwh dari get_energy semua mesin
computed_total = 0.0
computed_per_line: dict[str, float] = {}
for mid in ALL_MACHINES:
    r = ac.get_energy(mid, SEED_START, SEED_END, limit=10_000)
    machine_kwh = sum(row["energy_kwh"] for row in r)
    computed_total += machine_kwh
    # Cari line dari machines list
    machine_meta = next(m for m in machines if m["machine_id"] == mid)
    line = machine_meta["line"]
    computed_per_line[line] = round(computed_per_line.get(line, 0.0) + machine_kwh, 2)

computed_total = round(computed_total, 2)
print(f"\n  total_kwh dari summary   : {summary['total_kwh']}")
print(f"  total_kwh dari energy    : {computed_total}")
print(f"  per_line dari summary    : {summary['per_line']}")
print(f"  per_line dari energy     : {computed_per_line}")

# Validasi nilai absolut (dari user)
assert abs(summary["total_kwh"] - EXPECTED_TOTAL_KWH) < TOLERANCE, \
    f"total_kwh {summary['total_kwh']} ≠ ekspektasi {EXPECTED_TOTAL_KWH}"
assert summary["estimated_cost_rp"] == EXPECTED_COST_RP, \
    f"estimated_cost_rp {summary['estimated_cost_rp']} ≠ {EXPECTED_COST_RP}"
assert abs(summary["per_line"].get("Line A", 0) - EXPECTED_LINE_A) < TOLERANCE, \
    f"Line A {summary['per_line'].get('Line A')} ≠ {EXPECTED_LINE_A}"
assert abs(summary["per_line"].get("Line B", 0) - EXPECTED_LINE_B) < TOLERANCE, \
    f"Line B {summary['per_line'].get('Line B')} ≠ {EXPECTED_LINE_B}"

# Validasi silang: summary harus konsisten dengan akumulasi energy
assert abs(summary["total_kwh"] - computed_total) < TOLERANCE, \
    f"summary.total_kwh {summary['total_kwh']} ≠ computed {computed_total}"
for line, computed_kwh in computed_per_line.items():
    summary_kwh = summary["per_line"].get(line, 0)
    assert abs(summary_kwh - computed_kwh) < TOLERANCE, \
        f"{line}: summary={summary_kwh} ≠ computed={computed_kwh}"

ok(f"get_summary OK – total_kwh={summary['total_kwh']}, nilai terverifikasi & konsisten dengan /energy")

# ── Tes 6: get_forecast() – 503 → mock, error lain → exception ───────────────
hr("6. get_forecast() – 503 → mock (is_mock=True)")
fc = ac.get_forecast("M01", hours=6)
dump({**fc, "predictions": fc["predictions"][:3]})
print(f"  ... (total {len(fc['predictions'])} titik prediksi)")
# Backend mengembalikan 503 (ML belum ada) → harus mock
assert fc["is_mock"] is True, "is_mock harus True (backend 503)"
assert len(fc["predictions"]) == 6, f"Harus 6 titik, dapat {len(fc['predictions'])}"
assert all(k in fc["predictions"][0] for k in ("forecast_time", "predicted_kwh"))
ok("get_forecast OK – fallback mock saat 503, is_mock=True, 6 titik, kolom benar")

# ── Tes 7: get_waste_alerts() – 503 → mock ───────────────────────────────────
hr("7. get_waste_alerts() – 503 → mock (is_mock=True)")
wa = ac.get_waste_alerts("M02")
dump(wa)
assert wa["is_mock"] is True, "is_mock harus True (backend 503)"
alerts = wa["alerts"]
assert len(alerts) > 0, "Harus ada alert mock"
assert all(k in alerts[0] for k in ("machine_id", "timestamp", "type", "severity", "note"))
ok("get_waste_alerts OK – fallback mock saat 503, is_mock=True, kolom benar")

# ── Tes 8: get_data_range() ───────────────────────────────────────────────────
hr("8. get_data_range()")
t0, t1 = ac.get_data_range("M01")
print(f"  start : {t0}")
print(f"  end   : {t1}")
assert t0 < t1, "start harus sebelum end"
assert t0 == SEED_START, f"start {t0} ≠ {SEED_START}"
assert t1 == SEED_END,   f"end {t1} ≠ {SEED_END}"
ok(f"get_data_range OK – {t0.date()} s/d {t1}")

# ── Tes 9: check_api() – port salah → False ──────────────────────────────────
hr("9. check_api() dengan port salah (9999) → harus False, bukan exception")
alive_bad = ac.check_api(base_url="http://127.0.0.1:9999")
print(f"  check_api(port=9999) = {alive_bad}")
assert alive_bad is False, "check_api ke port mati harus False"
ok("check_api OK – mengembalikan False untuk port yang tidak terjangkau")

# ── Tes 10: get_summary() – port salah → exception, bukan data palsu ─────────
hr("10. _get('/summary') ke port 9999 → wajib exception, bukan data palsu")
raised = False
try:
    _ = ac._get("/summary", base_url="http://127.0.0.1:9999")
except RuntimeError as exc:
    raised = True
    print(f"  Exception tertangkap (benar): {exc}")
assert raised, "_get('/summary') HARUS melempar RuntimeError saat backend tidak terjangkau"
ok("get_summary dengan port mati → melempar RuntimeError, tidak diam-diam kembalikan data")

# ── Tes 11: get_machines() – port salah → exception ──────────────────────────
hr("11. _get('/machines') ke port 9999 → wajib exception")
raised = False
try:
    _ = ac._get("/machines", base_url="http://127.0.0.1:9999")
except RuntimeError as exc:
    raised = True
    print(f"  Exception tertangkap (benar): {exc}")
assert raised, "_get('/machines') HARUS melempar RuntimeError saat backend tidak terjangkau"
ok("get_machines dengan port mati → melempar RuntimeError")

# ── Tes 12: get_energy() – port salah → exception ────────────────────────────
hr("12. _get('/energy') ke port 9999 → wajib exception")
raised = False
try:
    _ = ac._get(
        "/energy",
        params={"machine_id": "M01", "start": SEED_START.isoformat(),
                "end": SEED_END.isoformat(), "limit": 10},
        base_url="http://127.0.0.1:9999",
    )
except RuntimeError as exc:
    raised = True
    print(f"  Exception tertangkap (benar): {exc}")
assert raised, "_get('/energy') HARUS melempar RuntimeError saat backend tidak terjangkau"
ok("get_energy dengan port mati → melempar RuntimeError")

# ── Ringkasan ─────────────────────────────────────────────────────────────────
print(f"\n{'═'*60}")
if FAIL_TOTAL == 0:
    print(f"  Semua {PASS_TOTAL} tes LULUS ✓")
else:
    print(f"  {PASS_TOTAL} LULUS, {FAIL_TOTAL} GAGAL ✗")
print(f"{'═'*60}")

if FAIL_TOTAL > 0:
    sys.exit(1)
