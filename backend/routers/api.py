from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Query
from database.db import get_db

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