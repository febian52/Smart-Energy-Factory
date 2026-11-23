# Laporan Benchmark Smart Energy (2026-11-23 15:29)

## 1. Volume data

| Metrik | Nilai |
|---|---|
| Jumlah mesin | 12 |
| Interval (menit) | 5 |
| Rentang UTC | 2026-01-01 00:00 s/d 2026-06-29 23:55 |
| Rentang WIB | 2026-01-01 07:00 s/d 2026-06-30 06:55 |
| Jumlah hari | 180 |
| Persentase pemborosan | 4.06% |
| Dokumen machines | 12 |
| Dokumen energy_readings | 622,080 |
| Dokumen production_logs | 6,480 |
| Dokumen forecasts | 0 |
| Dokumen waste_alerts | 0 |
| Dokumen waste_labels | 25,250 |

## 2. Ukuran penyimpanan (MB)

| collection | docs | dataSize_MB | storageSize_MB | indexSize_MB | avgDocSize_MB | avgDocSize_bytes |
|---|---|---|---|---|---|---|
| machines | 12 | 0.0 | 0.02 | 0.04 | 0.000117 | 123 |
| energy_readings | 622080 | 89.8 | 27.29 | 13.33 | 0.000144 | 151 |
| production_logs | 6480 | 0.58 | 0.16 | 0.21 | 9e-05 | 94 |
| forecasts | 0 | 0.0 | 0.0 | 0.01 | 0.0 | 0 |
| waste_alerts | 0 | 0.0 | 0.0 | 0.01 | 0.0 | 0 |
| waste_labels | 25250 | 2.49 | 0.48 | 0.58 | 9.8e-05 | 103 |

## 3. Kinerja insert (insert_many, batch 10.000)

| collection | docs | insert_seconds | docs_per_second |
|---|---|---|---|
| energy_readings | 622080 | 3.48 | 178594 |
| production_logs | 6480 | 0.05 | 136625 |
| waste_labels | 25250 | 0.23 | 111923 |
| machines | 12 | 0.02 | 776 |
| TOTAL | 653822 | 3.78 | 172969 |

Waktu generate di memori: 0.5 s; waktu membuat index: 2.7 s.

## 4. Kinerja query (rata-rata ms dari 5 kali ulang, setelah 1x pemanasan)

| data | docs | query | tanpa index (ms) | dengan index (ms) | percepatan (x) |
|---|---|---|---|---|---|
| 100k | 99,996 | energy_1machine_1week | 134.2 | 8.1 | 16.6 |
| 100k | 99,996 | daily_kwh_per_machine | 325.3 | 293.7 | 1.1 |
| 100k | 99,996 | avg_kwh_per_hour | 347.6 | 369.8 | 0.9 |
| 100k | 99,996 | top5_kwh | 66.4 | 75.1 | 0.9 |
| 100k | 99,996 | top5_waste_kwh | timeout > 5 s | 1118.4 | - |
| 300k | 300,000 | energy_1machine_1week | 388.5 | 10.0 | 38.9 |
| 300k | 300,000 | daily_kwh_per_machine | 923.3 | 903.9 | 1.0 |
| 300k | 300,000 | avg_kwh_per_hour | 1188.1 | 1152.7 | 1.0 |
| 300k | 300,000 | top5_kwh | 216.5 | 229.0 | 0.9 |
| 300k | 300,000 | top5_waste_kwh | timeout > 5 s | 3756.4 | - |
| penuh | 622,080 | energy_1machine_1week | 725.9 | 6.0 | 121.0 |
| penuh | 622,080 | daily_kwh_per_machine | 1887.2 | 1971.1 | 1.0 |
| penuh | 622,080 | avg_kwh_per_hour | 2356.4 | 2366.4 | 1.0 |
| penuh | 622,080 | top5_kwh | 501.8 | 492.9 | 1.0 |
| penuh | 622,080 | top5_waste_kwh | timeout > 5 s | timeout > 5 s | - |

## 5. Hasil explain('executionStats')

`nReturned` pada agregasi = dokumen yang keluar dari tahap pembacaan koleksi (bukan jumlah hasil akhir). Kolom lookup menunjukkan pemindaian koleksi dalam `$lookup`.

| dataset | query | indexed | scan_stage | docs_examined | n_returned | explain_ms | lookup_scan | lookup_docs_examined |
|---|---|---|---|---|---|---|---|---|
| 100k | energy_1machine_1week | tidak | COLLSCAN | 99996 | 2016 | 126 |  |  |
| 100k | daily_kwh_per_machine | tidak | COLLSCAN | 99996 | 360 | 364 |  |  |
| 100k | avg_kwh_per_hour | tidak | COLLSCAN | 99996 | 288 | 369 |  |  |
| 100k | top5_kwh | tidak | COLLSCAN | 99996 | 12 | 91 |  |  |
| 100k | top5_waste_kwh | tidak | COLLSCAN | None | None | None |  |  |
| 100k | energy_1machine_1week | ya | IXSCAN | 2016 | 2016 | 1 |  |  |
| 100k | daily_kwh_per_machine | ya | COLLSCAN | 99996 | 360 | 276 |  |  |
| 100k | avg_kwh_per_hour | ya | COLLSCAN | 99996 | 288 | 378 |  |  |
| 100k | top5_kwh | ya | COLLSCAN | 99996 | 12 | 100 |  |  |
| 100k | top5_waste_kwh | ya | COLLSCAN | 3706 | 3706 | 1374 |  |  |
| 300k | energy_1machine_1week | tidak | COLLSCAN | 300000 | 2016 | 337 |  |  |
| 300k | daily_kwh_per_machine | tidak | COLLSCAN | 300000 | 1056 | 881 |  |  |
| 300k | avg_kwh_per_hour | tidak | COLLSCAN | 300000 | 288 | 1143 |  |  |
| 300k | top5_kwh | tidak | COLLSCAN | 300000 | 12 | 256 |  |  |
| 300k | top5_waste_kwh | tidak | COLLSCAN | None | None | None |  |  |
| 300k | energy_1machine_1week | ya | IXSCAN | 2016 | 2016 | 4 |  |  |
| 300k | daily_kwh_per_machine | ya | COLLSCAN | 300000 | 1056 | 909 |  |  |
| 300k | avg_kwh_per_hour | ya | COLLSCAN | 300000 | 288 | 1156 |  |  |
| 300k | top5_kwh | ya | COLLSCAN | 300000 | 12 | 264 |  |  |
| 300k | top5_waste_kwh | ya | COLLSCAN | 12125 | 12125 | 4197 |  |  |
| penuh | energy_1machine_1week | tidak | COLLSCAN | 622080 | 2016 | 698 |  |  |
| penuh | daily_kwh_per_machine | tidak | COLLSCAN | 622080 | 2172 | 1858 |  |  |
| penuh | avg_kwh_per_hour | tidak | COLLSCAN | 622080 | 288 | 2420 |  |  |
| penuh | top5_kwh | tidak | COLLSCAN | 622080 | 12 | 509 |  |  |
| penuh | top5_waste_kwh | tidak | COLLSCAN | None | None | None |  |  |
| penuh | energy_1machine_1week | ya | IXSCAN | 2016 | 2016 | 1 |  |  |
| penuh | daily_kwh_per_machine | ya | COLLSCAN | 622080 | 2172 | 1895 |  |  |
| penuh | avg_kwh_per_hour | ya | COLLSCAN | 622080 | 288 | 2404 |  |  |
| penuh | top5_kwh | ya | COLLSCAN | 622080 | 12 | 540 |  |  |
| penuh | top5_waste_kwh | ya | COLLSCAN | None | None | None |  |  |

## 6. Spesifikasi mesin uji

| Item | Nilai |
|---|---|
| OS | Windows 11 |
| CPU | Intel64 Family 6 Model 151 Stepping 2, GenuineIntel |
| Core | 8 fisik / 12 logis |
| RAM | 19.8 GB |
| MongoDB | 8.0.10 |
| Python | 3.14.3 |
| PyMongo | 4.20.1 |
