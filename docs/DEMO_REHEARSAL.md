# Run Sheet Rehearsal Demo — Smart Energy Factory

Target durasi: **10 menit** (+ 5 menit Q&A)
Periode data demo: **24–30 Juni 2026 (WIB)** — dataset simulasi historis.

---

## 0. Keputusan data: JANGAN regenerate (H-1)

Dataset yang ada sekarang dipakai untuk semua angka, model, dan screenshot. Regenerate H-1 berisiko:

- `--start-date` berbeda → hari-dalam-minggu dan pola libur bergeser, sehingga seluruh nilai data berubah.
- Model forecast (Didi), model anomali (Jovan), metrik MAE/RMSE/WAPE dan precision/recall/F1, serta screenshot artikel dihitung dari data lama → jadi tidak cocok dengan dashboard.
- `python -m database.generate_data` **tidak dijamin jalan**: file memakai `import db`, bukan import paket. Cek dulu kalau memang mau dipakai.
- `HOLIDAYS` di generator hanya sampai Juni 2026.

Kalau tim tetap mau regenerate: pakai DB terpisah (`smart_energy_demo`), arahkan backend ke DB itu, lalu latih ulang kedua model. Tidak realistis semalam.

**Narasi resmi data (pakai ini kalau ditanya):**

> "Dataset ini adalah dataset historis simulasi Januari–Juni 2026: 12 mesin, interval 5 menit, 622.080 pembacaan, dibangkitkan dengan seed tetap untuk reproduksibilitas. Jadi ini bukan data realtime pabrik."

Catatan: reproduksibilitas penuh butuh versi numpy yang sama. Kalau beda versi, hasil bisa bergeser sedikit.

---

## 1. Pre-flight (15 menit sebelum tampil)

- [ ] MongoDB jalan
- [ ] Backend jalan: `uvicorn backend.main:app --reload` → cek `http://localhost:8000/docs`
- [ ] Streamlit jalan: `streamlit run frontend/app.py`
- [ ] Buka semua halaman sekali (Beranda → Overview → Detail Mesin → Forecast → Waste Alerts) supaya cache panas
- [ ] Tes toggle **Mesin / Lini / Shift** di Overview
- [ ] Tes Forecast **24 Jam** dan **7 Hari**
- [ ] Tes filter tanggal + tombol **Unduh CSV** di Waste Alerts
- [ ] Buka kedua expander **Performa Model**
- [ ] Screenshot semua halaman untuk backup
- [ ] Tutup notifikasi, chat, dan tab lain
- [ ] Browser zoom 100–110%, sembunyikan bookmark bar
- [ ] Colok charger

> Load pertama bisa 10–20 detik (backend cold start + model + 12 mesin).
> Setelah halaman dibuka sekali, navigasi berikutnya cepat karena cache.

---

## 2. Run sheet 10 menit

| Waktu | Halaman | Aksi | Poin bicara |
|---|---|---|---|
| 0:00–0:40 | Beranda | Tunjuk sidebar + status backend | Latar belakang: 12 mesin, 3 lini, listrik tidak termonitor |
| 0:40–1:20 | Beranda | Scroll kartu modul | 4 modul: Overview, Detail Mesin, Forecast, Waste Alerts |
| 1:20–3:40 | Overview | Total kWh + biaya; toggle Mesin → Lini → Shift; donut status; kartu alert | Angka utama + insight per lini/shift |
| 3:40–5:00 | Detail Mesin | Pilih M01; 4 KPI; grafik daya; donut utilisasi; tabel | Drill-down telemetri per mesin |
| 5:00–7:00 | Forecast | Pilih M01; 24 jam; aktual vs prediksi; 7 hari; warning kapasitas; expander performa | Cara kerja model + akurasi |
| 7:00–9:00 | Waste Alerts | Filter 7 hari; KPI; tabel; CSV; tab Analisis; expander performa | Deteksi anomali + estimasi biaya |
| 9:00–10:00 | Closing | Balik ke Beranda / slide | Kesimpulan, keterbatasan, future work |

---

## 3. Script per halaman

### Opening (0:00)
> "Selamat pagi/siang. Kami dari tim Smart Energy Factory. Latar belakangnya, pabrik punya 12 mesin di 3 lini produksi, tapi konsumsi listrik belum termonitor dan pemborosan sulit dideteksi. Kami bangun dashboard yang memantau, memprediksi, dan mendeteksi pemborosan listrik."

### Overview (1:20)
> "Ini ringkasan 7 hari terakhir, periode 24–30 Juni 2026. Total konsumsi **36.843,9 kWh**, estimasi biaya **Rp 55.265.867** dengan tarif Rp 1.500 per kWh. Kalau saya ubah ke tampilan **Lini**, terlihat Line C konsumsi tertinggi. Kalau ke **Shift**, shift Pagi paling dominan. Di kanan ada distribusi status running/idle/off dan ringkasan alert."

### Detail Mesin (3:40)
> "Di sini kami bisa drill-down per mesin. Contoh M01 CNC Milling: total energi, daya rata-rata dan puncak, status terakhir, serta durasi running/idle/off. Ini penting karena **idle tapi daya masih tinggi** adalah salah satu pola pemborosan yang kami deteksi."

### Forecast (5:00)
> "Model XGBoost memprediksi 24 jam sampai 7 hari ke depan. Garis biru data aktual 72 jam terakhir, garis amber prediksi. Model dilatih **direct multi-horizon**, jadi error tidak menumpuk. Evaluasi offline: **MAE 6,40 kWh/jam**, **WAPE 30,4%**, lebih baik dari baseline Seasonal Naive 7,36."

### Waste Alerts (7:00)
> "Halaman ini mendeteksi anomali. Isolation Forest menemukan pola menyimpang, lalu aturan kami memberi tipe dan severity. Tipe yang kami bedakan: **idle high power**, **spike**, **running tanpa produksi**, **kebocoran daya saat off**, dan **deviasi pola daya**. Contoh: mesin idle dengan daya di atas 25% rated power masuk **idle high power**."

> "Dari 748 kasus di 7 hari, total energi pada interval anomali **1.759,0 kWh** atau setara **Rp 2.638.441**. Angka ini konsumsi listrik saat anomali terjadi, bukan selisih terhadap baseline normal — jadi kami sebut estimasi biaya, bukan klaim kerugian bersih."

> "Di data uji berlabel: **precision 61,4%**, **recall 63,5%**, **F1 62,5%**."

### Closing (9:00)
> "Kesimpulannya, dashboard ini bukan cuma monitoring, tapi juga forecasting dan deteksi pemborosan dengan estimasi biaya. Keterbatasannya, data masih simulasi dan belum realtime. Ke depan kami akan tambah streaming ingestion, alerting, dan autentikasi."

---

## 4. Cue card angka

| Item | Angka |
|---|---|
| Mesin / lini / shift | 12 mesin · 3 lini · 3 shift |
| Periode demo | 24–30 Juni 2026 WIB |
| Total konsumsi 7 hari | 36.843,9 kWh |
| Estimasi biaya konsumsi | Rp 55.265.867 (Rp 1.500/kWh) |
| Lini | A 10.160,5 · B 13.130,6 · C 13.552,8 kWh |
| Shift | Pagi 16.136,0 · Siang 13.495,6 · Malam 7.212,3 kWh |
| Waste alert 7 hari | 748 kasus |
| Energi interval anomali | 1.759,0 kWh |
| Estimasi biaya anomali | Rp 2.638.441 |
| Mesin alert terbanyak | M09 — 165 kasus · 869,8 kWh |
| Forecast XGBoost | MAE 6,40 · RMSE 11,92 · MAPE 34,3% · WAPE 30,4% |
| Baseline Seasonal Naive | MAE 7,36 · WAPE 35,0% |
| Anomali (data uji) | P 61,4% · R 63,5% · F1 62,5% |
| Data uji anomali | 4.148 anomali / 103.680 baris · contamination 4% |

---

## 5. Antisipasi Q&A

| Pertanyaan | Jawaban singkat |
|---|---|
| "Ini realtime?" | "Belum. Ini dataset historis simulasi Jan–Jun 2026. Arsitekturnya siap untuk streaming, tapi ingestion realtime belum diimplementasikan." |
| "Datanya dari mana?" | "Dataset historis simulasi Januari–Juni 2026: 12 mesin, interval 5 menit, 622.080 pembacaan, dibangkitkan dengan seed tetap untuk reproduksibilitas. Bukan data realtime pabrik." |
| "Kenapa data terakhirnya Juni 2026?" | "Itu periode dataset simulasi yang kami pakai. Dashboard menampilkan periodenya secara eksplisit." |
| "Akurasi forecast?" | "MAE 6,40 kWh/jam, WAPE 30,4%, lebih baik dari baseline Seasonal Naive 7,36." |
| "MAPE kok 34%?" | "Banyak jam dengan konsumsi rendah, jadi persentase error besar. WAPE lebih representatif." |
| "Akurasi anomaly?" | "Precision 61,4%, recall 63,5%, F1 62,5% pada data uji berlabel." |
| "Rp 2,6 juta itu kerugian?" | "Itu estimasi biaya energi pada interval yang ditandai anomali, belum dikurangi baseline normal. Jadi kami sebut estimasi, bukan kerugian bersih." |
| "Kenapa XGBoost?" | "Menangani pola non-linear dan fitur waktu, dan mengalahkan baseline di evaluasi." |
| "Bedanya sama dashboard biasa?" | "Kami tambah forecasting dan anomaly detection, bukan cuma visualisasi." |
| "Keterbatasan?" | "Data simulasi, belum realtime, evaluasi offline, belum ada auth." |

---

## 6. Latihan 3 putaran

1. **Putaran 1 — klik saja (5 menit).** Tanpa bicara. Catat halaman mana yang lag/blank.
2. **Putaran 2 — full script (10 menit).** Pakai timer, rekam layar. Target selesai 9:30.
3. **Putaran 3 — diganggu (12 menit).** Minta teman bertanya 3 kali di tengah. Latih transisi balik ke materi.

---

## 7. Kalau ada masalah saat demo

| Masalah | Aksi |
|---|---|
| Sidebar "Backend Terputus" | Nyalakan backend, tunggu, klik **Muat Ulang Data** |
| Halaman lambat | Tunggu spinner, jangan klik berulang |
| Muncul badge "Data contoh" | Model 503 → jelaskan fallback, atau restart backend |
| Waste Alerts kosong | Reset filter tanggal ke default 7 hari |
| KPI energi/biaya tidak muncul | Data contoh tidak punya field daya → jelaskan, lanjut ke tabel |
| Data terlihat lama | Klik **Muat Ulang Data** di sidebar |
| Semua gagal | Pindah ke screenshot/video backup |

---

## 8. Jangan dilakukan saat demo

- Jangan buka Swagger `/summary` — `alert_count`-nya 0 dan bisa bertentangan dengan dashboard.
- Jangan regenerate data atau menjalankan generator saat rehearsal/demo.
- Jangan bilang **"realtime"**.
- Jangan melebarkan filter tanggal Detail Mesin terlalu jauh (aman 7 hari).
- Jangan sebut angka anomali sebagai "kerugian bersih" tanpa menyebut baseline.
- Jangan buka DevTools/terminal di layar proyektor.
