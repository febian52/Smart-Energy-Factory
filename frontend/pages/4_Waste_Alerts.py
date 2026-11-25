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
    from frontend.ui import apply_theme, style_plotly_fig, create_type_donut, format_id_num
except ImportError:
    from api_client import get_machines, get_waste_alerts, get_data_range
    from ui import apply_theme, style_plotly_fig, create_type_donut, format_id_num

try:
    st.set_page_config(
        page_title="Waste Alerts - Smart Energy Factory",
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
# Helper: Badge severity
# ---------------------------------------------------------------------------
SEVERITY_BADGE = {
    "low": '<span class="badge-pill-green">Low</span>',
    "medium": '<span class="badge-pill-amber">Medium</span>',
    "high": '<span class="badge-pill-red">High</span>',
}
SEVERITY_NUM = {"low": 1, "medium": 2, "high": 3}


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
    <div style="margin-bottom: 20px; padding-bottom: 12px; border-bottom: 1px solid #E5E8EF;">
        <h1 style="color: #111827; font-size: 1.55rem; font-weight: 700; margin: 0 0 4px 0; letter-spacing: -0.02em;">
            Peringatan Pemborosan Energi (Waste Alerts)
        </h1>
        <p style="color: #6B7280; font-size: 0.88rem; margin: 0; max-width: 850px; line-height: 1.5;">
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

# Konversi ke DataFrame sebelum render filter severity dinamis
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

    df_alerts["severity"] = df_alerts["severity"].astype(str).str.lower()
    df_alerts["hour_wib"] = df_alerts["timestamp_wib"].dt.hour
    df_alerts["severity_num"] = df_alerts["severity"].map(SEVERITY_NUM).fillna(1)
else:
    df_alerts = pd.DataFrame(columns=["machine_id", "timestamp", "timestamp_wib", "type", "severity", "note", "hour_wib", "severity_num"])

# Opsi Filter Severity dibentuk dinamis dari nilai yang ada di data API
if not df_alerts.empty:
    available_severities = sorted(
        df_alerts["severity"].dropna().unique().tolist(),
        key=lambda s: SEVERITY_NUM.get(s, 0),
        reverse=True,
    )
else:
    available_severities = []

with f_c2:
    sel_severity = st.selectbox(
        "Filter Severity",
        options=["Semua"] + available_severities,
        format_func=lambda s: s.capitalize() if s != "Semua" else "Semua",
    )

# Tampilkan SATU banner gabungan jika ada sebagian mesin yang gagal
if failed_machines:
    st.warning(
        f"⚠️ **Sebagian data pemborosan gagal dimuat:** {', '.join(failed_machines)}. "
        f"Menampilkan data parsial dari mesin yang berhasil ({len(success_machines)}/{len(target_machines)} mesin).",
        icon="⚠️",
    )

if is_mock_flag:
    st.info("🧪 **Data contoh** — Sebagian data ditampilkan sebagai contoh (backend model belum tersedia atau USE_MOCK aktif).", icon="🧪")

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
            '<div style="text-align:center; padding:60px 20px; background:#FFFFFF; border:1px solid #E5E8EF; border-radius:14px;">',
            '<div style="font-size:2.5rem; margin-bottom:12px;">✅</div>',
            '<div style="font-size:1.1rem; font-weight:700; color:#111827; margin-bottom:8px;">Tidak ada peringatan ditemukan</div>',
            '<div style="font-size:0.88rem; color:#6B7280;">Tidak ada waste alert pada filter mesin, severity, dan rentang tanggal yang dipilih.</div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )
    st.stop()


# ---------------------------------------------------------------------------
# 4. Tab: Alert Aktif & Analisis
# ---------------------------------------------------------------------------
tab_aktif, tab_analisis = st.tabs(["Alert Aktif", "Analisis"])

with tab_aktif:
    # KPI Strip Ringkas
    total_alerts = len(df_alerts)

    if is_partial_data:
        kpi_sub_total = f'<span class="badge-pill-amber">⚠️ Parsial ({len(success_machines)}/{len(target_machines)} Mesin)</span>'
    else:
        kpi_sub_total = '<span class="badge-pill-green">Data Lengkap</span>'

    k1, k2, k3, k4 = st.columns(4)

    with k1:
        st.markdown(
            "".join([
                '<div class="kpi-card" style="height:100%;">',
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
            max_badge_cls = {3: "badge-pill-red", 2: "badge-pill-amber", 1: "badge-pill-green"}.get(max_sev_num, "badge-pill-grey")
        else:
            max_sev_str, max_badge_cls = "—", "badge-pill-grey"

        st.markdown(
            "".join([
                '<div class="kpi-card" style="height:100%;">',
                '<div class="kpi-label">Severity Tertinggi</div>',
                f'<div><span class="kpi-val">{max_sev_str}</span></div>',
                f'<div class="kpi-sub"><span class="{max_badge_cls}">Tingkat Risiko</span></div>',
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
                '<div class="kpi-card" style="height:100%;">',
                '<div class="kpi-label">Mesin Paling Sering Alert</div>',
                f'<div><span class="kpi-val">{top_mach}</span></div>',
                f'<div class="kpi-sub"><span class="badge-pill-amber">{format_id_num(top_mach_count, 0)} Kejadian</span></div>',
                '</div>',
            ]),
            unsafe_allow_html=True,
        )

    with k4:
        sev_counts = df_alerts["severity"].value_counts().to_dict()
        sev_order = ["high", "medium", "low"] + [
            s for s in sorted(sev_counts.keys()) if s not in ("high", "medium", "low")
        ]
        sev_cls_map = {
            "high": "badge-pill-red",
            "medium": "badge-pill-amber",
            "low": "badge-pill-green",
        }
        sev_pills = []
        for s in sev_order:
            if s in sev_counts:
                cls = sev_cls_map.get(s, "badge-pill-grey")
                label = "Med" if s == "medium" else s.title()
                sev_pills.append(f'<span class="{cls}">{label} {format_id_num(sev_counts[s], 0)}</span>')
        if not sev_pills:
            sev_pills.append('<span class="badge-pill-grey">—</span>')

        st.markdown(
            "".join([
                '<div class="kpi-card" style="height:100%;">',
                '<div class="kpi-label">Sebaran Severity</div>',
                '<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:6px 0;">',
                "".join(sev_pills),
                '</div>',
                f'<div class="kpi-sub">Total {format_id_num(total_alerts, 0)} kasus</div>',
                '</div>',
            ]),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin:1.5rem 0 1rem 0;'></div>", unsafe_allow_html=True)

    # Tabel Alert HTML (Max 100 Baris) + Unduh CSV
    tbl_hdr, tbl_btn = st.columns([3, 1])
    with tbl_hdr:
        st.markdown(
            "".join([
                '<div style="font-weight:700; font-size:1.05rem; color:#111827; margin-bottom:2px;">Daftar Peringatan Pemborosan</div>',
                '<div style="font-size:0.8rem; color:#6B7280;">Waktu dalam WIB · Menampilkan hingga 100 anomali terbaru · Teks rekomendasi penuh</div>',
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

    # Ambil maksimal 100 baris terbaru
    display_rows = df_table.head(100)

    tbody_parts = []
    for idx, row in display_rows.iterrows():
        sev_key = str(row["severity"]).lower()
        pill = SEVERITY_BADGE.get(sev_key, f'<span class="badge-pill-grey">{row["severity"]}</span>')
        tbody_parts.append(
            f'<tr>'
            f'<td style="white-space:nowrap; font-weight:600; color:#111827; vertical-align:top;">{row["timestamp_wib_str"]}</td>'
            f'<td style="font-weight:700; color:#1D6FF2; vertical-align:top;">{row["machine_id"]}</td>'
            f'<td style="color:#111827; font-weight:500; vertical-align:top; white-space:nowrap;">{row["type_title"]}</td>'
            f'<td style="vertical-align:top;">{pill}</td>'
            f'<td style="color:#4B5563; line-height:1.45; word-break:break-word; vertical-align:top;">{row["note_clean"]}</td>'
            f'</tr>'
        )

    tbody_html = "".join(tbody_parts)
    table_html = "".join([
        '<div class="data-table-container">',
        '<div style="overflow-x:auto;">',
        '<table class="data-table">',
        '<thead>',
        '<tr>',
        '<th style="width:170px;">Waktu (WIB)</th>',
        '<th style="width:75px;">Mesin</th>',
        '<th style="width:190px;">Tipe Pemborosan</th>',
        '<th style="width:110px;">Severity</th>',
        '<th>Rekomendasi Tindakan</th>',
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
        st.caption(f"Menampilkan 100 dari total {format_id_num(len(df_table), 0)} kasus terbaru. Gunakan tombol 'Unduh Semua CSV' di atas untuk mengunduh seluruh {format_id_num(len(df_table), 0)} data terfilter.")

    st.caption("Titik anomali dideteksi Isolation Forest; tipe, severity, dan rekomendasi ditentukan aturan.")


with tab_analisis:
    # ---------------------------------------------------------------------------
    # Visualisasi: Bar Chart per Mesin & Distribusi Jam WIB
    # ---------------------------------------------------------------------------
    vis_c1, vis_c2 = st.columns([1.1, 1.5])

    # --- Bar chart: Alert per Mesin ---
    with vis_c1:
        with st.container(border=True):
            st.markdown(
                "".join([
                    '<div style="font-weight:700; font-size:0.95rem; color:#111827; margin-bottom:2px;">Alert per Mesin</div>',
                    '<div style="font-size:0.75rem; color:#6B7280; margin-bottom:8px;">Jumlah kasus anomali per ID mesin</div>',
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
                        color="#1D6FF2",
                        cornerradius=6,
                    ),
                    text=mach_counts["count"],
                    textposition="outside",
                    textfont=dict(size=11, color="#111827", family="Inter, sans-serif"),
                    hovertemplate="<b>Mesin %{y}</b><br>Total Alert: %{x:,} kasus<extra></extra>",
                )
            )
            style_plotly_fig(fig_bar, height=270)
            fig_bar.update_layout(
                margin=dict(l=10, r=35, t=10, b=10),
                xaxis=dict(title="Jumlah Kasus", showgrid=True, zeroline=False),
                yaxis=dict(title="", tickfont=dict(size=11, color="#111827"), dtick=1),
            )
            st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

    # --- Bubble Chart: Jam WIB vs Jumlah Alert ---
    with vis_c2:
        with st.container(border=True):
            st.markdown(
                "".join([
                    '<div style="font-weight:700; font-size:0.95rem; color:#111827; margin-bottom:2px;">Distribusi Jam Kejadian (WIB)</div>',
                    '<div style="font-size:0.75rem; color:#6B7280; margin-bottom:8px;">Jam operasional terjadinya anomali (ukuran bubble = keparahan rata-rata)</div>',
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
                    line=dict(color="rgba(29, 111, 242, 0.25)", width=1.5, dash="dot"),
                    marker=dict(
                        size=hourly_grp["count"].apply(lambda c: max(8, min(34, 8 + c * 0.4))),
                        color=hourly_grp["avg_sev"],
                        colorscale=[[0.0, "#16A34A"], [0.5, "#F59E0B"], [1.0, "#EF4444"]],
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

    st.markdown("<div style='margin:1rem 0;'></div>", unsafe_allow_html=True)

    # ---------------------------------------------------------------------------
    # Donut Kategori & Rincian Kartu Berdasarkan Kategori Pemborosan
    # ---------------------------------------------------------------------------
    type_counts = df_alerts["type"].value_counts().to_dict()

    d_col1, d_col2 = st.columns([1.1, 1.9])

    with d_col1:
        with st.container(border=True):
            st.markdown(
                "".join([
                    '<div style="font-weight:700; font-size:0.95rem; color:#111827; margin-bottom:2px;">Sebaran Tipe Anomali</div>',
                    '<div style="font-size:0.75rem; color:#6B7280; margin-bottom:8px;">Proporsi kategori anomali terdeteksi</div>',
                ]),
                unsafe_allow_html=True,
            )
            fig_type_donut = create_type_donut(type_counts, height=255)
            st.plotly_chart(fig_type_donut, use_container_width=True, config={"displayModeBar": False})

    with d_col2:
        TYPE_META = {
            "idle_power_waste": {
                "title": "Idle Power Waste",
                "desc": "Mesin standby (idle) namun menyerap daya di atas toleransi tanpa proses produksi.",
                "color": "#F59E0B",
            },
            "over_capacity_load": {
                "title": "Beban Berlebih (Overcapacity)",
                "desc": "Beban melampaui kapasitas nominal rated power, risiko degradasi atau trip.",
                "color": "#EF4444",
            },
            "peak_hour_surge": {
                "title": "Lonjakan Jam Puncak",
                "desc": "Lonjakan konsumsi daya tinggi pada interval jam beban puncak tarif pabrik.",
                "color": "#1D6FF2",
            },
            "running_no_production": {
                "title": "Running Tanpa Produksi",
                "desc": "Mesin aktif running tanpa ada pencatatan hasil kerja pada shift kerja berjalan.",
                "color": "#6366F1",
            },
        }
        FALLBACK_COLORS = ["#1D6FF2", "#F59E0B", "#EF4444", "#6366F1", "#16A34A", "#0EA5E9"]

        dynamic_types = sorted(type_counts.keys(), key=lambda t: -type_counts[t])
        for row_idx in range(0, len(dynamic_types), 2):
            pair = dynamic_types[row_idx : row_idx + 2]
            cols = st.columns(2)
            for col_idx, atype in enumerate(pair):
                meta = TYPE_META.get(
                    atype,
                    {
                        "title": atype.replace("_", " ").title(),
                        "desc": "Kategori anomali konsumsi energi yang terdeteksi dari data sensor.",
                        "color": FALLBACK_COLORS[(row_idx + col_idx) % len(FALLBACK_COLORS)],
                    },
                )
                cnt = type_counts.get(atype, 0)
                pct = (cnt / total_alerts * 100) if total_alerts > 0 else 0.0
                with cols[col_idx]:
                    st.markdown(
                        "".join([
                            '<div class="kpi-card" style="margin-bottom:10px;">',
                            '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">',
                            f'<span style="font-weight:700; font-size:0.88rem; color:#111827;">{meta["title"]}</span>',
                            f'<span class="badge-pill-blue">{format_id_num(cnt, 0)} Kasus</span>',
                            '</div>',
                            f'<div style="font-size:0.75rem; color:#6B7280; line-height:1.35; margin-bottom:8px;">{meta["desc"]}</div>',
                            '<div style="display:flex; justify-content:space-between; font-size:11px; font-weight:600; color:#6B7280; margin-bottom:4px;">',
                            '<span>Porsi Kasus</span>',
                            f'<span>{format_id_num(pct, 1)}%</span>',
                            '</div>',
                            '<div style="background:#F3F4F6; height:6px; border-radius:3px; overflow:hidden;">',
                            f'<div style="background:{meta["color"]}; width:{pct:.1f}%; height:100%; border-radius:3px;"></div>',
                            '</div>',
                            '</div>',
                        ]),
                        unsafe_allow_html=True,
                    )
