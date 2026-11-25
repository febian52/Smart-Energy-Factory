import sys
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent.parent
for p in (str(CURRENT_DIR.parent), str(ROOT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    import frontend.api_client as ac
    from frontend.api_client import (
        get_machines,
        get_forecast,
        get_energy,
        get_data_range,
        TARIF_PER_KWH,
    )
    from frontend.ui import (
        apply_theme,
        style_plotly_fig,
        format_id_num,
        format_id_currency,
    )
except ImportError:
    import api_client as ac
    from api_client import (
        get_machines,
        get_forecast,
        get_energy,
        get_data_range,
        TARIF_PER_KWH,
    )
    from ui import (
        apply_theme,
        style_plotly_fig,
        format_id_num,
        format_id_currency,
    )

# Model ML memprediksi hingga 168 jam secara autoregresif (168 langkah inferensi).
# Tingkatkan batas waktu timeout runtime ke 45 detik agar kalkulasi 7 hari tidak terputus.
if hasattr(ac, "TIMEOUT"):
    ac.TIMEOUT = 45

try:
    st.set_page_config(
        page_title="Forecast - Smart Energy Factory",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception:
    pass

# Terapkan Tema Warm Light
apply_theme()


# ---------------------------------------------------------------------------
# 1. Pengambilan Daftar Mesin (Dropdown)
# ---------------------------------------------------------------------------
try:
    machines = get_machines()
    if not machines:
        st.error("🚨 Tidak ada data mesin yang ditemukan dari backend.", icon="🚫")
        st.stop()
except RuntimeError as exc:
    st.error(
        f"🚨 **Gagal memuat daftar mesin dari API Backend:**\n\n`{exc}`\n\n"
        "Pastikan backend berjalan di `http://localhost:8000` atau periksa koneksi jaringan Anda.",
        icon="🚫",
    )
    st.stop()
except Exception as exc:
    st.error(f"Terjadi kesalahan saat memuat daftar mesin: {exc}", icon="⚠️")
    st.stop()

# ---------------------------------------------------------------------------
# Header Halaman & Kontrol Pilihan Mesin + Horizon Prediksi
# ---------------------------------------------------------------------------
header_title_html = "".join([
    '<div style="margin: 0 0 14px 0; padding-bottom: 12px; border-bottom: 1px solid #E5E8EF;">',
    '<h1 style="color: #111827; font-size: 1.55rem; font-weight: 700; margin: 0 0 4px 0; letter-spacing: -0.02em;">',
    'Forecast Konsumsi Energi',
    '</h1>',
    '<div style="font-size: 13px; font-weight: 500; color: #6B7280;">',
    'Prediksi beban energi per mesin menggunakan model ML (WIB)',
    '</div>',
    '</div>',
])
st.markdown(header_title_html, unsafe_allow_html=True)

ctrl_c1, ctrl_c2 = st.columns([2.2, 1.4])

with ctrl_c1:
    machine_options = {
        m["machine_id"]: f"{m['machine_id']} - {m.get('name', 'Mesin')} ({m.get('line', 'Line')})"
        for m in machines
    }
    selected_machine_id = st.selectbox(
        "Pilih Mesin",
        options=list(machine_options.keys()),
        format_func=lambda mid: machine_options[mid],
    )
    selected_machine = next((m for m in machines if m["machine_id"] == selected_machine_id), {})
    rated_kw = float(selected_machine.get("rated_power_kw", 0.0))

with ctrl_c2:
    st.markdown("<div style='margin-top: 26px;'></div>", unsafe_allow_html=True)
    horizon_label = st.segmented_control(
        "Horizon Prediksi",
        options=["24 Jam", "7 Hari (168 Jam)"],
        default="24 Jam",
        selection_mode="single",
        label_visibility="collapsed",
    ) or "24 Jam"
    selected_hours = 24 if horizon_label == "24 Jam" else 168

# ---------------------------------------------------------------------------
# 2. Pengambilan Data Prediksi Model ML
# ---------------------------------------------------------------------------
try:
    with st.spinner(f"Memuat prediksi untuk {selected_machine_id} ({selected_hours} jam)..."):
        forecast_res = get_forecast(selected_machine_id, hours=selected_hours, timeout=45)
except RuntimeError as exc:
    st.error(
        f"🚨 **Gagal memuat prediksi dari API Backend:**\n\n`{exc}`",
        icon="🚫",
    )
    st.stop()
except Exception as exc:
    st.error(f"Terjadi kesalahan saat memuat prediksi: {exc}", icon="⚠️")
    st.stop()

is_mock = forecast_res.get("is_mock", False) if isinstance(forecast_res, dict) else False
predictions = forecast_res.get("predictions", []) if isinstance(forecast_res, dict) else forecast_res

if not predictions:
    st.error("🚨 Data prediksi kosong dari API backend untuk mesin ini.", icon="⚠️")
    st.stop()

# ---------------------------------------------------------------------------
# 3. Pengambilan Data Aktual 72 Jam Terakhir
# ---------------------------------------------------------------------------
try:
    start_dt, end_dt = get_data_range(selected_machine_id)
    actual_start = end_dt - timedelta(hours=72)
    actual_rows = get_energy(selected_machine_id, start=actual_start, end=end_dt, limit=10000)
except Exception as exc:
    st.warning(f"⚠️ Gagal memuat data energi aktual 72 jam: {exc}")
    actual_rows = []

if len(actual_rows) >= 10000:
    st.warning("⚠️ **Peringatan Batas Data:** Data pembacaan aktual mencapai batas 10.000 baris. Beberapa data mungkin terpotong.")

# ---------------------------------------------------------------------------
# 4. Konversi Waktu dari UTC ke WIB untuk Aktual dan Prediksi
# ---------------------------------------------------------------------------
# Pemrosesan Data Aktual
if actual_rows:
    df_actual = pd.DataFrame(actual_rows)
    df_actual["timestamp"] = pd.to_datetime(df_actual["timestamp"])
    if df_actual["timestamp"].dt.tz is None:
        df_actual["timestamp"] = df_actual["timestamp"].dt.tz_localize("UTC")
    df_actual["timestamp_wib"] = df_actual["timestamp"].dt.tz_convert("Asia/Jakarta")
    df_actual["hour_wib"] = df_actual["timestamp_wib"].dt.floor("h")

    # Agregasi per jam dengan menjumlahkan energy_kwh
    df_actual_hourly = (
        df_actual.groupby("hour_wib", as_index=False)["energy_kwh"]
        .sum()
        .sort_values("hour_wib")
    )
else:
    df_actual_hourly = pd.DataFrame(columns=["hour_wib", "energy_kwh"])

# Pemrosesan Data Prediksi
df_preds = pd.DataFrame(predictions)

# Poin 7: Validasi field — jika format respons /forecast berubah, tampilkan error jelas
_required_cols = {"forecast_time", "predicted_kwh"}
if not _required_cols.issubset(df_preds.columns):
    _missing = _required_cols - set(df_preds.columns)
    st.error(
        f"🚨 **Format respons /forecast berubah — field hilang: `{_missing}`.**\n\n"
        "Hubungi tim backend untuk memastikan kolom `forecast_time` dan `predicted_kwh` tersedia.",
        icon="🚫",
    )
    st.stop()

df_preds["forecast_time"] = pd.to_datetime(df_preds["forecast_time"])
if df_preds["forecast_time"].dt.tz is None:
    df_preds["forecast_time"] = df_preds["forecast_time"].dt.tz_localize("UTC")
df_preds["timestamp_wib"] = df_preds["forecast_time"].dt.tz_convert("Asia/Jakarta")
df_preds["hour_wib"] = df_preds["timestamp_wib"].dt.floor("h")
df_preds["predicted_kwh"] = df_preds["predicted_kwh"].astype(float)
df_preds = df_preds.sort_values("hour_wib")

# ---------------------------------------------------------------------------
# 5. Tiga Kartu Ringkas (KPI)
# ---------------------------------------------------------------------------
total_pred_kwh = float(df_preds["predicted_kwh"].sum())
cost_pred = total_pred_kwh * TARIF_PER_KWH  # Tarif Rp/kWh dari api_client

if not df_preds.empty:
    peak_idx = df_preds["predicted_kwh"].idxmax()
    peak_row = df_preds.loc[peak_idx]
    peak_time_str = peak_row["timestamp_wib"].strftime("%d %b %Y, %H:00 WIB")
    peak_val = float(peak_row["predicted_kwh"])
else:
    peak_time_str = "—"
    peak_val = 0.0

mock_badge = '<span class="badge-mock">Data contoh</span>' if is_mock else ""

kpi_c1, kpi_c2, kpi_c3 = st.columns(3)

with kpi_c1:
    card1_html = "".join([
        '<div class="kpi-card" style="height:100%;">',
        f'<div class="kpi-label">Total Prediksi Energi {mock_badge}</div>',
        '<div>',
        f'<span class="kpi-val">{format_id_num(total_pred_kwh, 1)}</span>',
        '<span class="kpi-unit">kWh</span>',
        '</div>',
        '<div class="kpi-sub" style="margin-top:6px;">',
        f'<span style="color:#6B7280; font-weight:500; font-size:12px;">Horizon: <b style="color:#111827;">{selected_hours} Jam</b> ({len(df_preds)} titik jam)</span>',
        '</div>',
        '</div>',
    ])
    st.markdown(card1_html, unsafe_allow_html=True)

with kpi_c2:
    card2_html = "".join([
        '<div class="kpi-card" style="height:100%;">',
        '<div class="kpi-label">Jam Puncak Prediksi (WIB)</div>',
        '<div>',
        f'<span class="kpi-val" style="font-size:1.35rem;">{peak_time_str}</span>',
        '</div>',
        '<div class="kpi-sub" style="margin-top:6px;">',
        f'<span class="badge-pill-amber">Beban Puncak: {format_id_num(peak_val, 2)} kWh</span>',
        '</div>',
        '</div>',
    ])
    st.markdown(card2_html, unsafe_allow_html=True)

with kpi_c3:
    card3_html = "".join([
        '<div class="kpi-card" style="height:100%;">',
        '<div class="kpi-label">Estimasi Biaya Prediksi</div>',
        '<div>',
        f'<span class="kpi-val">{format_id_currency(cost_pred)}</span>',
        '</div>',
        '<div class="kpi-sub" style="margin-top:6px;">',
        f'<span class="badge-pill-blue">⚡ Tarif {format_id_currency(TARIF_PER_KWH)}</span> ',
        '<span style="color:#6B7280; font-weight:500; font-size:12px;">per kWh</span>',
        '</div>',
        '</div>',
    ])
    st.markdown(card3_html, unsafe_allow_html=True)

st.markdown("<div style='margin: 1.2rem 0;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 3 & 6. Pembuatan Grafik Plotly & Pengecekan Kapasitas
# ---------------------------------------------------------------------------
fig = go.Figure()

# Titik plotting prediksi (menyambung langsung dari titik akhir aktual)
pred_x = list(df_preds["hour_wib"])
pred_y = list(df_preds["predicted_kwh"])

if not df_actual_hourly.empty:
    last_actual_time = df_actual_hourly["hour_wib"].iloc[-1]
    last_actual_val = float(df_actual_hourly["energy_kwh"].iloc[-1])
    pred_plot_x = [last_actual_time] + pred_x
    pred_plot_y = [last_actual_val] + pred_y
else:
    last_actual_time = None
    pred_plot_x = pred_x
    pred_plot_y = pred_y

# 1. Garis Aktual: Biru Solid #1D6FF2
if not df_actual_hourly.empty:
    fig.add_trace(
        go.Scatter(
            x=df_actual_hourly["hour_wib"],
            y=df_actual_hourly["energy_kwh"],
            mode="lines",
            name="Aktual 72 Jam (kWh)",
            line=dict(color="#1D6FF2", width=2.5, shape="spline"),
            fill="tozeroy",
            fillcolor="rgba(29, 111, 242, 0.08)",
            hovertemplate="<b>Aktual</b><br>Waktu: %{x|%d %b %Y, %H:00} WIB<br>Konsumsi: <b>%{y:.2f} kWh</b><extra></extra>",
        )
    )

# 2. Garis Prediksi: Amber #F59E0B Putus-putus
fig.add_trace(
    go.Scatter(
        x=pred_plot_x,
        y=pred_plot_y,
        mode="lines",
        name=f"Prediksi {selected_hours} Jam (kWh)",
        line=dict(color="#F59E0B", width=2.5, dash="dash", shape="spline"),
        fill="tozeroy",
        fillcolor="rgba(245, 158, 11, 0.05)",
        hovertemplate="<b>Prediksi</b><br>Waktu: %{x|%d %b %Y, %H:00} WIB<br>Prediksi: <b>%{y:.2f} kWh</b><extra></extra>",
    )
)

# 3. Garis Vertikal Pemisah Tipis di Akhir Data Aktual
if last_actual_time is not None:
    fig.add_shape(
        type="line",
        x0=last_actual_time,
        x1=last_actual_time,
        y0=0,
        y1=1,
        yref="paper",
        line=dict(color="#9CA3AF", width=1.5, dash="dot"),
    )
    fig.add_annotation(
        x=last_actual_time,
        y=1.0,
        yref="paper",
        text="Batas Aktual / Mulai Prediksi",
        showarrow=False,
        xanchor="right",
        yanchor="top",
        font=dict(size=12, color="#6B7280"),
        bgcolor="rgba(255, 255, 255, 0.8)",
        borderpad=4,
    )

style_plotly_fig(fig, height=360)
fig.update_layout(
    legend=dict(
        orientation="h",
        yref="paper",
        y=1.08,
        yanchor="bottom",
        x=1,
        xanchor="right",
        font=dict(size=11, color="#6B7280"),
    ),
    margin=dict(l=20, r=20, t=60, b=30),
    hovermode="x unified",
)
fig.update_xaxes(
    title_text="Waktu (WIB)",
    title_standoff=12,
    tickfont=dict(size=11, color="#6B7280"),
    title_font=dict(size=11, color="#6B7280"),
)
fig.update_yaxes(
    title_text="Konsumsi Energi (kWh)",
    tickfont=dict(size=11, color="#6B7280"),
    title_font=dict(size=11, color="#6B7280"),
    range=[0, float(max(pred_plot_y)) * 1.25],
)

# Tampilkan Kontainer Kartu Grafik
with st.container(border=True):
    chart_card_header = "".join([
        '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">',
        '<div>',
        f'<h3 style="margin:0; font-size:1.05rem; font-weight:700; color:#111827;">Proyeksi Beban Konsumsi: {selected_machine_id}</h3>',
        f'<div style="font-size:12px; color:#6B7280; font-weight:500;">Kurva komparasi data riil 72 jam terakhir terhadap proyeksi model {selected_hours} jam ke depan (WIB)</div>',
        '</div>',
        '</div>',
    ])
    st.markdown(chart_card_header, unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Pengecekan apakah angka prediksi per jam melebihi rated_power_kw mesin
    exceeded_mask = df_preds["predicted_kwh"] > rated_kw
    exceeded_count = int(exceeded_mask.sum())
    if rated_kw > 0 and exceeded_count > 0:
        max_pred_val = float(df_preds["predicted_kwh"].max())
        warning_capacity_html = "".join([
            '<div style="font-size:12px; color:#92400E; font-weight:500; padding:9px 14px; background:#FEF3C7; border-radius:8px; border:1px solid #FDE68A; margin-top:10px; display:flex; align-items:center; gap:8px;">',
            '<span>⚠️</span>',
            f'<span><b>Prediksi melebihi kapasitas mesin:</b> Terdeteksi {exceeded_count} jam proyeksi dengan beban di atas rated power ({format_id_num(rated_kw, 1)} kW), nilai tertinggi mencapai {format_id_num(max_pred_val, 2)} kWh.</span>',
            '</div>',
        ])
        st.markdown(warning_capacity_html, unsafe_allow_html=True)

# Footer Info
st.markdown(
    "".join([
        '<div style="text-align: right; font-size: 12px; color: #6B7280; margin-top: 16px;">',
        f'Mesin: <b>{selected_machine_id}</b> (Kapasitas: <b>{format_id_num(rated_kw, 1)} kW</b>) · Horizon Prediksi: <b>{selected_hours} Jam</b> · Ditampilkan dalam Waktu Indonesia Barat (WIB)',
        '</div>',
    ]),
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Performa Model Forecast (Evaluasi Offline)
# ---------------------------------------------------------------------------
st.markdown("<div style='margin:1.2rem 0;'></div>", unsafe_allow_html=True)

with st.expander("📊 Performa Model Forecast (Evaluasi Offline)"):
    _eval_path = ROOT_DIR / "ml" / "forecast" / "hasil_evaluasi.csv"
    _horizon_path = ROOT_DIR / "ml" / "forecast" / "hasil_evaluasi_horizon.csv"

    try:
        _df_eval = pd.read_csv(_eval_path)
    except Exception as exc:
        st.caption(f"File evaluasi model tidak ditemukan atau tidak bisa dibaca: {exc}")
    else:
        st.markdown(
            "".join([
                '<div style="font-size:12px; color:#6B7280; margin-bottom:8px; line-height:1.5;">',
                'Metrik evaluasi pada data uji. Model yang dipakai di aplikasi: <b>XGBoost</b>. '
                'MAE/RMSE dalam <b>kWh per jam</b>.',
                '</div>',
            ]),
            unsafe_allow_html=True,
        )

        _eval_rows = []
        for _, _r in _df_eval.iterrows():
            _is_used = str(_r["model"]).lower() == "xgboost"
            _row_style = ' style="background:#EFF6FF;"' if _is_used else ""
            _used_badge = ' <span class="badge-pill-blue">Dipakai</span>' if _is_used else ""
            _eval_rows.append(
                f'<tr{_row_style}>'
                f'<td style="font-weight:600; color:#111827;">{_r["model"]}{_used_badge}</td>'
                f'<td>{format_id_num(float(_r["MAE"]), 2)}</td>'
                f'<td>{format_id_num(float(_r["RMSE"]), 2)}</td>'
                f'<td>{format_id_num(float(_r["MAPE_%"]), 1)}%</td>'
                f'<td>{format_id_num(float(_r["WAPE_%"]), 1)}%</td>'
                '</tr>'
            )

        st.markdown(
            "".join([
                '<div class="data-table-container"><div style="overflow-x:auto;">',
                '<table class="data-table">',
                '<thead><tr><th>Model</th><th>MAE (kWh)</th><th>RMSE (kWh)</th><th>MAPE (%)</th><th>WAPE (%)</th></tr></thead>',
                '<tbody>',
                "".join(_eval_rows),
                '</tbody></table></div></div>',
            ]),
            unsafe_allow_html=True,
        )

        try:
            _df_horizon = pd.read_csv(_horizon_path)
        except Exception:
            _df_horizon = None

        if _df_horizon is not None and not _df_horizon.empty:
            _horizon_rows = []
            for _, _r in _df_horizon.iterrows():
                _xgb_mae = float(_r.get("XGBoost", 0.0))
                _naive_mae = float(_r.get("SeasonalNaive(168h)", 0.0))
                _improvement = ((_naive_mae - _xgb_mae) / _naive_mae * 100) if _naive_mae else 0.0
                _horizon_rows.append(
                    f'<tr>'
                    f'<td style="font-weight:600; color:#111827;">{_r["bucket"]}</td>'
                    f'<td>{format_id_num(_xgb_mae, 2)}</td>'
                    f'<td>{format_id_num(_naive_mae, 2)}</td>'
                    f'<td>{format_id_num(_improvement, 1)}%</td>'
                    '</tr>'
                )

            st.markdown(
                "".join([
                    '<div style="font-size:12px; color:#6B7280; margin:14px 0 6px 0; line-height:1.5;">',
                    '<b>MAE per horizon</b> — perbandingan XGBoost vs baseline Seasonal Naive.',
                    '</div>',
                    '<div class="data-table-container"><div style="overflow-x:auto;">',
                    '<table class="data-table">',
                    '<thead><tr><th>Horizon</th><th>XGBoost MAE</th><th>Seasonal Naive MAE</th><th>XGBoost lebih baik</th></tr></thead>',
                    '<tbody>',
                    "".join(_horizon_rows),
                    '</tbody></table></div></div>',
                ]),
                unsafe_allow_html=True,
            )

        st.caption(
            "MAPE bisa terlihat tinggi karena banyak jam dengan konsumsi rendah; "
            "WAPE lebih representatif untuk beban yang tidak rata."
        )
