"""
frontend/api_client.py
======================
Klien API untuk Smart Energy Factory.

Konfigurasi via environment variable (atau .env di root proyek):
  API_BASE_URL  – URL backend, default http://localhost:8000
  USE_MOCK      – "true"/"1" untuk paksa data mock, default False

Kebijakan mock:
  • USE_MOCK=true  → get_machines, get_energy, get_summary, get_forecast,
                     get_waste_alerts semuanya pakai data mock.
  • USE_MOCK=false → get_machines, get_energy, get_summary WAJIB berhasil;
                     jika API gagal, lempar RuntimeError (jangan diam-diam
                     kembalikan data palsu).
                     get_forecast & get_waste_alerts fallback ke mock HANYA
                     saat backend merespons HTTP 503 (model belum tersedia).
                     Error lain (koneksi, 4xx, 5xx lainnya) tetap lempar
                     exception.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Konfigurasi
# ---------------------------------------------------------------------------
load_dotenv()  # membaca .env di direktori kerja (root proyek)

BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
_USE_MOCK_RAW: str = os.getenv("USE_MOCK", "false").lower()
USE_MOCK: bool = _USE_MOCK_RAW in ("true", "1", "yes")

TIMEOUT: int = 10          # detik
TIMEOUT_HEALTH: int = 3    # detik – untuk health-check ringan
TARIF_PER_KWH: int = 1500  # Rp – sama dengan konstanta di backend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentinel: apakah streamlit tersedia (untuk cache_data)
# ---------------------------------------------------------------------------
try:
    import streamlit as st
    _HAS_ST = True
except ImportError:
    _HAS_ST = False


def _cache(fn):
    """Dekorator cache: pakai st.cache_data TTL 60 s jika Streamlit jalan,
    jika tidak kembalikan fungsi apa adanya."""
    if _HAS_ST:
        return st.cache_data(ttl=60, show_spinner=False)(fn)
    return fn


# ---------------------------------------------------------------------------
# Data Mock
# ---------------------------------------------------------------------------
_MOCK_MACHINES = [
    {"machine_id": "M01", "name": "CNC Milling 1",  "line": "Line A", "type": "CNC",        "rated_power_kw": 15},
    {"machine_id": "M02", "name": "Kompresor 1",     "line": "Line A", "type": "Compressor", "rated_power_kw": 30},
    {"machine_id": "M03", "name": "Oven 1",          "line": "Line B", "type": "Oven",       "rated_power_kw": 45},
]

def _mock_energy(machine_id: str, start: datetime, end: datetime, limit: int) -> list[dict]:
    """Bangkitkan data energi tiruan sesuai logika seed_dummy.py."""
    import random
    rows: list[dict] = []
    rated = next((m["rated_power_kw"] for m in _MOCK_MACHINES if m["machine_id"] == machine_id), 15)
    cur = start
    while cur <= end and len(rows) < limit:
        running = 7 <= cur.hour < 22
        ratio = random.uniform(0.70, 0.95) if running else random.uniform(0.05, 0.15)
        power = round(rated * ratio, 2)
        rows.append({
            "machine_id": machine_id,
            "timestamp": cur.isoformat(),
            "power_kw": power,
            "energy_kwh": power,
            "voltage": 380,
            "current": round(power * 1000 / (380 * 1.732 * 0.85), 2),
            "status": "running" if running else "idle",
        })
        cur += timedelta(hours=1)
    return rows

def _mock_forecast(machine_id: str, hours_ahead: int) -> dict:
    """Mock forecast – satu titik prediksi per jam."""
    import random
    rated = next((m["rated_power_kw"] for m in _MOCK_MACHINES if m["machine_id"] == machine_id), 15)
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    preds = [
        {
            "forecast_time": (now + timedelta(hours=h)).isoformat(),
            "predicted_kwh": round(rated * random.uniform(0.5, 0.9), 2),
        }
        for h in range(1, hours_ahead + 1)
    ]
    return {"machine_id": machine_id, "hours_ahead": hours_ahead, "predictions": preds, "is_mock": True}

def _mock_waste_alerts(machine_id: str, start: Optional[datetime], end: Optional[datetime]) -> list[dict]:
    """Mock waste-alerts dengan skema yang disepakati."""
    base = start or datetime(2026, 11, 1, 10, 0)
    return [
        {
            "machine_id": machine_id,
            "timestamp": (base + timedelta(hours=i * 8)).isoformat(),
            "type": ["idle_waste", "overconsumption", "peak_hours"][i % 3],
            "severity": ["low", "medium", "high"][i % 3],
            "note": f"Contoh peringatan #{i + 1} (data mock)",
        }
        for i in range(3)
    ]

# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _get(path: str, params: dict | None = None, base_url: str | None = None) -> dict | list:
    """Lakukan GET ke BASE_URL + path; lempar RuntimeError yang informatif.
    Meneruskan status_code asli sebagai atribut RuntimeError sehingga pemanggil
    dapat membedakan 503 dari error koneksi.
    """
    url = f"{base_url or BASE_URL}{path}"
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        exc = RuntimeError(f"Tidak dapat terhubung ke backend: {url}")
        exc.status_code = None  # type: ignore[attr-defined]
        raise exc
    except requests.exceptions.Timeout:
        exc = RuntimeError(f"Request timeout setelah {TIMEOUT}s: {url}")
        exc.status_code = None  # type: ignore[attr-defined]
        raise exc
    except requests.exceptions.HTTPError as http_exc:
        code = http_exc.response.status_code
        exc = RuntimeError(f"HTTP {code} dari {url}: {http_exc.response.text[:200]}")
        exc.status_code = code  # type: ignore[attr-defined]
        raise exc
    except Exception as e:
        exc = RuntimeError(f"Error tidak dikenal saat GET {url}: {e}")
        exc.status_code = None  # type: ignore[attr-defined]
        raise exc


def _post(path: str, payload: dict) -> dict | list:
    """Lakukan POST ke BASE_URL + path dengan JSON body."""
    url = f"{BASE_URL}{path}"
    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        exc = RuntimeError(f"Tidak dapat terhubung ke backend: {url}")
        exc.status_code = None  # type: ignore[attr-defined]
        raise exc
    except requests.exceptions.Timeout:
        exc = RuntimeError(f"Request timeout setelah {TIMEOUT}s: {url}")
        exc.status_code = None  # type: ignore[attr-defined]
        raise exc
    except requests.exceptions.HTTPError as http_exc:
        code = http_exc.response.status_code
        exc = RuntimeError(f"HTTP {code} dari {url}: {http_exc.response.text[:200]}")
        exc.status_code = code  # type: ignore[attr-defined]
        raise exc
    except Exception as e:
        exc = RuntimeError(f"Error tidak dikenal saat POST {url}: {e}")
        exc.status_code = None  # type: ignore[attr-defined]
        raise exc


# ---------------------------------------------------------------------------
# Normalisasi forecast & waste
# ---------------------------------------------------------------------------

def _normalize_forecast(raw, machine_id: str, hours_ahead: int) -> dict:
    """
    Terima berbagai bentuk respons backend:
      - dict dengan kunci 'predictions'  → gunakan langsung
      - list of dict langsung             → bungkus ke 'predictions'
      - bentuk tidak dikenal              → fallback ke mock

    Kolom yang dijamin ada di setiap item 'predictions':
      forecast_time (str ISO), predicted_kwh (float)
    """
    preds = None

    if isinstance(raw, dict):
        # Bentuk utama: {"machine_id":..., "predictions": [...]}
        if "predictions" in raw and isinstance(raw["predictions"], list):
            preds = raw["predictions"]
        # Bentuk alternatif: {"alerts": [...]} atau {"forecasts": [...]}
        for key in ("forecasts", "data", "results"):
            if key in raw and isinstance(raw[key], list):
                preds = raw[key]
                break
    elif isinstance(raw, list):
        preds = raw

    if not preds:
        logger.warning("Respons forecast tidak dikenali, pakai mock.")
        return _mock_forecast(machine_id, hours_ahead)

    # Pastikan setiap item punya kolom yang disepakati
    normalized = []
    for item in preds:
        if not isinstance(item, dict):
            continue
        # Coba berbagai alias nama kolom dari backend
        ft = (item.get("forecast_time")
              or item.get("time")
              or item.get("timestamp")
              or item.get("datetime"))
        kwh = (item.get("predicted_kwh")
               or item.get("energy_kwh")
               or item.get("value")
               or item.get("kWh"))
        if ft is None or kwh is None:
            continue
        normalized.append({"forecast_time": str(ft), "predicted_kwh": float(kwh)})

    if not normalized:
        logger.warning("Tidak ada item valid di predictions, pakai mock.")
        return _mock_forecast(machine_id, hours_ahead)

    return {"machine_id": machine_id, "hours_ahead": hours_ahead, "predictions": normalized, "is_mock": False}


def _normalize_waste(raw, machine_id: str, start, end) -> dict:
    """
    Terima berbagai bentuk respons backend:
      - list of dict langsung
      - dict dengan kunci 'alerts', 'data', 'results', 'waste_alerts'

    Kolom yang dijamin ada di setiap item:
      machine_id, timestamp, type, severity, note
    """
    items = None

    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        for key in ("alerts", "waste_alerts", "data", "results"):
            if key in raw and isinstance(raw[key], list):
                items = raw[key]
                break

    if items is None:
        logger.warning("Respons waste-alerts tidak dikenali, pakai mock.")
        return {"alerts": _mock_waste_alerts(machine_id, start, end), "is_mock": True}

    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized.append({
            "machine_id": item.get("machine_id", machine_id),
            "timestamp":  str(item.get("timestamp") or item.get("time") or ""),
            "type":       item.get("type") or item.get("alert_type") or "unknown",
            "severity":   item.get("severity") or item.get("level") or "unknown",
            "note":       item.get("note") or item.get("message") or item.get("description") or "",
        })

    return {"alerts": normalized, "is_mock": False}


# ---------------------------------------------------------------------------
# Fungsi Publik
# ---------------------------------------------------------------------------

def check_api(base_url: str | None = None) -> bool:
    """
    Lakukan GET / dengan timeout pendek.
    Kembalikan True jika backend merespons dengan status 200, False jika tidak.
    Tidak pernah melempar exception — aman dipakai sebagai indikator sidebar.
    """
    target = (base_url or BASE_URL).rstrip("/")
    try:
        resp = requests.get(f"{target}/", timeout=TIMEOUT_HEALTH)
        return resp.status_code == 200
    except Exception:
        return False


@_cache
def get_machines() -> list[dict]:
    """
    GET /machines
    Kembalikan daftar mesin. Setiap item:
      machine_id (str), name (str), line (str), type (str), rated_power_kw (int)

    USE_MOCK=true  → kembalikan data mock.
    USE_MOCK=false → wajib berhasil; lempar RuntimeError jika API gagal.
    """
    if USE_MOCK:
        return _MOCK_MACHINES
    return _get("/machines")  # type: ignore[return-value]


@_cache
def get_energy(
    machine_id: str,
    start: datetime,
    end: datetime,
    limit: int = 10_000,
) -> list[dict]:
    """
    GET /energy
    machine_id wajib; start & end selalu dikirim; limit max 10 000.

    Setiap item: machine_id, timestamp, power_kw, energy_kwh,
                 voltage, current, status

    USE_MOCK=true  → kembalikan data mock.
    USE_MOCK=false → wajib berhasil; lempar RuntimeError jika API gagal.
    """
    limit = min(limit, 10_000)
    if USE_MOCK:
        return _mock_energy(machine_id, start, end, limit)
    params = {
        "machine_id": machine_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "limit": limit,
    }
    return _get("/energy", params=params)  # type: ignore[return-value]


@_cache
def get_summary() -> dict:
    """
    GET /summary
    Kembalikan: total_kwh (float), estimated_cost_rp (int),
                per_line (dict[str, float]), alert_count (int)

    USE_MOCK=true  → kembalikan data mock.
    USE_MOCK=false → wajib berhasil; lempar RuntimeError jika API gagal.
                     Tidak pernah diam-diam mengembalikan data palsu.
    """
    if USE_MOCK:
        return {
            "total_kwh": 9720.0,
            "estimated_cost_rp": 14_580_000,
            "per_line": {"Line A": 5832.0, "Line B": 3888.0},
            "alert_count": 0,
        }
    return _get("/summary")  # type: ignore[return-value]


@_cache
def get_forecast(machine_id: str, hours: int = 24) -> dict:
    """
    GET /forecast/{machine_id}?hours_ahead={hours}
    Kembalikan dict berisi:
      machine_id, hours_ahead, is_mock (bool),
      predictions: list[{forecast_time: str, predicted_kwh: float}]

    Fallback ke mock HANYA jika backend mengembalikan HTTP 503.
    Error lain (koneksi putus, 4xx, 5xx lain) → tetap lempar RuntimeError.
    """
    if USE_MOCK:
        return _mock_forecast(machine_id, hours)
    try:
        raw = _get(f"/forecast/{machine_id}", params={"hours_ahead": hours})
        return _normalize_forecast(raw, machine_id, hours)
    except RuntimeError as exc:
        status = getattr(exc, "status_code", None)
        if status == 503:
            logger.warning("get_forecast 503, pakai mock. %s", exc)
            result = _mock_forecast(machine_id, hours)
            result["_error"] = str(exc)
            return result
        raise  # error selain 503 tetap naik


@_cache
def get_waste_alerts(
    machine_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> dict:
    """
    GET /waste-alerts?machine_id=...&start=...&end=...
    Kembalikan dict berisi:
      is_mock (bool),
      alerts: list[{machine_id, timestamp, type, severity, note}]

    Fallback ke mock HANYA jika backend mengembalikan HTTP 503.
    Error lain (koneksi putus, 4xx, 5xx lain) → tetap lempar RuntimeError.
    """
    if USE_MOCK:
        return {"alerts": _mock_waste_alerts(machine_id, start, end), "is_mock": True}
    params: dict = {"machine_id": machine_id}
    if start:
        params["start"] = start.isoformat()
    if end:
        params["end"] = end.isoformat()
    try:
        raw = _get("/waste-alerts", params=params)
        return _normalize_waste(raw, machine_id, start, end)
    except RuntimeError as exc:
        status = getattr(exc, "status_code", None)
        if status == 503:
            logger.warning("get_waste_alerts 503, pakai mock. %s", exc)
            return {
                "alerts": _mock_waste_alerts(machine_id, start, end),
                "is_mock": True,
                "_error": str(exc),
            }
        raise  # error selain 503 tetap naik


# ---------------------------------------------------------------------------
# Helper: Rentang Tanggal Data
# ---------------------------------------------------------------------------

def get_data_range(machine_id: str = "M01") -> tuple[datetime, datetime]:
    """
    Ambil tanggal awal dan akhir data yang tersedia dengan mengambil
    record dari /energy.

    Fallback ke rentang seed default (2026-11-01 – 2026-11-03) HANYA jika
    USE_MOCK=true. Jika USE_MOCK=false dan backend tidak terjangkau, exception
    dari get_energy akan naik ke pemanggil.
    """
    SEED_START = datetime(2026, 11, 1)
    SEED_END   = datetime(2026, 11, 3, 23, 0)

    if USE_MOCK:
        return SEED_START, SEED_END

    rows = get_energy(machine_id, datetime(2000, 1, 1), datetime(2100, 1, 1), limit=10_000)
    if not rows:
        return SEED_START, SEED_END
    timestamps = [datetime.fromisoformat(r["timestamp"]) for r in rows if "timestamp" in r]
    if not timestamps:
        return SEED_START, SEED_END
    return min(timestamps), max(timestamps)


# ---------------------------------------------------------------------------
# Helper Agregasi Pandas
# ---------------------------------------------------------------------------

def to_dataframe(energy_rows: list[dict]) -> pd.DataFrame:
    """
    Konversi list energy_readings ke DataFrame dengan kolom:
      machine_id, timestamp (datetime), power_kw, energy_kwh,
      voltage, current, status
    """
    if not energy_rows:
        return pd.DataFrame(columns=[
            "machine_id", "timestamp", "power_kw", "energy_kwh",
            "voltage", "current", "status"
        ])
    df = pd.DataFrame(energy_rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def aggregate_hourly(energy_rows: list[dict]) -> pd.DataFrame:
    """
    Agregasi per jam:
      - energy_kwh : SUM   (total energi dalam jam itu)
      - power_kw   : MEAN  (daya rata-rata dalam jam itu)

    Kolom hasil: timestamp (jam), machine_id, energy_kwh, power_kw
    """
    df = to_dataframe(energy_rows)
    if df.empty:
        return df
    df["hour"] = df["timestamp"].dt.floor("h")
    agg = (
        df.groupby(["hour", "machine_id"], sort=True)
        .agg(energy_kwh=("energy_kwh", "sum"), power_kw=("power_kw", "mean"))
        .reset_index()
        .rename(columns={"hour": "timestamp"})
    )
    agg["energy_kwh"] = agg["energy_kwh"].round(3)
    agg["power_kw"]   = agg["power_kw"].round(3)
    return agg


def aggregate_daily(energy_rows: list[dict]) -> pd.DataFrame:
    """
    Agregasi per hari:
      - energy_kwh : SUM   (total energi dalam satu hari)
      - power_kw   : MEAN  (daya rata-rata dalam satu hari)

    Kolom hasil: date (date), machine_id, energy_kwh, power_kw
    """
    df = to_dataframe(energy_rows)
    if df.empty:
        return df
    df["date"] = df["timestamp"].dt.date
    agg = (
        df.groupby(["date", "machine_id"], sort=True)
        .agg(energy_kwh=("energy_kwh", "sum"), power_kw=("power_kw", "mean"))
        .reset_index()
    )
    agg["energy_kwh"] = agg["energy_kwh"].round(3)
    agg["power_kw"]   = agg["power_kw"].round(3)
    return agg
