# Bahan Presentasi & Slide — Smart Energy Factory

Dokumen ini berisi angka final, narasi, dan susunan slide. Semua angka sudah
diverifikasi langsung ke database `smart_energy`, bukan dari ingatan.

---

## 0. Angka Final (terverifikasi)

Perintah pembuktian (jalankan dari root proyek, MongoDB aktif):

```bash
python -m database.db
```

Output aktual:

```
Koneksi OK -> smart_energy
  machines                 12
  energy_readings     622,080
  production_logs       6,480
  forecasts                 0
  waste_alerts              0
  waste_labels         25,250
```

| Metrik | Nilai | Cara cek |
|---|---|---|
| Jumlah mesin | 12 | `machines` |
| Jumlah lini | 3 (Line A, B, C) | field `line` di `machines` |
| Interval pencatatan | 5 menit | 288 baris/mesin/hari |
| Rentang data | 180 hari, 1 Jan – 30 Jun 2026 WIB | `timestamp` pertama & terakhir |
| `energy_readings` | 622.080 | 12 × 180 × 288 |
| `production_logs` | 6.480 | 12 × 180 × 3 shift |
| `waste_labels` | 25.250 | 4,06% dari `energy_readings` |
| Baris per mesin (180 hari) | 51.840 | 180 × 288 |
| Seed | 42 | `database/generate_data.py` |
| Generator | `database/generate_data.py` | reproducible dengan seed sama |

Persentase pemborosan: `25.250 / 622.080 × 100 = 4,0587%` → **4,06%**.

Catatan waktu: timestamp di MongoDB disimpan UTC (`2026-01-01 00:00` s/d
`2026-06-29 23:55`). Dalam WIB itu setara **1 Jan 07:00 – 30 Jun 06:55**,
yaitu 180 hari kalender. Sebut di slide sebagai "180 hari (1 Jan – 30 Jun 2026 WIB)".

---

## 1. Jawaban "Datanya dari mana?"

### Versi pendek (1 kalimat)

> "Ini dataset historis simulasi 180 hari, Januari sampai Juni 2026, 12 mesin,
> interval 5 menit, total 622.080 pembacaan, dibangkitkan dengan seed tetap 42
> sehingga reproducible."

### Versi lengkap (30 detik)

> "Kami tidak memakai data pabrik asli karena data konsumsi listrik per mesin
> itu rahasia dan sulit diakses. Jadi kami membangun simulator terkontrol:
> 12 mesin di 3 lini, pola shift, hari libur, dan tiga jenis pemborosan yang
> sengaja diinjeksi lalu diberi label. Totalnya 622.080 pembacaan energi,
> 6.480 log produksi, dan 25.250 label pemborosan atau 4,06%.
>
> Karena labelnya kita tahu ground truth-nya, model bisa dievaluasi secara
> objektif — kita bisa hitung precision, recall, F1, dan MAE dengan benar.
> Kalau pakai data nyata tanpa label, evaluasi jadi subjektif.
>
> Dataset dibangkitkan dengan seed 42, jadi kalau dijalankan ulang di laptop
> lain dengan versi numpy sama, hasilnya identik. Ini penting supaya angka di
> laporan bisa direproduksi."

### Kalau ditanya lanjutan

| Pertanyaan | Jawaban |
|---|---|
| "Berarti datanya palsu?" | "Simulasi, bukan palsu. Polanya mengikuti karakter mesin nyata: rated power, shift, hari libur, dan pola beban. Yang disimulasikan adalah kondisinya, bukan metodenya." |
| "Kenapa tidak data asli?" | "Data energi per mesin adalah data operasional sensitif. Simulasi juga memberi kami label ground truth, yang tidak tersedia di data asli." |
| "Bisa dipercaya?" | "Bisa direproduksi: seed 42 + `generate_data.py`. Volume dan distribusinya bisa dicek ulang kapan saja dengan `python -m database.db`." |
| "Berapa lama datanya?" | "180 hari, 1 Januari – 30 Juni 2026 WIB." |
| "Kenapa berakhir Juni, sekarang November?" | "Karena ini dataset historis simulasi yang dibekukan untuk evaluasi. Bukan data realtime — dashboard menampilkan data historis, bukan streaming." |

**Jangan pernah bilang "realtime".** Selalu "dataset historis simulasi".

---

## 2. Pembagian Materi

| Orang | Bagian | Angka kunci |
|---|---|---|
| Rifki | Arsitektur backend & integrasi | 622.080 dokumen, endpoint REST |
| Fikri | Database & benchmark | insert 3,78 s; query 121× lebih cepat dengan index |
| Didi | Forecast | MAE 6,40 · RMSE 11,92 · WAPE 30,4% (baseline 7,36) |
| Jovan | Anomaly detection | Precision 61,4% · Recall 63,5% · F1 62,5% |
| Abyan | Dashboard & demo | 748 alert · 1.759,0 kWh · Rp 2.638.441 |

---

## 3. Susunan Slide (12 slide)

### Slide 1 — Judul
- Smart Energy Factory: Monitoring & Deteksi Pemborosan Energi
- Nama tim, mata kuliah, tanggal

### Slide 2 — Masalah
- Konsumsi listrik pabrik tidak terpantau per mesin
- Pemborosan (idle, spike, running tanpa produksi) tidak terdeteksi dini
- Monitoring manual tidak cukup: 622.080 titik data per 6 bulan
- *Pembicara: Abyan*

### Slide 3 — Tujuan
- Dashboard monitoring konsumsi energi per mesin/lini/shift
- Prediksi konsumsi (forecast)
- Deteksi anomali pemborosan + estimasi biaya
- *Pembicara: Abyan*

### Slide 4 — Dataset
- 12 mesin · 3 lini · interval 5 menit · 180 hari (1 Jan – 30 Jun 2026 WIB)
- 622.080 `energy_readings`
- 6.480 `production_logs` (3 shift × 180 hari × 12 mesin)
- 25.250 `waste_labels` = 4,06%
- Seed 42, reproducible via `generate_data.py`
- *Pembicara: Fikri*

### Slide 5 — Arsitektur
- Streamlit → FastAPI → MongoDB
- Lapisan ML: forecast (XGBoost) + anomaly (Isolation Forest)
- *Pembicara: Rifki*

### Slide 6 — Database & Benchmark
- Insert 622.080 dokumen: 3,48 s (178.594 dok/s)
- Ukuran data: 27,29 MB
- Query 1 mesin 1 minggu: 725,9 ms → **6,0 ms** dengan index (**121×**)
- *Pembicara: Fikri*
- Sumber: `database/benchmark_report/benchmark_summary.md`

### Slide 7 — Forecast
- Model: XGBoost
- MAE 6,40 kWh · RMSE 11,92 kWh · WAPE 30,4%
- Baseline MAE 7,36 → model lebih baik
- *Pembicara: Didi*

### Slide 8 — Anomaly Detection
- Isolation Forest + aturan bisnis untuk tipe & severity
- Precision 61,4% · Recall 63,5% · F1 62,5%
- 4.148 anomali dari 103.680 observasi uji (contamination 4%)
- *Pembicara: Jovan*

### Slide 9 — Dashboard: Overview
- Total energi 7 hari: 36.843,9 kWh
- Estimasi biaya: Rp 55.265.867
- Lini tertinggi: Line C (13.552,8 kWh)
- Shift tertinggi: Pagi (16.136,0 kWh)
- *Pembicara: Abyan*

### Slide 10 — Dashboard: Waste Alerts
- 748 kasus dalam 7 hari
- Energi pada interval anomali: 1.759,0 kWh
- Estimasi biaya energi anomali: Rp 2.638.441
- Contoh: M01 = 16 kasus, Rp 117.276
- *Pembicara: Abyan*

### Slide 11 — Demo Langsung
- Urutan: Overview → Detail Mesin → Forecast → Waste Alerts
- Skenario klik ada di `docs/DEMO_REHEARSAL.md`
- *Pembicara: Abyan*

### Slide 12 — Kesimpulan & Saran
- Dashboard menjawab: berapa konsumsi, berapa biayanya, di mana pemborosannya
- Keterbatasan: data simulasi, bukan realtime
- Saran: integrasi meter fisik, retraining berkala, alert ke WhatsApp/email
- *Pembicara: semua*

---

## 4. Benchmark — Pakai Laporan yang Ada

Laporan sudah tersedia di:

```
database/benchmark_report/benchmark_summary.md
```

(Bukan folder `benchmark_report/` di root — foldernya ada di dalam `database/`.)

Angka yang aman dikutip:

| Metrik | Nilai |
|---|---|
| Insert 622.080 dokumen | 3,48 s · 178.594 dok/s |
| Total dokumen diuji | 653.822 dalam 3,78 s |
| Ukuran `energy_readings` | 27,29 MB (storage) |
| Query 1 mesin 1 minggu (penuh) | 725,9 ms tanpa index → 6,0 ms dengan index |
| Percepatan | **121×** |
| Query 1 mesin 1 minggu (100k) | 134,2 ms → 8,1 ms (16,6×) |

> ⚠️ **Jangan jalankan `benchmark.py` saat latihan atau presentasi.**
> Script itu membuat database sementara dan membebani MongoDB, sehingga
> dashboard jadi lambat. Cukup kutip laporan di atas.

---

## 5. Soal "Bug Detail Mesin Kepotong 34 Hari"

### Penyebab asli

Batas 10.000 baris. Dengan 288 baris/hari, 10.000 baris = **34,7 hari**.
Request lama meminta `limit=10000` sekali jalan, jadi rentang lebih panjang
terpotong di hari ke-34.

### Status: sudah diperbaiki di frontend

`frontend/api_client.py` → `get_energy(..., page_all=True)` sekarang memakai
**paging berbasis timestamp**: ambil 10.000 baris, lanjut dari timestamp
terakhir + 1 detik, ulangi sampai rentang habis (batas aman 200.000 baris).

Hasil uji 180 hari penuh, mesin M01:

```
rows: 51840  expected: 51840  match: True
elapsed_s: 2.51
first: 2026-01-01T00:00:00  last: 2026-06-29T23:55:00
duplicate_ts: 0
```

Jadi **tidak perlu** mengubah backend. `limit=0` juga terbukti jalan
(51.840 baris, 7 MB, 2,35 s dalam satu respons), tapi respons 7 MB lebih
berisiko daripada 6 request kecil. Paging frontend lebih aman.

### Soal downsampling grafik

Sudah aman, tidak perlu kerja tambahan:

- Grafik Detail Mesin sudah agregasi: mode **Per Jam** (`groupby` per jam) dan
  **Harian** (`groupby` per tanggal). Tidak pernah plot 51.840 titik mentah.
- Tabel hanya menampilkan 50 baris pertama, dengan caption total baris.

### Balasan siap kirim ke Fikri

> "Makasih Fikri. Soal limit 10.000: akarnya benar di situ, tapi sudah gua
> perbaiki di sisi frontend. `get_energy()` sekarang paging per timestamp
> (`page_all=True`), jadi 180 hari × 288 = 51.840 baris kebaca semua —
> sudah gua tes: 51.840 baris, 0 duplikat, 2,5 detik. Backend nggak perlu
> diubah. `limit=0` juga gua tes dan jalan (51.840 baris, 7 MB), tapi paging
> 6 request kecil lebih aman daripada satu respons 7 MB. Untuk grafik, Detail
> Mesin sudah agregasi per jam/harian dan tabel cuma render 50 baris, jadi
> downsampling sudah beres. Angka 12 mesin / 622.080 / 6.480 / 25.250 (4,06%)
> / seed 42 sudah gua verifikasi ulang pakai `python -m database.db` — klop."

---

## 6. Cue Card Angka (hafalkan)

```
Dataset   : 12 mesin · 3 lini · 5 menit · 180 hari · 622.080 baris · seed 42
Label     : 25.250 pemborosan = 4,06%
7 hari    : 36.843,9 kWh · Rp 55.265.867
Line C    : 13.552,8 kWh (tertinggi)
Shift Pagi: 16.136,0 kWh (tertinggi)
Forecast  : MAE 6,40 · RMSE 11,92 · WAPE 30,4% (baseline 7,36)
Anomaly   : P 61,4% · R 63,5% · F1 62,5%
Alert 7h  : 748 kasus · 1.759,0 kWh · Rp 2.638.441
M01       : 16 kasus · Rp 117.276
```

---

## 7. Jebakan Saat Demo

| Jebakan | Hindari |
|---|---|
| Bilang "realtime" | Selalu "data historis simulasi" |
| Buka Swagger `/summary` | `alert_count` masih 0, kontradiksi dengan dashboard |
| Jalankan `benchmark.py` | Bebani MongoDB, dashboard melambat |
| Regenerate dataset | Bikin model, metrik, dan screenshot lama tidak valid |
| Klik "Muat Ulang Data" berkali-kali | Cache 600 s; reload memicu request ulang |
| Backend cold start | Tunggu 15–20 s sebelum mulai demo |
