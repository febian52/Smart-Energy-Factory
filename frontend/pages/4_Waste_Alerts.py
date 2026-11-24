import sys
from pathlib import Path
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
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

try:
    st.set_page_config(
        page_title="Waste Alerts - Smart Factory Energy Management",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception:
    pass

apply_theme()

WIB_TZ = ZoneInfo("Asia/Jakarta")
UTC_TZ = ZoneInfo("UTC")

# ---------------------------------------------------------------------------
# Helper: Badge severity → HTML pill
# ---------------------------------------------------------------------------
SEVERITY_BADGE = {
    "low":    '<span style="display:inline-flex;align-items:center;gap:5px;background:rgba(22,163,74,0.12);color:#16A34A;border-radius:20px;padding:3px 10px;font-size:0.75rem;font-weight:700;">Low</span>',
    "medium": '<span style="display:inline-flex;align-items:center;gap:5px;background:rgba(242,194,48,0.18);color:#A07A00;border-radius:20px;padding:3px 10px;font-size:0.75rem;font-weight:700;">Medium</span>',
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
# Header Halaman
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div style="margin-bottom: 20px;">
        <div style="font-size: 0.78rem; font-weight: 700; color: #E8590C; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 4px;">
            // ANOMALY & WASTE DETECTION SYSTEM
        </div>
        <h1 style="color: #1F1A17; font-size: 2.2rem; font-weight: 800; margin: 0 0 6px 0; letter-spacing: -0.03em;">
            Peringatan Pemborosan Energi (Waste Alerts)
        </h1>
        <p style="color: #6B6259; font-size: 0.95rem; margin: 0; max-width: 850px; line-height: 1.5;">
            Deteksi otomatis pemborosan konsumsi daya listrik berdasarkan model anomali operasional:
            kondisi tanpa beban (Idle Waste), beban berlebih di atas rated power, dan anomali pola shift kerja.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# 2. Filter: Mesin, Severity, Rentang Tanggal (Default 7 Hari Terakhir WIB)
# ---------------------------------------------------------------------------
try:
    s_dt_raw, e_dt_raw = get_data_range()
    if e_dt_raw.tzinfo is None:
        e_dt_wib = e_dt_raw.replace(tzinfo=UTC_TZ).astimezone(WIB_TZ)
    else:
        e_dt_wib = e_dt_raw.astimezone(WIB_TZ)

    default_end_date = e_dt_wib.date()
    default_start_date = default_end_date - timedelta(days=6)
except Exception:
    default_start_date = datetime(2026, 6, 24).date()
    default_end_date = datetime(2026, 6, 30).date()

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
        value=(default_start_date, default_end_date),
        min_value=datetime(2020, 1, 1).date(),
        max_value=datetime(2035, 12, 31).date(),
    )

if not isinstance(date_range, (list, tuple)) or len(date_range) != 2:
    st.info("ℹ️ Silakan tentukan tanggal awal dan tanggal akhir pada filter rentang tanggal.")
    st.stop()

sel_d_start, sel_d_end = date_range[0], date_range[1]

# Konversi rentang tanggal WIB ke rentang UTC untuk query backend API
wib_start = datetime.combine(sel_d_start, time.min, tzinfo=WIB_TZ)
wib_end   = datetime.combine(sel_d_end, time.max.replace(microsecond=0), tzinfo=WIB_TZ)
utc_start = wib_start.astimezone(UTC_TZ).replace(tzinfo=None)
utc_end   = wib_end.astimezone(UTC_TZ).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# 3. Ambil Data Alert dari API (dengan Cache & Timeout 45s per Request)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def fetch_waste_alerts_cached(mid: str, s_iso: str, e_iso: str) -> dict:
    s = datetime.fromisoformat(s_iso) if s_iso else None
    e = datetime.fromisoformat(e_iso) if e_iso else None
    return get_waste_alerts(mid, start=s, end=e, timeout=45)


target_machines = [m["machine_id"] for m in machines] if sel_machine == "Semua Mesin" else [sel_machine]

all_alerts: list[dict] = []
is_mock_flag = False
failed_machines: list[str] = []
success_machines: list[str] = []

with st.spinner("Memuat data peringatan pemborosan (waste alerts)..."):
    for mid in target_machines:
        try:
            res = fetch_waste_alerts_cached(mid, utc_start.isoformat(), utc_end.isoformat())
            alerts = res.get("alerts", [])
            all_alerts.extend(alerts)
            success_machines.append(mid)
            if res.get("is_mock"):
                is_mock_flag = True
        except RuntimeError as exc:
            failed_machines.append(f"{mid} ({exc})")
        except Exception as exc:
            failed_machines.append(f"{mid} ({exc})")

# Tampilkan SATU banner gabungan jika ada sebagian mesin yang gagal
if failed_machines:
    st.warning(
        f"⚠️ **Sebagian data pemborosan gagal dimuat:** {', '.join(failed_machines)}. "
        f"Menampilkan data parsial dari mesin yang berhasil ({len(success_machines)}/{len(target_machines)} mesin).",
        icon="⚠️",
    )

if is_mock_flag:
    st.info("🧪 **Data contoh** — Sebagian data ditampilkan sebagai contoh (backend model belum tersedia atau USE_MOCK aktif).", icon="🧪")

# Konversi ke DataFrame
if all_alerts:
    df_raw = pd.DataFrame(all_alerts)
    df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
    if df_raw["timestamp"].dt.tz is None:
        df_raw["timestamp"] = df_raw["timestamp"].dt.tz_localize("UTC")
    df_raw["timestamp_wib"] = df_raw["timestamp"].dt.tz_convert("Asia/Jakarta")

    # Filter ketat berdasarkan rentang tanggal WIB yang dipilih pengguna
    df_alerts = df_raw[
        (df_raw["timestamp_wib"].dt.date >= sel_d_start) &
        (df_raw["timestamp_wib"].dt.date <= sel_d_end)
    ].copy()

    df_alerts["hour_wib"] = df_alerts["timestamp_wib"].dt.hour
    df_alerts["severity_num"] = df_alerts["severity"].map(SEVERITY_NUM).fillna(1)
    df_alerts["severity"] = df_alerts["severity"].str.lower()
else:
    df_alerts = pd.DataFrame(columns=["machine_id", "timestamp", "timestamp_wib", "type", "severity", "note", "hour_wib", "severity_num"])

# Filter tingkat keparahan (Severity)
if sel_severity != "Semua" and not df_alerts.empty:
    df_alerts = df_alerts[df_alerts["severity"] == sel_severity]

is_partial_data = len(failed_machines) > 0

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
# 4. KPI Strip Ringkas (Tinggi Kartu Seragam)
# ---------------------------------------------------------------------------
total_alerts = len(df_alerts)

if is_partial_data:
    kpi_sub_total = f'<span style="background:rgba(232,89,12,0.12); color:#E8590C; font-size:12px; font-weight:700; border-radius:12px; padding:2px 8px;">⚠️ Data Parsial ({len(success_machines)}/{len(target_machines)} Mesin)</span>'
else:
    kpi_sub_total = '<span class="badge-pill-green">Data Lengkap</span>'

k1, k2, k3, k4 = st.columns(4)

with k1:
    st.markdown(
        "".join([
            '<div class="kpi-card-velora" style="height:100%;">',
            '<div class="kpi-label">Total Kasus Terdeteksi</div>',
            f'<div><span class="kpi-val">{total_alerts:,}</span><span class="kpi-unit">Kasus</span></div>',
            f'<div class="kpi-sub">{kpi_sub_total}</div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

with k2:
    if not df_alerts.empty:
        max_sev_num = int(df_alerts["severity_num"].max())
        max_sev_str = {3: "High", 2: "Medium", 1: "Low"}.get(max_sev_num, "—")
        max_sev_color = {3: "#E8590C", 2: "#F2C230", 1: "#16A34A"}.get(max_sev_num, "#6B6259")
    else:
        max_sev_str, max_sev_color = "—", "#6B6259"

    st.markdown(
        "".join([
            '<div class="kpi-card-velora" style="height:100%;">',
            '<div class="kpi-label">Severity Tertinggi</div>',
            f'<div><span class="kpi-val" style="color:{max_sev_color};">{max_sev_str}</span></div>',
            '<div class="kpi-sub"><span style="color:#6B6259; font-size:12px; font-weight:600;">Status Risiko</span></div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

with k3:
    if not df_alerts.empty:
        top_mach = df_alerts["machine_id"].value_counts().index[0]
        top_mach_count = int(df_alerts["machine_id"].value_counts().iloc[0])
    else:
        top_mach, top_mach_count = "—", 0

    st.markdown(
        "".join([
            '<div class="kpi-card-velora" style="height:100%;">',
            '<div class="kpi-label">Mesin Paling Boros</div>',
            f'<div><span class="kpi-val">{top_mach}</span></div>',
            f'<div class="kpi-sub"><span class="badge-pill-orange">{top_mach_count:,} Kejadian</span></div>',
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
            '<div class="kpi-card-velora" style="height:100%;">',
            '<div class="kpi-label">Sebaran Severity</div>',
            '<div style="display:flex;gap:10px;align-items:center;margin:6px 0;">',
            f'<span style="font-size:12px;color:#E8590C;font-weight:700;">High {high_count:,}</span>',
            f'<span style="font-size:12px;color:#A07A00;font-weight:700;">Medium {med_count:,}</span>',
            f'<span style="font-size:12px;color:#16A34A;font-weight:700;">Low {low_count:,}</span>',
            '</div>',
            f'<div class="kpi-sub" style="color:#6B6259;font-size:12px;">dari {total_alerts:,} total kasus</div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin:1.2rem 0;'></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 5. Tabel Alert HTML (Max 100 Baris) + Tombol Download CSV (Full Data)
# ---------------------------------------------------------------------------
tbl_hdr, tbl_btn = st.columns([3, 1])
with tbl_hdr:
    st.markdown(
        "".join([
            '<div style="font-weight:800; font-size:1.1rem; color:#1F1A17; margin-bottom:4px;">Daftar Peringatan Pemborosan</div>',
            '<div style="font-size:0.75rem; color:#6B6259; font-weight:600;">Waktu dalam WIB · Menampilkan hingga 100 anomali terbaru · Teks rekomendasi penuh</div>',
        ]),
        unsafe_allow_html=True,
    )

with tbl_btn:
    csv_buf = io.StringIO()
    export_df = df_alerts[["timestamp_wib", "machine_id", "type", "severity", "note"]].copy()
    export_df["timestamp_wib"] = export_df["timestamp_wib"].dt.strftime("%Y-%m-%d %H:%M WIB")
    export_df.to_csv(csv_buf, index=False)
    st.download_button(
        label="⬇ Unduh Semua CSV",
        data=csv_buf.getvalue(),
        file_name=f"waste_alerts_{sel_d_start}_{sel_d_end}.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.markdown("<div style='margin:8px 0;'></div>", unsafe_allow_html=True)

# Urutkan kronologis terbalik (terbaru di atas)
df_table = df_alerts[["timestamp_wib", "machine_id", "type", "severity", "note"]].copy()
df_table = df_table.sort_values("timestamp_wib", ascending=False).reset_index(drop=True)
df_table["timestamp_wib_str"] = df_table["timestamp_wib"].dt.strftime("%d %b %Y, %H:%M WIB")
df_table["type_title"] = df_table["type"].str.replace("_", " ").str.title()
df_table["note_clean"] = df_table["note"].fillna("—").replace("", "—")

# Ambil maksimal 100 baris terbaru untuk render tabel HTML yang cepat dan responsif
display_rows = df_table.head(100)

SEV_PILL = {
    "high": '<span style="display:inline-block; padding:3px 10px; border-radius:12px; font-weight:700; font-size:12px; background:rgba(232,89,12,0.12); color:#E8590C;">High</span>',
    "medium": '<span style="display:inline-block; padding:3px 10px; border-radius:12px; font-weight:700; font-size:12px; background:rgba(242,194,48,0.18); color:#A07A00;">Medium</span>',
    "low": '<span style="display:inline-block; padding:3px 10px; border-radius:12px; font-weight:700; font-size:12px; background:rgba(22,163,74,0.12); color:#16A34A;">Low</span>',
}

tbody_parts = []
for idx, row in display_rows.iterrows():
    sev_key = str(row["severity"]).lower()
    pill = SEV_PILL.get(sev_key, f'<span style="font-weight:700;">{row["severity"]}</span>')
    bg_row = "#FFFFFF" if idx % 2 == 0 else "#FAF7F2"
    tbody_parts.append(
        f'<tr style="background:{bg_row}; border-bottom:1px solid #EFE5D6;">'
        f'<td style="padding:10px 14px; white-space:nowrap; font-weight:600; color:#1F1A17; vertical-align:top;">{row["timestamp_wib_str"]}</td>'
        f'<td style="padding:10px 12px; font-weight:700; color:#E8590C; vertical-align:top;">{row["machine_id"]}</td>'
        f'<td style="padding:10px 14px; color:#1F1A17; font-weight:600; vertical-align:top; white-space:nowrap;">{row["type_title"]}</td>'
        f'<td style="padding:10px 12px; vertical-align:top;">{pill}</td>'
        f'<td style="padding:10px 16px; color:#4A4036; line-height:1.45; word-break:break-word; vertical-align:top;">{row["note_clean"]}</td>'
        f'</tr>'
    )

tbody_html = "".join(tbody_parts)
table_html = "".join([
    '<div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.03);">',
    '<div style="overflow-x:auto;">',
    '<table style="width:100%; border-collapse:collapse; font-size:13px; text-align:left;">',
    '<thead>',
    '<tr style="background:#FAF4E8; border-bottom:1.5px solid #EAE0D0; color:#6B6259; font-size:12px; text-transform:uppercase; letter-spacing:0.04em;">',
    '<th style="padding:12px 14px; width:170px;">Waktu (WIB)</th>',
    '<th style="padding:12px 12px; width:75px;">Mesin</th>',
    '<th style="padding:12px 14px; width:190px;">Tipe Pemborosan</th>',
    '<th style="padding:12px 12px; width:110px;">Severity</th>',
    '<th style="padding:12px 16px;">Rekomendasi Tindakan</th>',
    '</tr>',
    '</thead>',
    '<tbody>',
    tbody_html,
    '</tbody>',
    '</table>',
    '</div>',
    '</div>',
])
st.markdown(table_html, unsafe_allow_html=True)

if len(df_table) > 100:
    st.caption(f"Menampilkan 100 dari total {len(df_table):,} kasus terbaru. Gunakan tombol 'Unduh Semua CSV' di atas untuk mengunduh seluruh {len(df_table):,} data terfilter.")

st.markdown("<div style='margin:1.4rem 0;'></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 6. Visualisasi: Bar chart per mesin & Bubble chart jam vs jumlah alert
# ---------------------------------------------------------------------------
vis_c1, vis_c2 = st.columns([1.1, 1.5])

# --- Bar chart: Alert per Mesin ---
with vis_c1:
    with st.container(border=True):
        st.markdown(
            "".join([
                '<div style="font-weight:800; font-size:1rem; color:#1F1A17; margin-bottom:4px;">Alert per Mesin</div>',
                '<div style="font-size:0.75rem; color:#6B6259; margin-bottom:10px;">Jumlah kasus anomali per ID mesin</div>',
            ]),
            unsafe_allow_html=True,
        )

        mach_counts = df_alerts.groupby("machine_id").size().reset_index(name="count").sort_values("count", ascending=True)

        fig_bar = go.Figure(
            go.Bar(
                x=mach_counts["count"],
                y=mach_counts["machine_id"],
                orientation="h",
                marker=dict(
                    color=mach_counts["count"],
                    colorscale=[[0.0, "#FCD34D"], [1.0, "#E8590C"]],
                    showscale=False,
                    cornerradius=6,
                ),
                text=mach_counts["count"],
                textposition="outside",
                textfont=dict(size=11, color="#1F1A17", family="Plus Jakarta Sans"),
                hovertemplate="<b>Mesin %{y}</b><br>Total Alert: %{x:,} kasus<extra></extra>",
            )
        )
        style_plotly_fig(fig_bar, height=270)
        fig_bar.update_layout(
            margin=dict(l=10, r=35, t=10, b=10),
            xaxis=dict(title="Jumlah Kasus", showgrid=True, zeroline=False),
            yaxis=dict(title="", tickfont=dict(size=11, color="#1F1A17"), dtick=1),
        )
        st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

# --- Bubble Chart: Jam WIB vs Jumlah Alert ---
with vis_c2:
    with st.container(border=True):
        st.markdown(
            "".join([
                '<div style="font-weight:800; font-size:1rem; color:#1F1A17; margin-bottom:4px;">Distribusi Jam Kejadian (WIB)</div>',
                '<div style="font-size:0.75rem; color:#6B6259; margin-bottom:10px;">Jam operasional terjadinya anomali (ukuran bubble = rata-rata keparahan)</div>',
            ]),
            unsafe_allow_html=True,
        )

        hourly_grp = (
            df_alerts.groupby("hour_wib")
            .agg(count=("severity_num", "count"), avg_sev=("severity_num", "mean"))
            .reset_index()
        )

        all_hours = pd.DataFrame({"hour_wib": list(range(24))})
        hourly_grp = all_hours.merge(hourly_grp, on="hour_wib", how="left").fillna({"count": 0, "avg_sev": 1})

        fig_bubble = go.Figure(
            go.Scatter(
                x=hourly_grp["hour_wib"],
                y=hourly_grp["count"],
                mode="markers+lines",
                line=dict(color="rgba(232, 89, 12, 0.3)", width=1.5, dash="dot"),
                marker=dict(
                    size=hourly_grp["count"].apply(lambda c: max(8, min(36, 8 + c * 0.4))),
                    color=hourly_grp["avg_sev"],
                    colorscale=[[0.0, "#16A34A"], [0.5, "#F2C230"], [1.0, "#E8590C"]],
                    showscale=False,
                    line=dict(color="#FFFFFF", width=1.5),
                ),
                hovertemplate="<b>Jam %{x:02d}:00 WIB</b><br>Jumlah Alert: %{y:,}<br>Avg Severity: %{marker.color:.1f}/3<extra></extra>",
            )
        )
        style_plotly_fig(fig_bubble, height=270)
        fig_bubble.update_layout(
            margin=dict(l=10, r=10, t=10, b=25),
            xaxis=dict(
                title="Jam WIB (00–23)",
                tickmode="linear",
                tick0=0,
                dtick=2,
                tickfont=dict(size=11),
            ),
            yaxis=dict(title="Jumlah Kasus", showgrid=True),
        )
        st.plotly_chart(fig_bubble, use_container_width=True, config={"displayModeBar": False})

st.markdown("<div style='margin:1.4rem 0;'></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 7. Mini Alert Cards per Tipe
# ---------------------------------------------------------------------------
st.markdown(
    '<div style="font-weight:800; font-size:1.1rem; color:#1F1A17; margin-bottom:12px;">Rincian Berdasarkan Kategori Pemborosan</div>',
    unsafe_allow_html=True,
)

type_counts = df_alerts["type"].value_counts().to_dict()

TYPE_META = {
    "idle_power_waste": {
        "title": "Idle Power Waste",
        "desc": "Mesin dalam kondisi standby (idle) namun mengonsumsi daya listrik di atas ambang batas toleransi tanpa ada aktivitas produksi aktif.",
        "icon": "⏳",
        "border_color": "#F2C230",
    },
    "over_capacity_load": {
        "title": "Beban Berlebih (Overcapacity)",
        "desc": "Beban daya listrik mesin melampaui rated power kapasitas nominal, berisiko menyebabkan degradasi komponen mesin dan trip breaker.",
        "icon": "⚡",
        "border_color": "#E8590C",
    },
    "peak_hour_surge": {
        "title": "Lonjakan Jam Puncak",
        "desc": "Lonjakan konsumsi energi tinggi pada jam beban puncak tarif listrik pabrik (peak hours) yang dapat meningkatkan tagihan biaya listrik.",
        "icon": "📈",
        "border_color": "#E8590C",
    },
    "running_no_production": {
        "title": "Running Tanpa Produksi",
        "desc": "Mesin beroperasi dalam status running namun tidak ada output hasil kerja yang terdata pada jadwal shift berjalan.",
        "icon": "⚙️",
        "border_color": "#F2C230",
    },
}

all_types = list(TYPE_META.keys())
card_cols = st.columns(len(all_types))

for i, atype in enumerate(all_types):
    meta = TYPE_META[atype]
    cnt = type_counts.get(atype, 0)
    pct = (cnt / total_alerts * 100) if total_alerts > 0 else 0.0

    with card_cols[i]:
        st.markdown(
            "".join([
                f'<div style="background:#FFFFFF; border:1px solid #EFE5D6; border-top:3px solid {meta["border_color"]}; border-radius:16px; padding:16px 18px; box-shadow:0 2px 8px rgba(0,0,0,0.03); height:100%;">',
                f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">',
                f'<span style="font-size:1.4rem;">{meta["icon"]}</span>',
                f'<span class="badge-pill-orange">{cnt:,} Kasus</span>',
                '</div>',
                f'<div style="font-weight:700; font-size:0.92rem; color:#1F1A17; margin-bottom:6px;">{meta["title"]}</div>',
                f'<div style="font-size:0.75rem; color:#6B6259; line-height:1.4; margin-bottom:12px;">{meta["desc"]}</div>',
                f'<div style="display:flex; justify-content:space-between; font-size:11px; font-weight:600; color:#8C827A; margin-bottom:3px;">',
                '<span>Proporsi Kasus</span>',
                f'<span>{pct:.1f}%</span>',
                '</div>',
                f'<div style="background:#F2ECE2; height:5px; border-radius:3px; overflow:hidden;">',
                f'<div style="background:{meta["border_color"]}; width:{pct:.1f}%; height:100%; border-radius:3px;"></div>',
                '</div>',
                '</div>',
            ]),
            unsafe_allow_html=True,
        )
