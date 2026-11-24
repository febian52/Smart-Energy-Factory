import sys
from pathlib import Path
from datetime import datetime, time, timedelta
import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent.parent
for p in (str(CURRENT_DIR.parent), str(ROOT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from frontend.api_client import get_machines, get_waste_alerts, get_data_range
    from frontend.ui import apply_theme, style_plotly_fig
except ImportError:
    from api_client import get_machines, get_waste_alerts, get_data_range
    from ui import apply_theme, style_plotly_fig

st.set_page_config(
    page_title="Waste Alerts - Smart Factory Energy Management",
    page_icon="⚡",
    layout="wide",
)

apply_theme()


# ---------------------------------------------------------------------------
# Helper: Badge severity → HTML pill
# ---------------------------------------------------------------------------
SEVERITY_BADGE = {
    "low":    '<span style="display:inline-flex;align-items:center;gap:5px;background:rgba(22,163,74,0.10);color:#16A34A;border-radius:20px;padding:3px 10px;font-size:0.75rem;font-weight:700;">Low</span>',
    "medium": '<span style="display:inline-flex;align-items:center;gap:5px;background:rgba(242,194,48,0.15);color:#A07A00;border-radius:20px;padding:3px 10px;font-size:0.75rem;font-weight:700;">Medium</span>',
    "high":   '<span style="display:inline-flex;align-items:center;gap:5px;background:rgba(232,89,12,0.12);color:#E8590C;border-radius:20px;padding:3px 10px;font-size:0.75rem;font-weight:700;">High</span>',
}
SEVERITY_COLOR = {"low": "#16A34A", "medium": "#F2C230", "high": "#E8590C"}
SEVERITY_NUM   = {"low": 1, "medium": 2, "high": 3}


# ---------------------------------------------------------------------------
# 1. Load Mesin
# ---------------------------------------------------------------------------
try:
    with st.spinner("Memuat daftar mesin..."):
        machines = get_machines()
    if not machines:
        st.error("🚨 Tidak ada mesin yang terdaftar di database.", icon="🚫")
        st.stop()
except RuntimeError as exc:
    st.error(f"🚨 **Gagal memuat daftar mesin:**\n\n`{exc}`\n\nPastikan backend berjalan di `http://localhost:8000`.", icon="🚫")
    st.stop()
except Exception as exc:
    st.error(f"Terjadi kesalahan saat memuat mesin: {exc}", icon="⚠️")
    st.stop()


# ---------------------------------------------------------------------------
# Header Halaman (judul kiri, filter kanan)
# ---------------------------------------------------------------------------
hdr_c1, hdr_c2 = st.columns([2.0, 1.4])

with hdr_c1:
    st.markdown(
        "".join([
            '<div style="margin-bottom:12px;">',
            '<h1 style="color:#1F1A17; font-size:2.2rem; font-weight:800; margin:0 0 4px 0; letter-spacing:-0.03em;">',
            'Waste Alerts',
            '</h1>',
            '<div style="font-size:0.78rem; font-weight:700; color:#6B6259; text-transform:uppercase; letter-spacing:0.08em;">',
            '// DETEKSI ANOMALI OPERASIONAL · PEMBOROSAN &amp; OVERCONSUMPTION (WIB)',
            '</div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 2. Filter: Mesin, Severity, Rentang Tanggal
# ---------------------------------------------------------------------------
try:
    s_dt, e_dt = get_data_range()
except Exception:
    s_dt = datetime(2026, 11, 1)
    e_dt = datetime(2026, 11, 3, 23, 0)

f_c1, f_c2, f_c3 = st.columns([1.4, 1.1, 1.8])

with f_c1:
    machine_opts = ["Semua Mesin"] + [m["machine_id"] for m in machines]
    sel_machine = st.selectbox(
        "Filter Mesin",
        options=machine_opts,
        format_func=lambda mid: mid if mid == "Semua Mesin" else f"{mid} - {next((m['name'] for m in machines if m['machine_id']==mid), mid)}",
    )

with f_c2:
    sel_severity = st.selectbox(
        "Filter Severity",
        options=["Semua", "high", "medium", "low"],
        format_func=lambda s: s.capitalize() if s != "Semua" else "Semua",
    )

with f_c3:
    date_range = st.date_input(
        "Rentang Tanggal (WIB)",
        value=(s_dt.date(), e_dt.date()),
        min_value=datetime(2020, 1, 1).date(),
        max_value=datetime(2035, 12, 31).date(),
    )

if not isinstance(date_range, (list, tuple)) or len(date_range) != 2:
    st.info("ℹ️ Silakan tentukan tanggal awal dan tanggal akhir.")
    st.stop()

filter_start = datetime.combine(date_range[0], time.min)
filter_end   = datetime.combine(date_range[1], time.max.replace(microsecond=0))

# ---------------------------------------------------------------------------
# 3. Ambil Data Alert dari API
# ---------------------------------------------------------------------------
target_machines = [m["machine_id"] for m in machines] if sel_machine == "Semua Mesin" else [sel_machine]

all_alerts: list[dict] = []
is_mock_flag = False
load_errors: list[str] = []

with st.spinner("Memuat data waste alerts..."):
    for mid in target_machines:
        try:
            res = get_waste_alerts(mid, start=filter_start, end=filter_end)
            alerts = res.get("alerts", [])
            all_alerts.extend(alerts)
            if res.get("is_mock"):
                is_mock_flag = True
        except RuntimeError as exc:
            load_errors.append(f"{mid}: {exc}")
        except Exception as exc:
            load_errors.append(f"{mid}: {exc}")

for err in load_errors:
    st.warning(f"⚠️ Gagal memuat alert: {err}")

if is_mock_flag:
    st.info("🧪 **Data contoh** — Sebagian data ditampilkan sebagai contoh (backend model belum tersedia atau USE_MOCK aktif).", icon="🧪")

# Konversi ke DataFrame
if all_alerts:
    df_alerts = pd.DataFrame(all_alerts)
    df_alerts["timestamp"] = pd.to_datetime(df_alerts["timestamp"])
    if df_alerts["timestamp"].dt.tz is None:
        df_alerts["timestamp"] = df_alerts["timestamp"].dt.tz_localize("UTC")
    df_alerts["timestamp_wib"] = df_alerts["timestamp"].dt.tz_convert("Asia/Jakarta")
    df_alerts["hour_wib"] = df_alerts["timestamp_wib"].dt.hour
    df_alerts["severity_num"] = df_alerts["severity"].map(SEVERITY_NUM).fillna(1)
    df_alerts["severity"] = df_alerts["severity"].str.lower()
else:
    df_alerts = pd.DataFrame(columns=["machine_id", "timestamp", "timestamp_wib", "type", "severity", "note", "hour_wib", "severity_num"])

# Filter severity
if sel_severity != "Semua":
    df_alerts = df_alerts[df_alerts["severity"] == sel_severity]

# ---------------------------------------------------------------------------
# Empty State
# ---------------------------------------------------------------------------
if df_alerts.empty:
    st.markdown("<div style='margin:2rem 0;'></div>", unsafe_allow_html=True)
    st.markdown(
        "".join([
            '<div style="text-align:center; padding:60px 20px; background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px;">',
            '<div style="font-size:2.5rem; margin-bottom:12px;">✅</div>',
            '<div style="font-size:1.1rem; font-weight:700; color:#1F1A17; margin-bottom:8px;">Tidak ada peringatan ditemukan</div>',
            '<div style="font-size:0.9rem; color:#6B6259;">Tidak ada waste alert pada filter mesin, severity, dan rentang tanggal yang dipilih.</div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )
    st.stop()

# ---------------------------------------------------------------------------
# 4. KPI Strip (4 kartu)
# ---------------------------------------------------------------------------
total_alerts = len(df_alerts)
most_severe = df_alerts.loc[df_alerts["severity_num"].idxmax(), "severity"] if not df_alerts.empty else "—"
top_machine  = df_alerts["machine_id"].value_counts().idxmax() if not df_alerts.empty else "—"
top_machine_count = int(df_alerts["machine_id"].value_counts().max()) if not df_alerts.empty else 0
n_types = df_alerts["type"].nunique() if not df_alerts.empty else 0

k1, k2, k3, k4 = st.columns(4)

with k1:
    st.markdown(
        "".join([
            '<div class="kpi-card-velora">',
            '<div class="kpi-label">Total Kasus Alert</div>',
            f'<div><span class="kpi-val">{total_alerts}</span><span class="kpi-unit">kasus</span></div>',
            f'<div class="kpi-sub"><span class="badge-pill-orange">{n_types} Tipe Anomali</span></div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

with k2:
    sev_badge = SEVERITY_BADGE.get(most_severe, f'<span>{most_severe}</span>')
    st.markdown(
        "".join([
            '<div class="kpi-card-velora">',
            '<div class="kpi-label">Severity Tertinggi Ditemukan</div>',
            f'<div style="margin:6px 0;">{sev_badge}</div>',
            f'<div class="kpi-sub" style="color:#6B6259;font-size:12px;">{int((df_alerts["severity"]==most_severe).sum())} kasus severity ini</div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

with k3:
    st.markdown(
        "".join([
            '<div class="kpi-card-velora">',
            '<div class="kpi-label">Mesin Paling Sering Muncul</div>',
            f'<div><span class="kpi-val" style="font-size:1.8rem;">{top_machine}</span></div>',
            f'<div class="kpi-sub"><span class="badge-pill-orange">{top_machine_count} kasus</span></div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

with k4:
    high_count = int((df_alerts["severity"] == "high").sum())
    med_count  = int((df_alerts["severity"] == "medium").sum())
    low_count  = int((df_alerts["severity"] == "low").sum())
    st.markdown(
        "".join([
            '<div class="kpi-card-velora">',
            '<div class="kpi-label">Sebaran Severity</div>',
            f'<div style="display:flex;gap:10px;align-items:center;margin:6px 0;">',
            f'<span style="font-size:12px;color:#E8590C;font-weight:700;">High {high_count}</span>',
            f'<span style="font-size:12px;color:#A07A00;font-weight:700;">Medium {med_count}</span>',
            f'<span style="font-size:12px;color:#16A34A;font-weight:700;">Low {low_count}</span>',
            '</div>',
            f'<div class="kpi-sub" style="color:#6B6259;font-size:12px;">dari {total_alerts} total kasus</div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin:1.2rem 0;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 5. Tabel Alert + Tombol Download CSV
# ---------------------------------------------------------------------------
tbl_hdr, tbl_btn = st.columns([3, 1])
with tbl_hdr:
    st.markdown(
        "".join([
            '<div style="font-weight:800; font-size:1.1rem; color:#1F1A17; margin-bottom:4px;">Daftar Peringatan Pemborosan</div>',
            '<div style="font-size:0.75rem; color:#6B6259; font-weight:600;">Waktu dalam WIB · Semua data dari API /waste-alerts</div>',
        ]),
        unsafe_allow_html=True,
    )

with tbl_btn:
    csv_buf = io.StringIO()
    export_df = df_alerts[["timestamp_wib", "machine_id", "type", "severity", "note"]].copy()
    export_df["timestamp_wib"] = export_df["timestamp_wib"].dt.strftime("%Y-%m-%d %H:%M WIB")
    export_df.to_csv(csv_buf, index=False)
    st.download_button(
        label="⬇ Unduh CSV",
        data=csv_buf.getvalue(),
        file_name=f"waste_alerts_{date_range[0]}_{date_range[1]}.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.markdown("<div style='margin:8px 0;'></div>", unsafe_allow_html=True)

# Render tabel dengan st.dataframe (badge severity via kolom teks biasa)
df_table = df_alerts[["timestamp_wib", "machine_id", "type", "severity", "note"]].copy()
df_table = df_table.rename(columns={
    "timestamp_wib": "Waktu (WIB)",
    "machine_id": "Mesin",
    "type": "Tipe Anomali",
    "severity": "Severity",
    "note": "Rekomendasi / Catatan",
})
df_table["Waktu (WIB)"] = df_table["Waktu (WIB)"].dt.strftime("%d %b %Y, %H:%M WIB")
df_table["Tipe Anomali"] = df_table["Tipe Anomali"].str.replace("_", " ").str.title()
df_table["Severity"] = df_table["Severity"].str.capitalize()
df_table["Rekomendasi / Catatan"] = df_table["Rekomendasi / Catatan"].fillna("—").replace("", "—")
df_table = df_table.sort_values("Waktu (WIB)", ascending=False).reset_index(drop=True)

st.dataframe(
    df_table,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Severity": st.column_config.TextColumn("Severity", width="small"),
    },
)

st.markdown("<div style='margin:1.4rem 0;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 6. Visualisasi: Bar chart per mesin & Bubble chart jam vs jumlah alert
# ---------------------------------------------------------------------------
vis_c1, vis_c2 = st.columns([1.1, 1.5])

# --- Bar chart: Alert per Mesin ---
with vis_c1:
    st.markdown(
        "".join([
            '<div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:18px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.03);">',
            '<div style="font-weight:800; font-size:1rem; color:#1F1A17; margin-bottom:4px;">Alert per Mesin</div>',
            '<div style="font-size:0.75rem; color:#6B6259; margin-bottom:10px;">Jumlah kasus anomali per ID mesin</div>',
        ]),
        unsafe_allow_html=True,
    )

    machine_counts = df_alerts["machine_id"].value_counts().reset_index()
    machine_counts.columns = ["machine_id", "count"]
    machine_counts = machine_counts.sort_values("count", ascending=True)

    # Gradasi warna: sedikit kuning → banyak oranye
    n = len(machine_counts)
    bar_colors = [
        f"rgba(232, 89, 12, {0.4 + 0.6 * (i / max(n - 1, 1))})"
        for i in range(n)
    ]

    fig_bar = go.Figure(
        go.Bar(
            x=machine_counts["count"],
            y=machine_counts["machine_id"],
            orientation="h",
            marker=dict(color=bar_colors, line_width=0),
            hovertemplate="<b>%{y}</b><br>Jumlah Alert: <b>%{x}</b><extra></extra>",
        )
    )
    style_plotly_fig(fig_bar, height=240)
    fig_bar.update_layout(
        margin=dict(l=10, r=20, t=10, b=20),
        showlegend=False,
        xaxis=dict(title="Jumlah Kasus", tickfont=dict(size=12)),
        yaxis=dict(tickfont=dict(size=12)),
    )
    st.plotly_chart(fig_bar, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

# --- Bubble chart: Jam WIB vs Jumlah Alert, ukuran & warna = severity ---
with vis_c2:
    st.markdown(
        "".join([
            '<div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:18px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.03);">',
            '<div style="font-weight:800; font-size:1rem; color:#1F1A17; margin-bottom:2px;">Distribusi Waktu Alert (Jam WIB)</div>',
            '<div style="font-size:0.75rem; color:#6B6259; margin-bottom:10px;">Sumbu X = jam WIB (0-23) · Sumbu Y = jumlah kasus per jam · Ukuran = rata-rata severity</div>',
        ]),
        unsafe_allow_html=True,
    )

    # Agregasi per jam: hitung jumlah alert dan rata-rata severity_num
    hour_agg = (
        df_alerts.groupby("hour_wib", as_index=False)
        .agg(count=("machine_id", "count"), avg_sev=("severity_num", "mean"))
    )
    hour_agg["bubble_size"] = hour_agg["avg_sev"] * 20  # skala visual
    hour_agg["color"] = hour_agg["avg_sev"].apply(
        lambda s: "#E8590C" if s >= 2.5 else ("#F2C230" if s >= 1.5 else "#16A34A")
    )

    fig_bubble = go.Figure()
    for _, row in hour_agg.iterrows():
        fig_bubble.add_trace(
            go.Scatter(
                x=[row["hour_wib"]],
                y=[row["count"]],
                mode="markers",
                marker=dict(
                    size=row["bubble_size"],
                    color=row["color"],
                    opacity=0.7,
                    line=dict(color="rgba(255,255,255,0.6)", width=1.5),
                ),
                name=f"Jam {int(row['hour_wib']):02d}:00",
                hovertemplate=(
                    f"<b>Jam {int(row['hour_wib']):02d}:00 WIB</b><br>"
                    f"Jumlah Alert: <b>{int(row['count'])}</b><br>"
                    f"Rata-rata Severity: <b>{'High' if row['avg_sev']>=2.5 else 'Medium' if row['avg_sev']>=1.5 else 'Low'}</b>"
                    "<extra></extra>"
                ),
            )
        )

    # Legenda severity manual via annotation
    fig_bubble.add_annotation(x=23, y=1.0, text='<span style="font-size:11px;color:#E8590C;">● High</span>', showarrow=False, xanchor="right")
    fig_bubble.add_annotation(x=23, y=0.6, text='<span style="font-size:11px;color:#A07A00;">● Medium</span>', showarrow=False, xanchor="right")
    fig_bubble.add_annotation(x=23, y=0.2, text='<span style="font-size:11px;color:#16A34A;">● Low</span>', showarrow=False, xanchor="right")

    style_plotly_fig(fig_bubble, height=240)
    fig_bubble.update_layout(
        showlegend=False,
        margin=dict(l=10, r=20, t=10, b=20),
        xaxis=dict(title="Jam WIB (0-23)", tickvals=list(range(0, 24, 2)), tickfont=dict(size=12), range=[-1, 24]),
        yaxis=dict(title="Jumlah Kasus", tickfont=dict(size=12)),
    )
    st.plotly_chart(fig_bubble, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='margin:1.4rem 0;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 7. Mini Alert Card: Sebaran per Tipe Alert
# ---------------------------------------------------------------------------
st.markdown(
    "".join([
        '<div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:18px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.03);">',
        '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">',
        '<div style="font-weight:800; font-size:1rem; color:#1F1A17;">Sebaran per Tipe Anomali</div>',
        f'<span class="badge-pill-orange">{total_alerts} Total Kasus</span>',
        '</div>',
    ]),
    unsafe_allow_html=True,
)

type_counts = df_alerts["type"].value_counts()
type_cols_parts = []
for atype, count in type_counts.items():
    readable = str(atype).replace("_", " ").title()
    pct = count / total_alerts * 100 if total_alerts else 0
    # Bar mini per tipe
    type_cols_parts.append(
        "".join([
            '<div style="flex:1; min-width:120px; padding:10px 12px; background:#FAF4E8; border-radius:12px; text-align:center;">',
            f'<div style="font-size:1.3rem; font-weight:800; color:#E8590C; margin-bottom:4px;">{count}</div>',
            f'<div style="font-size:0.72rem; font-weight:700; color:#1F1A17; margin-bottom:4px;">{readable}</div>',
            f'<div style="background:#EFE5D6; height:5px; border-radius:3px; overflow:hidden;">',
            f'<div style="background:#E8590C; width:{min(pct,100):.0f}%; height:100%; border-radius:3px;"></div>',
            '</div>',
            f'<div style="font-size:0.68rem; color:#6B6259; margin-top:3px;">{pct:.1f}%</div>',
            '</div>',
        ])
    )

type_grid_html = "".join([
    '<div style="display:flex; flex-wrap:wrap; gap:10px;">',
    "".join(type_cols_parts),
    '</div>',
    '</div>',
])
st.markdown(type_grid_html, unsafe_allow_html=True)

# Footer
st.markdown(
    "".join([
        '<div style="text-align:right; font-size:12px; color:#6B6259; margin-top:20px;">',
        f'Filter: <b>{"Semua Mesin" if sel_machine=="Semua Mesin" else sel_machine}</b> · ',
        f'Severity: <b>{"Semua" if sel_severity=="Semua" else sel_severity.capitalize()}</b> · ',
        f'Periode: <b>{date_range[0]} – {date_range[1]} (WIB)</b>',
        '</div>',
    ]),
    unsafe_allow_html=True,
)
