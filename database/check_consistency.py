"""Cek konsistensi total kWh antar fungsi agregasi (untuk kartu biaya, chart per lini, per shift)."""
import db

TARIF = 1500.0
TOL = 5.0  # kWh; selisih pembulatan 3 desimal pada ribuan baris

s = db.summary(tariff_per_kwh=TARIF)
total = s["total_kwh"]
per_line = sum(r["total_kwh"] for r in s["per_line"])
daily = sum(r["total_kwh"] for r in db.daily_kwh_per_machine())
shift = sum(r["total_kwh"] for r in db.kwh_per_shift())
cost_expected = round(total * TARIF, 2)

def ok(label, a, b, tol=TOL):
    good = abs(a - b) <= tol
    print(f"[{'PASS' if good else 'FAIL'}] {label}: {a:,.3f} vs {b:,.3f} (selisih {abs(a-b):.3f})")
    return good

results = [
    ok("total summary vs jumlah per lini", total, per_line),
    ok("total summary vs jumlah per mesin per hari", total, daily),
    ok("total summary vs jumlah per shift", total, shift),
    ok("biaya = total kWh x tarif", s["total_cost"], cost_expected, tol=1.0),
]
print("\nBaris per_shift:", len(db.kwh_per_shift()), "(harapan 12 mesin x 180 hari x 3 = 6.480)")
print("HASIL:", "SEMUA LOLOS" if all(results) else "ADA YANG GAGAL")
