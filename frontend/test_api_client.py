"""
frontend/test_api_client.py
==========================

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
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# -- Tolak jika seseorang menjalankan dengan USE_MOCK=true --------------------
if os.environ.get("USE_MOCK", "false").lower() in ("true", "1", "yes"):
    print("ERROR: Jalankan tes ini tanpa USE_MOCK=true. Backend harus aktif.")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import frontend.api_client as ac

importlib.reload(ac)

SEP = "-" * 60
PASS_TOTAL = 0
FAIL_TOTAL = 0
POINT_STATUS = {}

POINT_NAMES = {
    1: "get_machines",
    2: "get_summary",
    3: "get_energy",
    4: "check_api/_get/fallback-mock",
    5: "forecast/waste-alerts",
}


def hr(label):
    print(f"\n{SEP}\n  {label}\n{SEP}")


def dump(obj, indent=2):
    if isinstance(obj, (dict, list)):
        print(json.dumps(obj, indent=indent, default=str))
    else:
        print(repr(obj))


def ok(msg):
    global PASS_TOTAL
    PASS_TOTAL += 1
    print(f"  [OK] {msg}")


def fail(msg):
    global FAIL_TOTAL
    FAIL_TOTAL += 1
    print(f"  [GAGAL] {msg}")


def set_point(n, passed):
    POINT_STATUS[n] = bool(passed)


def close(a, b, tol):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


# Batas keras API per request dan toleransi konsistensi
LIMIT = 10_000        # batas keras backend per request
TOL_KWH = 0.5         # toleransi konsistensi jumlah kWh
TOL_COST_RP = 100     # toleransi konsistensi estimasi biaya (Rp)
TARIFF_PER_KWH = 1500  # Rp per kWh (konstanta backend)
TOL_AGG = 0.01        # toleransi kecil untuk cek konsistensi agregasi

# ---------------------------------------------------------------------------
hr("0. check_api() - indikator status backend")
alive = ac.check_api()
print(f"  Backend tersedia: {alive}")
tes0_ok = alive is True
if tes0_ok:
    ok("check_api() mengembalikan True saat backend hidup")
else:
    fail("check_api() mengembalikan True saat backend hidup")

# ---------------------------------------------------------------------------
hr("1. get_machines()")
machines = ac.get_machines()
dump(machines)
tes1_ok = True
if not isinstance(machines, list) or len(machines) == 0:
    tes1_ok = False
else:
    required_keys = ("machine_id", "name", "line", "type", "rated_power_kw")
    for m in machines:
        if not isinstance(m, dict) or not all(k in m for k in required_keys):
            tes1_ok = False
            break
    machine_ids = [m.get("machine_id") for m in machines]
    if len(set(machine_ids)) != len(machine_ids):
        tes1_ok = False
if tes1_ok:
    ok(f"get_machines OK - jumlah mesin > 0, field lengkap, machine_id unik")
else:
    fail("get_machines GAGAL - jumlah > 0, field lengkap, machine_id unik")
set_point(1, tes1_ok)

# ---------------------------------------------------------------------------
hr("2. get_summary()")
summary = ac.get_summary()
dump(summary)
tes2_ok = True
summary_keys = ("total_kwh", "estimated_cost_rp", "per_line", "alert_count")
if not isinstance(summary, dict) or not all(k in summary for k in summary_keys):
    tes2_ok = False
else:
    total_kwh = float(summary["total_kwh"])
    per_line = summary["per_line"]
    if not isinstance(per_line, dict):
        tes2_ok = False
    else:
        per_line_sum = sum(float(v) for v in per_line.values())
        if not close(per_line_sum, total_kwh, TOL_KWH):
            tes2_ok = False
        if not close(float(summary["estimated_cost_rp"]), total_kwh * TARIFF_PER_KWH, TOL_COST_RP):
            tes2_ok = False
if tes2_ok:
    ok(f"get_summary OK - total_kwh {summary['total_kwh']}, per_line konsisten, estimasi biaya valid")
else:
    fail("get_summary GAGAL - konsistensi per_line, total_kwh, estimasi biaya")
set_point(2, tes2_ok)

# ---------------------------------------------------------------------------
hr("3. get_energy() dan aggregate_hourly()")
tes3_ok = True
first_machine = machines[0] if machines else {}
mid = first_machine.get("machine_id") if isinstance(first_machine, dict) else None
if not mid:
    mid = "M01"
day_start, _day_end = ac.get_data_range(mid)
day_end = day_start + timedelta(days=1)
rows = ac.get_energy(mid, day_start, day_end, limit=LIMIT)
dump(rows[:3])
print(f"  ... (total {len(rows)} baris)")
if not isinstance(rows, list) or len(rows) == 0:
    tes3_ok = False
elif len(rows) >= LIMIT:
    tes3_ok = False
else:
    energy_keys = ("machine_id", "timestamp", "power_kw", "energy_kwh", "voltage", "current", "status")
    if not all(k in rows[0] for k in energy_keys):
        tes3_ok = False
    elif not all(r.get("machine_id") == mid for r in rows):
        tes3_ok = False
    else:
        df_h = ac.aggregate_hourly(rows)
        sum_raw = sum(float(r.get("energy_kwh") or 0) for r in rows)
        sum_hourly = float(df_h["energy_kwh"].sum()) if not df_h.empty else 0.0
        if not close(sum_hourly, sum_raw, TOL_AGG):
            tes3_ok = False
if tes3_ok:
    ok(f"get_energy OK - mesin {mid}, rentang 1 hari, {len(rows)} baris (< {LIMIT}), field lengkap, agregasi konsisten")
else:
    fail("get_energy/aggregate_hourly GAGAL - rentang 1 hari, field, atau konsistensi agregasi")
set_point(3, tes3_ok)

# ---------------------------------------------------------------------------
hr("4. check_api() port salah, _get() port salah, fallback mock hanya HTTP 503")

tes4_ok = True

alive_bad = ac.check_api(base_url="http://127.0.0.1:9999")
print(f"  check_api(port=9999) = {alive_bad}")
if alive_bad is False:
    ok("check_api OK - port mati -> False, tanpa exception")
else:
    tes4_ok = False
    fail("check_api GAGAL - port mati harus False")

raised = False
try:
    ac._get("/summary", base_url="http://127.0.0.1:9999")
except RuntimeError as exc:
    raised = True
    print(f"  Exception tertangkap (benar): {exc}")
if raised:
    ok("_get OK - port mati -> RuntimeError")
else:
    tes4_ok = False
    fail("_get GAGAL - port mati harus melempar RuntimeError")

class StubHandler(BaseHTTPRequestHandler):
    status_code = 503

    def do_GET(self):
        body = json.dumps({"detail": "stub"}).encode("utf-8")
        self.send_response(self.status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


stub_server = ThreadingHTTPServer(("127.0.0.1", 9998), StubHandler)
threading.Thread(target=stub_server.serve_forever, daemon=True).start()
orig_base = ac.BASE_URL
ac.BASE_URL = "http://127.0.0.1:9998"
try:
    fc_stub = ac.get_forecast("M01", hours=1)
    if isinstance(fc_stub, dict) and fc_stub.get("is_mock") is True and isinstance(fc_stub.get("predictions"), list):
        ok("get_forecast OK - fallback mock hanya untuk HTTP 503 (is_mock True)")
    else:
        tes4_ok = False
        fail("get_forecast GAGAL - fallback mock hanya untuk HTTP 503")

    wa_stub = ac.get_waste_alerts("M01")
    if isinstance(wa_stub, dict) and wa_stub.get("is_mock") is True and isinstance(wa_stub.get("alerts"), list):
        ok("get_waste_alerts OK - fallback mock hanya untuk HTTP 503 (is_mock True)")
    else:
        tes4_ok = False
        fail("get_waste_alerts GAGAL - fallback mock hanya untuk HTTP 503")

    StubHandler.status_code = 404
    raised_404 = False
    try:
        ac.get_forecast("M01", hours=2)
    except RuntimeError:
        raised_404 = True
    if raised_404:
        ok("get_forecast OK - error non-503 (404) tetap melempar RuntimeError")
    else:
        tes4_ok = False
        fail("get_forecast GAGAL - error non-503 harus melempar RuntimeError")
finally:
    ac.BASE_URL = orig_base
    stub_server.shutdown()
    stub_server.server_close()

set_point(4, tes4_ok)

# ---------------------------------------------------------------------------
hr("5. get_forecast() dan get_waste_alerts() - bentuk respons dan is_mock")

tes5_ok = True
fc_machine = machines[0]["machine_id"] if machines else "M01"
fc = ac.get_forecast(fc_machine, hours=6)
dump(fc)
if not isinstance(fc, dict):
    tes5_ok = False
elif not isinstance(fc.get("is_mock"), bool):
    tes5_ok = False
elif fc.get("machine_id") != fc_machine:
    tes5_ok = False
else:
    preds = fc.get("predictions")
    if not isinstance(preds, list):
        tes5_ok = False
    else:
        for p in preds:
            if not isinstance(p, dict) or "forecast_time" not in p or "predicted_kwh" not in p:
                tes5_ok = False
                break
if tes5_ok:
    ok(f"get_forecast OK - is_mock bool, machine_id, bentuk predictions valid ({fc_machine})")
else:
    fail(f"get_forecast GAGAL - is_mock bool, machine_id, bentuk predictions ({fc_machine})")

waste_machine = machines[1]["machine_id"] if len(machines) > 1 else "M02"
wa = ac.get_waste_alerts(waste_machine)
dump(wa)
wa_ok = True
if not isinstance(wa, dict):
    wa_ok = False
elif not isinstance(wa.get("is_mock"), bool):
    wa_ok = False
else:
    alerts = wa.get("alerts")
    if not isinstance(alerts, list):
        wa_ok = False
    else:
        for a in alerts:
            if not isinstance(a, dict) or not all(k in a for k in ("machine_id", "timestamp", "type", "severity", "note")):
                wa_ok = False
                break
if wa_ok:
    ok(f"get_waste_alerts OK - is_mock bool, bentuk alerts valid ({waste_machine})")
else:
    fail(f"get_waste_alerts GAGAL - is_mock bool, bentuk alerts ({waste_machine})")

set_point(5, tes5_ok and wa_ok)

# ---------------------------------------------------------------------------
print(f"\n{SEP}")
print("RINGKASAN TUGAS - POIN 1 SAMPA 5")
print(f"{SEP}")
for n in (1, 2, 3, 4, 5):
    status = "sudah" if POINT_STATUS.get(n, False) else "belum"
    print(f"  {n}. {POINT_NAMES[n]} : {status}")
print(f"{SEP}")
print(f"  HASIL TES: {PASS_TOTAL} LULUS, {FAIL_TOTAL} GAGAL")
print(f"  Backend  : {ac.BASE_URL} - sedang berjalan")
print(f"{SEP}")

if FAIL_TOTAL > 0:
    sys.exit(1)
