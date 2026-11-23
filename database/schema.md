# Skema Database `smart_energy` (MongoDB lokal)

Pemilik: Lae (branch `feature/db`). Dokumen ini adalah **kontrak data**: nama koleksi/field tidak boleh diubah tanpa persetujuan Wowok.

- URI default: `mongodb://localhost:27017` (env `MONGO_URI`), database `smart_energy`.
- Data disimulasi (tanpa hardware). Dibangkitkan oleh `generate_data.py` (`--seed 42` = data identik di semua laptop).

## 1. Konvensi waktu (WAJIB dibaca)

| Hal | Aturan |
|---|---|
| `timestamp`, `forecast_time` | Tipe BSON `Date`, disimpan sebagai **UTC**. pymongo mengembalikan `datetime` tanpa tzinfo (artinya UTC). |
| Zona bisnis | **WIB = UTC+7**. Pengelompokan per hari/jam di agregasi memakai WIB. |
| `production_logs.date` | String `"YYYY-MM-DD"` = **tanggal WIB saat shift dimulai**. |
| Parameter `start`/`end` | ISO-8601 (`2026-01-01T00:00:00Z`); naive dianggap UTC. Rentang `[start, end)` (end eksklusif). |

### Definisi shift (WIB)

| shift | Jam WIB | Jam UTC |
|---|---|---|
| 1 | 07:00 - 15:00 | 00:00 - 08:00 |
| 2 | 15:00 - 23:00 | 08:00 - 16:00 |
| 3 | 23:00 - 07:00 (hari berikutnya) | 16:00 - 24:00 |

Shift 3 yang dimulai 23:00 WIB tanggal D tetap bertanggal **D** (bukan D+1).
Data dimulai **07:00 WIB** pada `--start-date` dan mencakup N hari penuh, jadi semua blok shift lengkap.

### Definisi status

| status | Arti | Daya (simulasi) |
|---|---|---|
| `running` | mesin berproduksi | sekitar 58-96% `rated_power_kw` |
| `idle` | hidup tanpa beban | sekitar 5-15% `rated_power_kw` |
| `off` | mati | mendekati 0 (< 0,4% rated) |

## 2. Koleksi (kontrak)

### 2.1 `machines` (12 dokumen)

| Field | Tipe | Satuan | Keterangan |
|---|---|---|---|
| `machine_id` | string | - | `M01`-`M12`, unik |
| `name` | string | - | nama mesin |
| `line` | string | - | `Line A` / `Line B` / `Line C` |
| `type` | string | - | CNC, conveyor, press, oven, chiller, pump, compressor, packaging |
| `rated_power_kw` | double | kW | daya nominal (5 - 90) |

```json
{"machine_id": "M01", "name": "CNC Milling 1", "line": "Line A", "type": "CNC", "rated_power_kw": 45.0}
```

### 2.2 `energy_readings` (≈ 622.080 dokumen)

| Field | Tipe | Satuan | Keterangan |
|---|---|---|---|
| `machine_id` | string | - | FK ke `machines.machine_id` |
| `timestamp` | Date (UTC) | - | awal interval 5 menit |
| `power_kw` | double | kW | daya rata-rata interval |
| `energy_kwh` | double | kWh | `power_kw x 5/60` (dibulatkan 5 desimal) |
| `voltage` | double | V | sekitar 380-400 V |
| `current` | double | A | `P*1000 / (sqrt(3) * V * 0,85)` (pf = 0,85) |
| `status` | string | - | `running` / `idle` / `off` |

```json
{"machine_id": "M01", "timestamp": {"$date": "2026-01-05T02:15:00Z"}, "power_kw": 38.214,
 "energy_kwh": 3.1845, "voltage": 392.4, "current": 66.14, "status": "running"}
```

### 2.3 `production_logs` (6.480 dokumen = 12 mesin x 180 hari x 3 shift)

| Field | Tipe | Satuan | Keterangan |
|---|---|---|---|
| `machine_id` | string | - | FK |
| `shift` | int32 | - | 1, 2, atau 3 |
| `date` | string | - | tanggal WIB saat shift dimulai |
| `units_produced` | int | unit | proporsional dengan lama `running` di shift itu (0 bila tidak produksi) |

```json
{"machine_id": "M01", "shift": 1, "date": "2026-01-05", "units_produced": 91}
```
Untuk mesin utilitas (chiller, pompa, kompresor) `units_produced` adalah unit layanan setara, hanya agar kolom terisi konsisten.

### 2.4 `forecasts` (diisi Didi/Wowok; saya hanya menyiapkan koleksi + index)

| Field | Tipe | Satuan |
|---|---|---|
| `machine_id` | string | - |
| `forecast_time` | Date (UTC) | waktu yang diprediksi |
| `predicted_kwh` | double | kWh |

```json
{"machine_id": "M01", "forecast_time": {"$date": "2026-07-01T00:05:00Z"}, "predicted_kwh": 3.12}
```

### 2.5 `waste_alerts` (diisi Jovan/Wowok; saya hanya menyiapkan koleksi + index)

| Field | Tipe | Keterangan |
|---|---|---|
| `machine_id` | string | FK |
| `timestamp` | Date (UTC) | waktu kejadian |
| `type` | string | disarankan sama dengan `waste_type` di bawah |
| `severity` | string | ditentukan Jovan (mis. low/medium/high) |
| `note` | string | catatan bebas |

```json
{"machine_id": "M05", "timestamp": {"$date": "2026-03-02T19:10:00Z"}, "type": "idle_high_power",
 "severity": "high", "note": "Idle tetapi daya 62% rated"}
```

## 3. Koleksi di luar kontrak API: `waste_labels`

Ground-truth pemborosan hasil simulasi. **Hanya baris positif** (≈ 25 ribu dokumen ≈ 4% dari energy_readings).

| Field | Tipe | Keterangan |
|---|---|---|
| `machine_id` | string | kunci join |
| `timestamp` | Date (UTC) | kunci join |
| `is_waste` | bool | selalu `true` |
| `waste_type` | string | `idle_high_power` / `spike` / `running_no_production` |

```json
{"machine_id": "M04", "timestamp": {"$date": "2026-02-10T03:40:00Z"}, "is_waste": true, "waste_type": "spike"}
```
**Kunci join: `(machine_id, timestamp)`** ke `energy_readings`.

| waste_type | Arti | Cara disimulasikan |
|---|---|---|
| `idle_high_power` | status `idle` tetapi daya 40-80% rated | 30-180 menit |
| `spike` | lonjakan daya mendadak (x1,25-1,6) saat `running` | 5-15 menit |
| `running_no_production` | mesin `running` tetapi `units_produced` 0/sangat rendah pada shift itu | seluruh baris `running` di shift tsb |

Catatan: ada juga fluktuasi normal (umpan) yang **tidak** berlabel agar deteksi tidak terlalu mudah.

## 4. Relasi

```
machines.machine_id 1 ──< energy_readings.machine_id
machines.machine_id 1 ──< production_logs.machine_id
machines.machine_id 1 ──< forecasts / waste_alerts / waste_labels .machine_id
energy_readings (machine_id, timestamp) 1 ── 0..1 waste_labels (machine_id, timestamp)
production_logs (machine_id, date, shift) <-> energy_readings (shift dihitung dari timestamp WIB)
```

## 5. Index

| Koleksi | Index |
|---|---|
| `machines` | `{machine_id: 1}` unik |
| `energy_readings` | `{machine_id: 1, timestamp: 1}` |
| `production_logs` | `{machine_id: 1, date: 1, shift: 1}` |
| `waste_alerts` | `{machine_id: 1, timestamp: 1}` |
| `forecasts` | `{machine_id: 1, forecast_time: 1}` |
| `waste_labels` | `{machine_id: 1, timestamp: 1}` |

Dibuat oleh `create_indexes()` di `db.py` (otomatis di akhir `generate_data.py`).

## 6. Kolom tambahan di CSV sample (bukan di MongoDB energy_readings)

`energy_readings_sample.csv` punya 2 kolom ekstra: `is_waste` (0/1) dan `waste_type` (`none` bila 0).

## 7. Asumsi simulasi

- 12 mesin, 3 line, interval **5 menit** (disetujui head project; jobdesk awal 1 menit), 180 hari (6 bulan x 30 hari) mulai 2026-01-01 07:00 WIB.
- Perkiraan volume: `energy_readings` 622.080 (12 x 51.840), `production_logs` 6.480, `waste_labels` ≈ 25 ribu.
- Mesin produksi aktif terutama shift 1-2 hari kerja; Sabtu sebagian; Minggu/libur nasional (perkiraan) hampir mati. Utilitas (chiller, pompa, kompresor) hampir selalu menyala dengan beban lebih rendah malam/akhir pekan.
- Noise acak + drift musiman (±3% produksi, ±8% utilitas). Tegangan N(392, 2,5) V di-clip 380-400 V. Power factor tetap 0,85.
- Tarif listrik untuk `/summary` adalah parameter (default asumsi Rp 1.500/kWh).
- `--seed` sama + versi numpy sama = data identik. Alternatif: `mongodump`/`mongorestore` (lihat `README_DB.md`).
