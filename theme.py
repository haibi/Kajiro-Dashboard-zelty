"""Palette et CSS — charte officielle Kajirō Sushi."""
from __future__ import annotations

import textwrap
from pathlib import Path

import streamlit as st

# Charte graphique officielle
COLORS = {
    "bg": "#0A0A0A",
    "surface": "#111111",
    "surface_alt": "#161616",
    "border": "#222222",
    "coral": "#ED7553",          # officiel — cercle du logo
    "coral_dim": "#C25A3D",
    "amber": "#E8A04C",
    "white": "#FFFFFF",
    "off_white": "#F5F5F0",
    "muted": "#7A7A7A",
    "dim": "#333333",
    "gold": "#FFD700",
    "silver": "#C0C0C0",
    "bronze": "#CD7F32",
}

ASSETS = Path(__file__).parent / "assets"


def load_svg(name: str) -> str:
    """Retourne le contenu SVG inline-prêt (sans wrapper)."""
    path = ASSETS / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _css() -> str:
    c = COLORS
    return textwrap.dedent(f"""
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@200;300;400;500;600;700;800;900&display=swap');

        :root {{
            --kj-bg: {c['bg']};
            --kj-surface: {c['surface']};
            --kj-surface-alt: {c['surface_alt']};
            --kj-border: {c['border']};
            --kj-coral: {c['coral']};
            --kj-white: {c['white']};
            --kj-muted: {c['muted']};
        }}

        html, body, [class*="css"], .stApp {{
            font-family: 'Poppins', system-ui, sans-serif !important;
            background: {c['bg']} !important;
            color: {c['white']} !important;
        }}

        #MainMenu, footer {{ visibility: hidden; }}
        header[data-testid="stHeader"] {{
            background: transparent !important;
            height: 0 !important;
        }}

        .block-container {{
            padding-top: 1.2rem !important;
            padding-bottom: 2rem !important;
            max-width: 1200px !important;
        }}

        h1, h2, h3, h4 {{
            font-family: 'Poppins', sans-serif !important;
            color: {c['white']} !important;
            font-weight: 700 !important;
            letter-spacing: 0.01em;
        }}

        section[data-testid="stSidebar"] {{
            background: {c['surface']} !important;
            border-right: 1px solid {c['border']};
        }}

        div[data-testid="stMetric"] {{
            background: {c['surface']};
            border: 1px solid {c['border']};
            border-radius: 12px;
            padding: 16px 18px;
            transition: border-color 0.2s;
        }}
        div[data-testid="stMetric"]:hover {{ border-color: {c['coral']}66; }}
        div[data-testid="stMetricLabel"] {{
            color: {c['muted']} !important;
            font-size: 10px !important;
            font-weight: 600 !important;
            letter-spacing: 0.14em;
            text-transform: uppercase;
        }}
        div[data-testid="stMetricValue"] {{
            color: {c['white']} !important;
            font-size: 26px !important;
            font-weight: 700 !important;
            font-family: 'Poppins', sans-serif !important;
        }}

        .stButton > button {{
            background: {c['coral']} !important;
            color: white !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            font-family: 'Poppins', sans-serif !important;
            letter-spacing: 0.04em;
            transition: all 0.2s;
            padding: 8px 18px !important;
        }}
        .stButton > button:hover {{
            background: {c['coral_dim']} !important;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px {c['coral']}33;
        }}
        .stButton > button[kind="secondary"] {{
            background: transparent !important;
            border: 1px solid {c['border']} !important;
            color: {c['muted']} !important;
        }}
        .stButton > button[kind="secondary"]:hover {{
            border-color: {c['coral']} !important;
            color: {c['coral']} !important;
            box-shadow: none;
        }}

        [data-baseweb="select"] > div,
        [data-baseweb="input"] > div,
        .stTextInput input,
        .stDateInput input {{
            background: {c['surface_alt']} !important;
            border-color: {c['border']} !important;
            color: {c['white']} !important;
            font-family: 'Poppins', sans-serif !important;
        }}
        .stTextInput input:focus,
        .stDateInput input:focus {{
            border-color: {c['coral']} !important;
            box-shadow: 0 0 0 1px {c['coral']}33 !important;
        }}

        [data-baseweb="tag"] {{
            background: {c['coral']}22 !important;
            border: 1px solid {c['coral']}66 !important;
            color: {c['coral']} !important;
            font-family: 'Poppins', sans-serif !important;
        }}

        .stDataFrame, [data-testid="stDataFrame"] {{
            border: 1px solid {c['border']};
            border-radius: 12px;
            overflow: hidden;
        }}

        button[data-baseweb="tab"] {{
            font-family: 'Poppins', sans-serif !important;
            font-weight: 600 !important;
            letter-spacing: 0.08em;
            color: {c['muted']} !important;
        }}
        button[data-baseweb="tab"][aria-selected="true"] {{ color: {c['white']} !important; }}
        [data-baseweb="tab-highlight"] {{ background: {c['coral']} !important; }}

        hr {{ border-color: {c['border']} !important; }}
        a {{ color: {c['coral']} !important; text-decoration: none; }}

        .kj-header {{
            display: flex; align-items: center; gap: 16px;
            padding: 10px 0 22px 0;
            border-bottom: 1px solid {c['border']};
            margin-bottom: 28px;
        }}
        .kj-header svg {{ height: 38px; width: auto; }}
        .kj-header-sub {{
            margin-left: auto;
            color: {c['muted']};
            font-size: 11px;
            letter-spacing: 0.18em;
            font-weight: 500;
            text-transform: uppercase;
        }}
        .kj-pill {{
            display: inline-flex; align-items: center; gap: 6px;
            background: {c['surface']};
            border: 1px solid {c['border']};
            border-radius: 999px;
            padding: 4px 12px;
            font-size: 10px;
            color: {c['muted']};
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }}
        .kj-pill-dot {{
            width: 6px; height: 6px; border-radius: 50%;
            background: {c['coral']};
            box-shadow: 0 0 8px {c['coral']};
        }}

        .kj-login-bg {{
            position: fixed; inset: 0; z-index: -1;
            background:
                radial-gradient(circle at 20% 30%, {c['coral']}11 0%, transparent 40%),
                radial-gradient(circle at 80% 70%, {c['coral']}08 0%, transparent 50%),
                {c['bg']};
        }}
        .kj-login-card {{
            max-width: 380px;
            margin: 6vh auto 0;
            text-align: center;
            padding: 32px 28px;
        }}
        .kj-login-logo {{
            width: 180px;
            margin: 0 auto 24px;
            display: block;
        }}
        .kj-login-logo svg {{ width: 100%; height: auto; }}
        .kj-login-title {{
            font-family: 'Poppins', sans-serif;
            font-weight: 200;
            letter-spacing: 0.32em;
            font-size: 11px;
            color: {c['muted']};
            text-transform: uppercase;
            margin-bottom: 4px;
        }}
        .kj-login-sub {{
            font-family: 'Poppins', sans-serif;
            font-weight: 600;
            letter-spacing: 0.08em;
            font-size: 13px;
            color: {c['white']};
            margin-bottom: 28px;
        }}
        .kj-login-divider {{
            width: 40px; height: 2px;
            background: {c['coral']};
            margin: 0 auto 28px;
            border-radius: 2px;
        }}
        .kj-login-footer {{
            margin-top: 32px;
            color: {c['dim']};
            font-size: 10px;
            letter-spacing: 0.16em;
            text-transform: uppercase;
        }}

        /* === Ranking table (style Bron) === */
        .kj-table {{
            background: {c['surface']};
            border: 1px solid {c['border']};
            border-radius: 12px;
            overflow: hidden;
            margin-top: 8px;
        }}
        .kj-tr {{
            display: grid;
            grid-template-columns: var(--cols);
            gap: 10px;
            padding: 12px 16px;
            border-bottom: 1px solid {c['border']};
            align-items: center;
            font-size: 13px;
            transition: background 0.12s;
        }}
        .kj-tr:last-child {{ border-bottom: none; }}
        .kj-tr:not(.kj-thead):not(.kj-tfoot):hover {{
            background: {c['coral']}0A;
        }}
        .kj-tr > div {{
            min-width: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .kj-thead {{
            background: {c['surface_alt']};
            color: {c['muted']};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            padding-top: 10px; padding-bottom: 10px;
        }}
        .kj-thead .kj-h-hi {{ color: {c['coral']}; }}
        .kj-tfoot {{
            background: {c['surface_alt']};
            border-top: 1px solid {c['border']};
            border-bottom: none;
            font-size: 12px;
        }}
        .kj-rank {{ font-size: 13px; }}
        .kj-name-cell {{ display: flex; flex-direction: column; gap: 6px; }}
        .kj-name-cell > div:first-child {{
            color: {c['white']}; font-size: 13px;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }}
        .kj-spark {{
            width: 100%;
            height: 3px;
            background: {c['dim']};
            border-radius: 2px;
            overflow: hidden;
        }}
        .kj-spark-fill {{
            height: 100%;
            background: linear-gradient(90deg, {c['coral']}, {c['amber']});
            border-radius: 2px;
            transition: width 0.4s ease;
        }}
    """).strip()


def inject_css() -> None:
    st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)


def header() -> None:
    logo = load_svg("logo_ligne_blanc.svg")
    html = (
        '<div class="kj-header">'
        f"{logo}"
        '<span class="kj-pill"><span class="kj-pill-dot"></span> Analytics réseau</span>'
        '<span class="kj-header-sub">Tableau de bord</span>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
