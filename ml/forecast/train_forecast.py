"""Training model forecasting energi.
Jalankan dari ROOT repo:  python -m ml.forecast.train_forecast data/energy_readings_sample.csv
Bisa juga di-paste per blok (# %%) ke Jupyter notebook.
"""
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

from ml.forecast.features import FEATURES, add_features, to_hourly

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "data/energy_readings_sample.csv"
MODEL_PATH = "ml/models/forecast.pkl"

# %% 1. Load + cek missing value
raw = pd.read_csv(CSV_PATH)
print(raw.shape)
print(raw.isna().sum())

# %% 2. Resample per jam
hourly = to_hourly(raw)
machine_map = {m: i for i, m in enumerate(sorted(hourly["machine_id"].unique()))}

# %% 3. EDA (simpan gambar buat laporan)
wib = hourly["timestamp"].dt.tz_convert("Asia/Jakarta")
hourly["hour"] = wib.dt.hour
hourly.groupby("hour")["energy_kwh"].mean().plot(title="Rata-rata kWh per jam (WIB)")
plt.savefig("ml/forecast/eda_hourly_profile.png", dpi=120); plt.clf()
hourly["dow"] = wib.dt.day_of_week
hourly.groupby("dow")["energy_kwh"].mean().plot(kind="bar", title="Rata-rata kWh per hari (0=Senin)")
plt.savefig("ml/forecast/eda_weekly_profile.png", dpi=120); plt.clf()

# %% 4. Feature engineering
df = add_features(hourly, machine_map).dropna(subset=FEATURES + ["energy_kwh"])

# %% 5. Split BERDASARKAN WAKTU (80% awal train, 20% akhir test), bukan acak
cut = df["timestamp"].quantile(0.8)
train, test = df[df["timestamp"] <= cut], df[df["timestamp"] > cut]
Xtr, ytr, Xte, yte = train[FEATURES], train["energy_kwh"], test[FEATURES], test["energy_kwh"]
print(f"train={len(train)}  test={len(test)}  cutoff={cut}")

# %% 6. Training + bandingkan model
models = {
    "LinearRegression": LinearRegression(),
    "RandomForest": RandomForestRegressor(n_estimators=150, max_depth=14, min_samples_leaf=5,
                                              n_jobs=-1, random_state=42),
}
try:
    from xgboost import XGBRegressor
    models["XGBoost"] = XGBRegressor(n_estimators=400, learning_rate=0.05, max_depth=6,
                                     subsample=0.8, random_state=42)
except ImportError:
    print("xgboost belum terinstall -> pip install xgboost (dilewati dulu)")


def mape(y, p, min_kwh=1.0):
    m = y >= min_kwh   # jam mesin off/idle (kWh ~0) bikin MAPE meledak -> diabaikan
    return float(np.mean(np.abs((y[m] - p[m]) / y[m])) * 100)


def wape(y, p):
    # Weighted APE: total error / total aktual -> stabil walau banyak jam dengan kWh kecil
    return float(np.abs(y - p).sum() / y.sum() * 100)


rows, preds = [], {}
for name, mdl in models.items():
    mdl.fit(Xtr, ytr)
    p = mdl.predict(Xte)
    preds[name] = p
    rows.append({"model": name,
                 "MAE": mean_absolute_error(yte, p),
                 "RMSE": float(np.sqrt(mean_squared_error(yte, p))),
                 "MAPE_%": mape(yte.values, p),
                 "WAPE_%": wape(yte.values, p)})

# %% 7. Tabel evaluasi + plot aktual vs prediksi
result = pd.DataFrame(rows).sort_values("RMSE").round(4)
print(result.to_string(index=False))
result.to_csv("ml/forecast/hasil_evaluasi.csv", index=False)

best_name = result.iloc[0]["model"]
one = test["machine_id"].iloc[0]
mask = (test["machine_id"] == one).values
plt.figure(figsize=(12, 4))
plt.plot(test["timestamp"][mask].values[:168], yte.values[mask][:168], label="Aktual")
plt.plot(test["timestamp"][mask].values[:168], preds[best_name][mask][:168], label=f"Prediksi ({best_name})")
plt.title(f"Aktual vs Prediksi - {one} (7 hari pertama data test)")
plt.legend(); plt.tight_layout()
plt.savefig("ml/forecast/aktual_vs_prediksi.png", dpi=120)

# %% 8. Simpan model terbaik
joblib.dump({"model": models[best_name], "features": FEATURES,
             "machine_map": machine_map, "model_name": best_name}, MODEL_PATH, compress=3)
print("Model terbaik:", best_name, "->", MODEL_PATH)
