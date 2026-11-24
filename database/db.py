import os
import time
from collections import namedtuple
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

load_dotenv()

DEFAULT_URI = "mongodb://localhost:27017"
DEFAULT_DB_NAME = "smart_energy"
WIB_TZ = "+07:00"

COLLECTIONS = (
    "machines",
    "energy_readings",
    "production_logs",
    "forecasts",
    "waste_alerts",
    "waste_labels",  # di luar kontrak API (ground truth pemborosan)
)

# koleksi -> daftar (keys, opsi)
INDEX_SPECS: Dict[str, List[Tuple[List[Tuple[str, int]], Dict[str, Any]]]] = {
    "machines": [([("machine_id", 1)], {"unique": True})],
    "energy_readings": [([("machine_id", 1), ("timestamp", 1)], {})],
    "production_logs": [([("machine_id", 1), ("date", 1), ("shift", 1)], {})],
    "waste_alerts": [([("machine_id", 1), ("timestamp", 1)], {})],
    "forecasts": [([("machine_id", 1), ("forecast_time", 1)], {})],
    "waste_labels": [([("machine_id", 1), ("timestamp", 1)], {})],
}

TimeLike = Union[str, datetime, None]
InsertResult = namedtuple("InsertResult", ["inserted", "seconds"])

_clients: Dict[str, MongoClient] = {}


# --------------------------------------------------------------------------
# Koneksi & helper
# --------------------------------------------------------------------------
def get_client(uri: Optional[str] = None) -> MongoClient:
    """MongoClient (di-cache per URI). URI default: env MONGO_URI atau localhost."""
    uri = uri or os.getenv("MONGO_URI", DEFAULT_URI)
    if uri not in _clients:
        _clients[uri] = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return _clients[uri]


def get_db(name: Optional[str] = None, uri: Optional[str] = None) -> Database:
    """Database 'smart_energy' (mendukung env DB_NAME dari main maupun MONGO_DB)."""
    db_name = name or os.getenv("DB_NAME") or os.getenv("MONGO_DB", DEFAULT_DB_NAME)
    return get_client(uri)[db_name]


def ping(uri: Optional[str] = None) -> bool:
    """Cek koneksi. Melempar ServerSelectionTimeoutError bila mongod belum jalan."""
    get_client(uri).admin.command("ping")
    return True


def get_collection(name: str, db: Optional[Database] = None) -> Collection:
    """Ambil koleksi dari database default (atau db yang diberikan)."""
    return (db if db is not None else get_db())[name]


def bulk_insert(collection: Union[str, Collection], docs, batch_size: int = 10_000,
                progress=None) -> InsertResult:
    """
    Insert dokumen dengan insert_many per batch (default 10.000).

    docs     : list/iterator of dict
    progress : objek tqdm opsional (di-update per batch)
    return   : InsertResult(inserted, seconds) -> seconds hanya waktu insert_many.
    """
    if isinstance(collection, str):
        collection = get_collection(collection)
    state = {"inserted": 0, "seconds": 0.0}
    batch: List[dict] = []

    def _flush():
        if not batch:
            return
        t0 = time.perf_counter()
        collection.insert_many(batch, ordered=False)
        state["seconds"] += time.perf_counter() - t0
        state["inserted"] += len(batch)
        if progress is not None:
            progress.update(len(batch))
        batch.clear()

    for d in docs:
        batch.append(d)
        if len(batch) >= batch_size:
            _flush()
    _flush()
    return InsertResult(state["inserted"], state["seconds"])


def create_indexes(db: Optional[Database] = None) -> Dict[str, List[str]]:
    """Buat semua index (idempotent). Return {koleksi: [nama index]}."""
    db = db if db is not None else get_db()
    created: Dict[str, List[str]] = {}
    for coll, specs in INDEX_SPECS.items():
        created[coll] = [db[coll].create_index(keys, **opts) for keys, opts in specs]
    return created


def drop_indexes(db: Optional[Database] = None) -> None:
    """Hapus semua index non-_id (dipakai benchmark 'sebelum index')."""
    db = db if db is not None else get_db()
    for coll in INDEX_SPECS:
        if coll in db.list_collection_names():
            db[coll].drop_indexes()


def to_utc(value: TimeLike) -> Optional[datetime]:
    """str ISO / datetime -> datetime UTC naive. None tetap None."""
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _time_filter(start: TimeLike, end: TimeLike, field: str = "timestamp") -> Dict[str, Any]:
    cond: Dict[str, Any] = {}
    if start is not None:
        cond["$gte"] = to_utc(start)
    if end is not None:
        cond["$lt"] = to_utc(end)
    return {field: cond} if cond else {}


def _match_stage(flt: Dict[str, Any]) -> List[dict]:
    return [{"$match": flt}] if flt else []


def _run(db: Optional[Database], coll: str, pipeline: List[dict]) -> List[dict]:
    db = db if db is not None else get_db()
    return list(db[coll].aggregate(pipeline, allowDiskUse=True))


# --------------------------------------------------------------------------
# Query sederhana (untuk endpoint)
# --------------------------------------------------------------------------
def list_machines(db: Optional[Database] = None) -> List[dict]:
    """GET /machines -> [{machine_id, name, line, type, rated_power_kw}] urut machine_id."""
    db = db if db is not None else get_db()
    return list(db["machines"].find({}, {"_id": 0}).sort("machine_id", 1))


def get_energy(machine_id: str, start: TimeLike = None, end: TimeLike = None,
               limit: int = 10_000, db: Optional[Database] = None) -> List[dict]:
    """
    GET /energy?machine_id=&start=&end=
    Bacaan energi satu mesin, urut timestamp naik, rentang [start, end).
    limit default 10.000 (1 bulan data 5-menit = 8.640 baris).
    """
    db = db if db is not None else get_db()
    flt = {"machine_id": machine_id, **_time_filter(start, end)}
    cur = db["energy_readings"].find(flt, {"_id": 0}).sort("timestamp", 1)
    if limit:
        cur = cur.limit(int(limit))
    return list(cur)


# --------------------------------------------------------------------------
# Aggregation pipeline (builder dipisah agar bisa di-explain oleh benchmark.py)
# Semua builder mengembalikan (nama_koleksi, pipeline)
# --------------------------------------------------------------------------
def pipeline_daily_kwh_per_machine(start: TimeLike = None, end: TimeLike = None,
                                   machine_id: Optional[str] = None):
    flt = _time_filter(start, end)
    if machine_id:
        flt["machine_id"] = machine_id
    pipeline = _match_stage(flt) + [
        {"$group": {
            "_id": {"machine_id": "$machine_id",
                    "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp",
                                               "timezone": WIB_TZ}}},
            "total_kwh": {"$sum": "$energy_kwh"},
            "readings": {"$sum": 1}}},
        {"$sort": {"_id.machine_id": 1, "_id.date": 1}},
        {"$project": {"_id": 0, "machine_id": "$_id.machine_id", "date": "$_id.date",
                      "total_kwh": {"$round": ["$total_kwh", 3]}, "readings": 1}},
    ]
    return "energy_readings", pipeline


def daily_kwh_per_machine(start: TimeLike = None, end: TimeLike = None,
                          machine_id: Optional[str] = None,
                          db: Optional[Database] = None) -> List[dict]:
    """(1) Total kWh per mesin per hari (hari kalender WIB)."""
    return _run(db, *pipeline_daily_kwh_per_machine(start, end, machine_id))


def pipeline_avg_kwh_per_hour(start: TimeLike = None, end: TimeLike = None,
                              machine_id: Optional[str] = None, per_machine: bool = True):
    flt = _time_filter(start, end)
    if machine_id:
        flt["machine_id"] = machine_id
    key1: Dict[str, Any] = {
        "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp", "timezone": WIB_TZ}},
        "hour": {"$hour": {"date": "$timestamp", "timezone": WIB_TZ}},
    }
    key2: Dict[str, Any] = {"hour": "$_id.hour"}
    proj: Dict[str, Any] = {"_id": 0, "hour": "$_id.hour",
                            "avg_kwh": {"$round": ["$avg_kwh", 3]}, "days": 1}
    sort: Dict[str, int] = {"hour": 1}
    if per_machine:
        key1["machine_id"] = "$machine_id"
        key2["machine_id"] = "$_id.machine_id"
        proj["machine_id"] = "$_id.machine_id"
        sort = {"machine_id": 1, "hour": 1}
    pipeline = _match_stage(flt) + [
        {"$group": {"_id": key1, "kwh": {"$sum": "$energy_kwh"}}},
        {"$group": {"_id": key2, "avg_kwh": {"$avg": "$kwh"}, "days": {"$sum": 1}}},
        {"$project": proj},
        {"$sort": sort},
    ]
    return "energy_readings", pipeline


def avg_kwh_per_hour(start: TimeLike = None, end: TimeLike = None,
                     machine_id: Optional[str] = None, per_machine: bool = True,
                     db: Optional[Database] = None) -> List[dict]:
    """(2) Rata-rata kWh per jam-dalam-sehari (jam WIB 0-23)."""
    return _run(db, *pipeline_avg_kwh_per_hour(start, end, machine_id, per_machine))


_LOOKUP_MACHINE = [
    {"$lookup": {"from": "machines", "localField": "_id", "foreignField": "machine_id", "as": "m"}},
    {"$unwind": {"path": "$m", "preserveNullAndEmptyArrays": True}},
]


def pipeline_top_machines_by_kwh(n: int = 5, start: TimeLike = None, end: TimeLike = None):
    pipeline = _match_stage(_time_filter(start, end)) + [
        {"$group": {"_id": "$machine_id", "total_kwh": {"$sum": "$energy_kwh"}}},
        {"$sort": {"total_kwh": -1}},
        {"$limit": int(n)},
    ] + _LOOKUP_MACHINE + [
        {"$project": {"_id": 0, "machine_id": "$_id", "name": "$m.name", "line": "$m.line",
                      "type": "$m.type", "total_kwh": {"$round": ["$total_kwh", 3]}}},
    ]
    return "energy_readings", pipeline


def top_machines_by_kwh(n: int = 5, start: TimeLike = None, end: TimeLike = None,
                        db: Optional[Database] = None) -> List[dict]:
    """(3a) Top-N mesin paling boros berdasarkan TOTAL kWh."""
    rows = _run(db, *pipeline_top_machines_by_kwh(n, start, end))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def pipeline_top_machines_by_waste_energy(n: int = 5, start: TimeLike = None, end: TimeLike = None):
    flt = {"is_waste": True, **_time_filter(start, end)}
    pipeline = [
        {"$match": flt},
        {"$lookup": {
            "from": "energy_readings",
            "let": {"m": "$machine_id", "t": "$timestamp"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [{"$eq": ["$machine_id", "$$m"]},
                                               {"$eq": ["$timestamp", "$$t"]}]}}},
                {"$project": {"_id": 0, "energy_kwh": 1}},
            ],
            "as": "e"}},
        {"$unwind": "$e"},
        {"$group": {"_id": "$machine_id", "waste_kwh": {"$sum": "$e.energy_kwh"},
                    "waste_rows": {"$sum": 1}}},
        {"$sort": {"waste_kwh": -1}},
        {"$limit": int(n)},
    ] + _LOOKUP_MACHINE + [
        {"$project": {"_id": 0, "machine_id": "$_id", "name": "$m.name", "line": "$m.line",
                      "waste_kwh": {"$round": ["$waste_kwh", 3]}, "waste_rows": 1}},
    ]
    return "waste_labels", pipeline


def top_machines_by_waste_energy(n: int = 5, start: TimeLike = None, end: TimeLike = None,
                                 db: Optional[Database] = None) -> List[dict]:
    """(3b) Top-N mesin berdasarkan ENERGI PEMBOROSAN."""
    rows = _run(db, *pipeline_top_machines_by_waste_energy(n, start, end))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def pipeline_kwh_per_line(start: TimeLike = None, end: TimeLike = None):
    pipeline = _match_stage(_time_filter(start, end)) + [
        {"$group": {"_id": "$machine_id", "kwh": {"$sum": "$energy_kwh"}}},
    ] + _LOOKUP_MACHINE + [
        {"$group": {"_id": {"$ifNull": ["$m.line", "UNKNOWN"]},
                    "total_kwh": {"$sum": "$kwh"}, "machines": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    return "energy_readings", pipeline


def summary(tariff_per_kwh: float = 1500.0, start: TimeLike = None, end: TimeLike = None,
            db: Optional[Database] = None) -> dict:
    """(4) Ringkasan untuk GET /summary."""
    rows = _run(db, *pipeline_kwh_per_line(start, end))
    per_line = [{"line": r["_id"], "machines": r["machines"],
                 "total_kwh": round(r["total_kwh"], 3),
                 "cost": round(r["total_kwh"] * tariff_per_kwh, 2)} for r in rows]
    total_kwh = round(sum(r["total_kwh"] for r in per_line), 3)
    s, e = to_utc(start), to_utc(end)
    return {
        "period": {"start": s.isoformat() if s else None, "end": e.isoformat() if e else None},
        "tariff_per_kwh": tariff_per_kwh,
        "total_kwh": total_kwh,
        "total_cost": round(total_kwh * tariff_per_kwh, 2),
        "per_line": per_line,
    }


def pipeline_kwh_per_shift(start: TimeLike = None, end: TimeLike = None,
                           machine_id: Optional[str] = None):
    flt = _time_filter(start, end)
    if machine_id:
        flt["machine_id"] = machine_id
    pipeline = _match_stage(flt) + [
        # Shift dimulai 07:00 WIB = 00:00 UTC, jadi tanggal shift = tanggal UTC
        # dan nomor shift = jam UTC // 8 + 1.
        {"$group": {
            "_id": {"machine_id": "$machine_id",
                    "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                    "shift": {"$add": [{"$floor": {"$divide": [{"$hour": "$timestamp"}, 8]}}, 1]}},
            "total_kwh": {"$sum": "$energy_kwh"}}},
        {"$lookup": {
            "from": "production_logs",
            "let": {"m": "$_id.machine_id", "d": "$_id.date", "s": "$_id.shift"},
            "pipeline": [{"$match": {"$expr": {"$and": [
                {"$eq": ["$machine_id", "$$m"]}, {"$eq": ["$date", "$$d"]},
                {"$eq": ["$shift", "$$s"]}]}}},
                {"$project": {"_id": 0, "units_produced": 1}}],
            "as": "p"}},
        {"$project": {"_id": 0, "machine_id": "$_id.machine_id", "date": "$_id.date",
                      "shift": {"$toInt": "$_id.shift"},
                      "total_kwh": {"$round": ["$total_kwh", 3]},
                      "units_produced": {"$ifNull": [{"$first": "$p.units_produced"}, 0]}}},
        {"$sort": {"date": 1, "machine_id": 1, "shift": 1}},
    ]
    return "energy_readings", pipeline


def kwh_per_shift(start: TimeLike = None, end: TimeLike = None,
                  machine_id: Optional[str] = None, db: Optional[Database] = None) -> List[dict]:
    """
    Total kWh per mesin per tanggal-shift (shift WIB: 1=07-15, 2=15-23, 3=23-07),
    plus units_produced dari production_logs.
    Contoh: {"machine_id":"M01","date":"2026-01-05","shift":1,"total_kwh":210.4,"units_produced":91}
    Untuk total per shift seluruh pabrik, jumlahkan per (date, shift) di Python.
    """
    return _run(db, *pipeline_kwh_per_shift(start, end, machine_id))


if __name__ == "__main__":
    ping()
    d = get_db()
    print("Koneksi OK ->", d.name)
    for c in COLLECTIONS:
        print(f"  {c:16s} {d[c].estimated_document_count():>10,d}")