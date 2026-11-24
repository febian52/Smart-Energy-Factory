# Smart Energy Factory

**Smart Factory Energy Management: Forecasting Konsumsi Energi & Deteksi Pemborosan Listrik pada Mesin Produksi**

Proyek praktikum Big Data. Sistem ini memantau konsumsi listrik mesin-mesin produksi, memprediksi konsumsi energi ke depan (*forecasting*), dan mendeteksi pemborosan listrik (*anomaly detection*). Data bersifat simulasi (tanpa hardware).

## Fitur

- Dashboard konsumsi energi per mesin, lini, dan shift
- Forecast konsumsi energi 24 jam / 7 hari ke depan (Machine Learning)
- Deteksi pemborosan listrik, misalnya mesin idle tetapi daya tinggi (Machine Learning)
- Estimasi biaya listrik dan rekomendasi penghematan

## Teknologi

| Komponen | Teknologi |
|---|---|
| Backend | Python, FastAPI, Uvicorn |
| Database | MongoDB (PyMongo) |
| Machine Learning | scikit-learn, XGBoost, pandas, joblib |
| Front end | Streamlit |

## Struktur Folder

```
Smart-Energy-Factory/
├── backend/            # FastAPI (API & integrasi modul)
│   ├── main.py
│   └── routers/
│       └── api.py
├── database/           # Koneksi MongoDB & data
│   ├── db.py
│   ├── seed_dummy.py
│   ├── generate_data.py
│   └── schema.md
├── ml/
│   ├── forecast/       # Model forecasting konsumsi energi
│   ├── anomaly/        # Model deteksi pemborosan
│   └── models/         # File model (.pkl)
├── frontend/           # Dashboard Streamlit
│   └── app.py
├── docs/               # Artikel, slide, dokumentasi
├── requirements.txt
├── .env.example
└── README.md
```

## Prasyarat

- Python 3.10 atau lebih baru
- Git
- MongoDB Community Server (lokal) atau MongoDB Atlas
- (Opsional) MongoDB Compass untuk melihat isi database

## Instalasi

1. Clone repo:

   ```bash
   git clone https://github.com/febian52/Smart-Energy-Factory.git
   cd Smart-Energy-Factory
   ```

2. Buat dan aktifkan virtual environment:

   ```bash
   python -m venv venv

   # Windows (Git Bash)
   source venv/Scripts/activate
   # Windows (CMD / PowerShell)
   venv\Scripts\activate
   # Mac / Linux
   source venv/bin/activate
   ```

3. Install dependensi:

   ```bash
   pip install -r requirements.txt
   ```

4. Salin file environment, lalu sesuaikan isinya:

   ```bash
   cp .env.example .env
   ```

   Isi `.env`:

   ```
   MONGO_URI=mongodb://localhost:27017
   DB_NAME=smart_energy
   ```

   Jika MongoDB memakai autentikasi, gunakan format:
   `mongodb://USERNAME:PASSWORD@localhost:27017/?authSource=admin`

   > File `.env` tidak boleh di-commit ke GitHub.

## Mengisi Data

Pastikan MongoDB sudah berjalan, lalu jalankan **salah satu**:

```bash
# Data lengkap (simulasi skala besar)
python -m database.generate_data

# Atau data dummy kecil untuk pengujian cepat (3 mesin, 3 hari)
python -m database.seed_dummy
```

## Menjalankan Aplikasi

Jalankan semua perintah dari **root repo** (bukan dari dalam folder `backend`).

**Backend (terminal 1):**

```bash
uvicorn backend.main:app --reload
```

- API: http://localhost:8000
- Dokumentasi interaktif (Swagger): http://localhost:8000/docs

**Front end (terminal 2):**

```bash
streamlit run frontend/app.py
```

> **Catatan Frontend (branch `feature/frontend`):**
> - Frontend membutuhkan backend aktif di `http://localhost:8000`. Pastikan backend sudah berjalan sebelum membuka Streamlit.
> - Install dependensi frontend terlebih dahulu jika belum: `pip install -r requirements.txt`
> - **JANGAN jalankan file di folder `pages/` secara langsung** (misalnya `streamlit run frontend/pages/1_Overview.py`). Selalu jalankan via `frontend/app.py`.
> - Jika ada perubahan data, clear cache Streamlit dengan menu kanan atas → *Clear cache*, atau tekan `Ctrl+F5` di browser.

## Daftar Endpoint

| Method | Endpoint | Deskripsi |
|---|---|---|
| GET | `/machines` | Daftar semua mesin |
| GET | `/energy?machine_id=&start=&end=&limit=` | Data konsumsi energi per mesin, dengan filter waktu |
| GET | `/summary` | Total kWh, estimasi biaya, konsumsi per lini, jumlah alert |
| POST | `/forecast` | Prediksi konsumsi energi (body JSON) |
| GET | `/forecast/{machine_id}?hours_ahead=24` | Prediksi konsumsi energi per mesin |
| GET | `/waste-alerts?machine_id=&start=&end=` | Deteksi pemborosan listrik |

Endpoint `/forecast` dan `/waste-alerts` mengembalikan status **503** apabila model ML belum tersedia.

### Contoh Response

`GET /machines`

```json
[
  {
    "machine_id": "M01",
    "name": "CNC Milling 1",
    "line": "Line A",
    "type": "CNC",
    "rated_power_kw": 15
  }
]
```

`GET /energy?machine_id=M01`

```json
[
  {
    "machine_id": "M01",
    "timestamp": "2026-11-01T00:00:00",
    "power_kw": 1.2,
    "energy_kwh": 1.2,
    "voltage": 380,
    "current": 2.14,
    "status": "idle"
  }
]
```

`GET /summary`

```json
{
  "total_kwh": 5432.1,
  "estimated_cost_rp": 8148150,
  "per_line": { "Line A": 3200.5, "Line B": 2231.6 },
  "alert_count": 12
}
```

`POST /forecast`

```json
{
  "machine_id": "M01",
  "hours_ahead": 24
}
```

Response:

```json
{
  "machine_id": "M01",
  "hours_ahead": 24,
  "predictions": [
    { "timestamp": "2026-11-04T00:00:00", "predicted_kwh": 12.3 }
  ]
}
```

## Skema Database (MongoDB)

| Koleksi | Field |
|---|---|
| `machines` | machine_id, name, line, type, rated_power_kw |
| `energy_readings` | machine_id, timestamp, power_kw, energy_kwh, voltage, current, status (running / idle / off) |
| `production_logs` | machine_id, shift, date, units_produced |
| `forecasts` | machine_id, forecast_time, predicted_kwh |
| `waste_alerts` | machine_id, timestamp, type, severity, note |

> Field `timestamp` disimpan sebagai tipe **datetime**.

## Asumsi

- Tarif listrik: Rp 1.500 per kWh (asumsi untuk estimasi biaya).
- Seluruh data merupakan hasil simulasi, termasuk data pemborosan yang sengaja disisipkan sebagai bahan pelatihan model.

## Alur Kerja Tim (Git)

1. Jangan push langsung ke `main`.
2. Buat branch dari `main`: `feature/db`, `feature/ml-forecast`, `feature/ml-anomaly`, `feature/frontend`.
3. Commit rutin dengan pesan yang jelas (contoh: `feat: tambah endpoint summary`).
4. Push branch, lalu buat Pull Request ke `main`.
5. Project Lead melakukan review dan merge.
6. Setelah merge, jalankan `git checkout main` lalu `git pull origin main`.

## Anggota Tim

| Nama | Peran | Tanggung Jawab |
|---|---|---|
| Rifki Febian Aldiansyah| Project Lead + Backend API | Repo, REST API (FastAPI), integrasi semua modul |
| Fikri Zaini | Database + Data Engineering | Skema MongoDB, data generator, query agregasi |
| Destsa Ardiansyah | Machine Learning 1 | Model forecasting konsumsi energi |
| Nainggolan, Jovan Sesar Alexsander | Machine Learning 2 + Artikel | Model deteksi pemborosan, artikel jurnal |
| Abyan Maheswara | Front End + Presentasi | Dashboard Streamlit, slide presentasi |

## Troubleshooting

| Masalah | Solusi |
|---|---|
| `No module named 'database'` | Jalankan dari root repo, dan pastikan setiap folder punya `__init__.py` |
| `ServerSelectionTimeoutError` | Service MongoDB belum berjalan, atau `MONGO_URI` salah |
| `requires authentication` | Tambahkan username dan password ke `MONGO_URI` |
| `/machines` mengembalikan `[]` | Data belum diisi, atau `DB_NAME` di `.env` berbeda dengan database yang terisi |
| Front end terkena error CORS | Pastikan backend berjalan dan `CORSMiddleware` aktif di `backend/main.py` |

## Lisensi

Proyek ini dibuat untuk keperluan praktikum perkuliahan.