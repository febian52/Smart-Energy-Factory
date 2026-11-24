"""Training model forecasting energi (strategi DIRECT multi-horizon 1-168 jam).

Jalankan dari ROOT repo:
  python -m ml.forecast.train_forecast data/energy_readings_sample.csv [data/machines.csv]
machines.csv (rated_power_kw) dipakai untuk normalisasi + batas atas prediksi.
Bisa juga di-paste per blok (# %%) ke Jupyter notebook.
"""
import os
import sys
import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error

from ml.forecast.features import FEATURES, MAX_H, build_features, to_hourly, _wib_parts

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "data/energy_readings_sample.csv"
MACHINES_PATH = sys.argv[2] if len(sys.argv) > 2 else "data/machines.csv"
MODEL_PATH = "ml/models/forecast.pkl"
OUT_DIR = "ml/forecast"
rng = np.random.default_rng(42)

# %% 1. Load + cek missing value
raw = pd.read_csv(CSV_PATH)
print(raw.shape)
print(raw[["machine_id", "timestamp", "energy_kwh"]].isna().sum())

# %% 2. Resample per jam -> tabel lebar (kolom = mesin), tanpa NaN
hourly = to_hourly(raw)
wide = (hourly.pivot(index="timestamp", columns="machine_id", values="energy_kwh")
        .asfreq("h").interpolate(limit=3).bfill().ffill())
machines = list(wide.columns)
machine_map = {m: i for i, m in enumerate(machines)}
ts = wide.index.values.astype("datetime64[h]")
N = len(wide)

# %% 3. Rated power per mesin (normalisasi + batas atas prediksi)
if os.path.exists(MACHINES_PATH):
    rated = pd.read_csv(MACHINES_PATH).set_index("machine_id")["rated_power_kw"].astype(float).to_dict()
else:
    print("machines.csv tidak ditemukan -> rated dianggap = kWh per jam maksimum tiap mesin")
    rated = wide.max().to_dict()
rated = {m: float(rated.get(m, wide[m].max())) for m in machines}
Y = {m: wide[m].values / rated[m] for m in machines}   # rasio terhadap kapasitas

# %% 4. EDA (simpan gambar buat laporan)
hour_wib, dow_wib = _wib_parts(ts)
prof = pd.DataFrame({"hour": hour_wib, "dow": dow_wib,
                     "kwh": wide.sum(axis=1).values})
prof.groupby("hour")["kwh"].mean().plot(title="Rata-rata total kWh semua mesin per jam (WIB)")
plt.savefig(f"{OUT_DIR}/eda_hourly_profile.png", dpi=120); plt.clf()
prof.groupby("dow")["kwh"].mean().plot(kind="bar", title="Rata-rata total kWh per hari (0=Senin)")
plt.savefig(f"{OUT_DIR}/eda_weekly_profile.png", dpi=120); plt.clf()

# %% 5. Split BERDASARKAN WAKTU: 80% awal train, 20% akhir test
cut = int(N * 0.8)
print(f"cutoff = {wide.index[cut]}  (train: sebelum, test: sesudah)")
tr_origins = np.arange(168, cut - MAX_H, 3)      # target train semuanya < cutoff
te_origins = np.arange(cut, N - MAX_H, 24)       # target test semuanya setelah cutoff


def make(origins, m):
    X, T = build_features(Y[m], ts, origins, machine_map[m])
    return X, Y[m][T.ravel()], T.ravel()


Xtr_l, ytr_l = [], []
for m in machines:
    X, y, _ = make(tr_origins, m)
    keep = rng.choice(len(X), size=min(40_000, len(X)), replace=False)   # subsample biar training ringan
    Xtr_l.append(X.iloc[keep]); ytr_l.append(y[keep])
Xtr, ytr = pd.concat(Xtr_l, ignore_index=True), np.concatenate(ytr_l)

Xte_l, yte_l, rte_l = [], [], []
for m in machines:
    X, y, _ = make(te_origins, m)
    Xte_l.append(X); yte_l.append(y); rte_l.append(np.full(len(X), rated[m]))
Xte, yte, rte = pd.concat(Xte_l, ignore_index=True), np.concatenate(yte_l), np.concatenate(rte_l)
print(f"train={len(Xtr)} baris  test={len(Xte)} baris")

# %% 6. Training + bandingkan model
models = {
    "LinearRegression": LinearRegression(),
    "RandomForest": RandomForestRegressor(n_estimators=80, max_depth=18, min_samples_leaf=50,
                                          max_samples=0.3, n_jobs=-1, random_state=42),
}
try:
    from xgboost import XGBRegressor
    models["XGBoost"] = XGBRegressor(n_estimators=300, learning_rate=0.08, max_depth=7,
                                     subsample=0.8, tree_method="hist", random_state=42)
except ImportError:
    print("xgboost belum terinstall -> pip install xgboost (dilewati dulu)")


def mape(y, p, min_kwh=1.0):
    m = y >= min_kwh   # jam mesin off/idle (kWh ~0) bikin MAPE meledak -> diabaikan
    return float(np.mean(np.abs((y[m] - p[m]) / y[m])) * 100)


def wape(y, p):
    return float(np.abs(y - p).sum() / y.sum() * 100)


def metrics(name, p_kwh, y_kwh):
    return {"model": name, "MAE": mean_absolute_error(y_kwh, p_kwh),
            "RMSE": float(np.sqrt(mean_squared_error(y_kwh, p_kwh))),
            "MAPE_%": mape(y_kwh, p_kwh), "WAPE_%": wape(y_kwh, p_kwh)}


y_kwh = yte * rte
preds, rows = {}, []
for name, mdl in models.items():
    mdl.fit(Xtr, ytr)
    p = np.clip(mdl.predict(Xte), 0, 1.0) * rte      # batas atas = rated_power_kw
    preds[name] = p
    rows.append(metrics(name, p, y_kwh))
naive = Xte["lag_168h"].values * rte                  # baseline: jam yg sama minggu lalu
preds["SeasonalNaive(168h)"] = naive
rows.append(metrics("SeasonalNaive(168h)", naive, y_kwh))

# %% 7. Tabel evaluasi + error per horizon + plot
result = pd.DataFrame(rows).sort_values("RMSE").round(4)
print(result.to_string(index=False))
result.to_csv(f"{OUT_DIR}/hasil_evaluasi.csv", index=False)

cand = result[result["model"].isin(models)]
best_name = cand.iloc[0]["model"]
bucket = pd.cut(Xte["horizon"], [0, 6, 24, 72, 168], labels=["1-6 jam", "7-24 jam", "25-72 jam", "73-168 jam"])
hz = pd.DataFrame({"bucket": bucket,
                   best_name: np.abs(preds[best_name] - y_kwh),
                   "SeasonalNaive(168h)": np.abs(naive - y_kwh)}).groupby("bucket", observed=True).mean().round(3)
print("\nMAE per horizon (kWh/jam):"); print(hz)
hz.to_csv(f"{OUT_DIR}/hasil_evaluasi_horizon.csv")

m0 = machines[0]
o = te_origins[len(te_origins) // 2]
X1, T1 = build_features(Y[m0], ts, [o], machine_map[m0])
p1 = np.clip(models[best_name].predict(X1), 0, 1.0) * rated[m0]
plt.figure(figsize=(12, 4))
plt.plot(Y[m0][T1.ravel()] * rated[m0], label="Aktual")
plt.plot(p1, label=f"Prediksi 168 jam ({best_name})")
plt.title(f"Aktual vs Prediksi - {m0} (7 hari setelah {wide.index[o]})")
plt.xlabel("jam ke-"); plt.ylabel("kWh/jam"); plt.legend(); plt.tight_layout()
plt.savefig(f"{OUT_DIR}/aktual_vs_prediksi.png", dpi=120)

# %% 8. Simpan model terbaik
joblib.dump({"model": models[best_name], "features": FEATURES, "machine_map": machine_map,
             "rated_kw": rated, "model_name": best_name, "max_horizon": MAX_H},
            MODEL_PATH, compress=3)
print("Model terbaik:", best_name, "->", MODEL_PATH)
