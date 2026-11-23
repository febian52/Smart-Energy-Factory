from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Query
from database.db import get_db
from fastapi import HTTPException
from pydantic import BaseModel

router = APIRouter()
TARIF_PER_KWH = 1500  # Rp per kWh (asumsi), sebutkan di artikel


@router.get("/machines")
def list_machines():
    db = get_db()
    return list(db.machines.find({}, {"_id": 0}))


@router.get("/energy")
def get_energy(
    machine_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(1000, le=10000),
):
    db = get_db()
    q = {"machine_id": machine_id}
    if start or end:
        q["timestamp"] = {}
        if start:
            q["timestamp"]["$gte"] = start
        if end:
            q["timestamp"]["$lte"] = end
    cursor = db.energy_readings.find(q, {"_id": 0}).sort("timestamp", 1).limit(limit)
    return list(cursor)


@router.get("/summary")
def summary():
    db = get_db()
    rows = list(db.energy_readings.aggregate([
        {"$group": {"_id": "$machine_id", "total_kwh": {"$sum": "$energy_kwh"}}}
    ]))
    line_of = {
        m["machine_id"]: m["line"]
        for m in db.machines.find({}, {"_id": 0, "machine_id": 1, "line": 1})
    }
    per_line = {}
    for r in rows:
        line = line_of.get(r["_id"], "unknown")
        per_line[line] = per_line.get(line, 0) + r["total_kwh"]

    total_kwh = sum(per_line.values())
    return {
        "total_kwh": round(total_kwh, 2),
        "estimated_cost_rp": round(total_kwh * TARIF_PER_KWH),
        "per_line": {k: round(v, 2) for k, v in per_line.items()},
        "alert_count": db.waste_alerts.count_documents({}),
    }

try:
    from ml.forecast.predict import forecast
except ImportError:
    forecast = None

try:
    from ml.anomaly.detect import detect_waste
except ImportError:
    detect_waste = None


class ForecastRequest(BaseModel):
    machine_id: str
    hours_ahead: int = 24


def _run_forecast(machine_id: str, hours_ahead: int):
    if forecast is None:
        raise HTTPException(503, "Model forecast belum tersedia")
    return {
        "machine_id": machine_id,
        "hours_ahead": hours_ahead,
        "predictions": forecast(machine_id, hours_ahead),
    }


@router.post("/forecast")
def post_forecast(req: ForecastRequest):
    return _run_forecast(req.machine_id, req.hours_ahead)


@router.get("/forecast/{machine_id}")
def get_forecast(machine_id: str, hours_ahead: int = 24):
    return _run_forecast(machine_id, hours_ahead)


@router.get("/waste-alerts")
def waste_alerts(
    machine_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
):
    if detect_waste is None:
        raise HTTPException(503, "Model deteksi pemborosan belum tersedia")
    return detect_waste(machine_id, start, end)