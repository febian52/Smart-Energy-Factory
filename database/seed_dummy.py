import random
from datetime import datetime, timedelta
from database.db import get_db

db = get_db()
for col in ["machines", "energy_readings", "waste_alerts"]:
    db[col].delete_many({})

machines = [
    {"machine_id": "M01", "name": "CNC Milling 1", "line": "Line A", "type": "CNC", "rated_power_kw": 15},
    {"machine_id": "M02", "name": "Kompresor 1", "line": "Line A", "type": "Compressor", "rated_power_kw": 30},
    {"machine_id": "M03", "name": "Oven 1", "line": "Line B", "type": "Oven", "rated_power_kw": 45},
]
db.machines.insert_many(machines)

start = datetime(2026, 11, 1)
rows = []
for m in machines:
    for h in range(72):
        ts = start + timedelta(hours=h)
        running = 7 <= ts.hour < 22
        ratio = random.uniform(0.7, 0.95) if running else random.uniform(0.05, 0.15)
        power = round(m["rated_power_kw"] * ratio, 2)
        rows.append({
            "machine_id": m["machine_id"],
            "timestamp": ts,
            "power_kw": power,
            "energy_kwh": power,
            "voltage": 380,
            "current": round(power * 1000 / (380 * 1.732 * 0.85), 2),
            "status": "running" if running else "idle",
        })
db.energy_readings.insert_many(rows)
print(f"Seeded {len(machines)} machines, {len(rows)} readings")