"""Palette et CSS — charte officielle Kajirō Sushi."""
from __future__ import annotations

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


def inject_css() -> None:
    st.markdown(
        f"""
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@200;300;400;500;600;700;800;900&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
        <style>
        :root {{
            --kj-bg: {COLORS['bg']};
            --kj-surface: {COLORS['surface']};
            --kj-surface-alt: {COLORS['surface_alt']};
            --kj-border: {COLORS['border']};
            --kj-coral: {COLORS['coral']};
            --kj-white: {COLORS['white']};
            --kj-muted: {COLORS['muted']};
        }}

        html, body, [class*="css"], .stApp {{
            font-family: 'Poppins', system-ui, sans-serif !important;
            background: {COLORS['bg']} !important;
            color: {COLORS['white']} !important;
        }}

        /* hide streamlit chrome */
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
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
            color: {COLORS['white']} !important;
            font-weight: 700 !important;
            letter-spacing: 0.01em;
        }}

        /* Sidebar */
        section[data-testid="stSidebar"] {{
            background: {COLORS['surface']} !important;
            border-right: 1px solid {COLORS['border']};
        }}

        /* Metric cards */
        div[data-testid="stMetric"] {{
            background: {COLORS['surface']};
            border: 1px solid {COLORS['border']};
            border-radius: 12px;
            padding: 16px 18px;
            transition: border-color 0.2s;
        }}
        div[data-testid="stMetric"]:hover {{
            border-color: {COLORS['coral']}66;
        }}
        div[data-testid="stMetricLabel"] {{
            color: {COLORS['muted']} !important;
            font-size: 10px !important;
            font-weight: 600 !important;
            letter-spacing: 0.14em;
            text-transform: uppercase;
        }}
        div[data-testid="stMetricValue"] {{
            color: {COLORS['white']} !important;
            font-size: 26px !important;
            font-weight: 700 !important;
            font-family: 'Poppins', sans-serif !important;
        }}

        /* Buttons */
        .stButton > button {{
            background: {COLORS['coral']} !important;
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
            background: {COLORS['coral_dim']} !important;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px {COLORS['coral']}33;
        }}
        .stButton > button[kind="secondary"] {{
            background: transparent !important;
            border: 1px solid {COLORS['border']} !important;
            color: {COLORS['muted']} !important;
        }}
        .stButton > button[kind="secondary"]:hover {{
            border-color: {COLORS['coral']} !important;
            color: {COLORS['coral']} !important;
            box-shadow: none;
        }}

        /* Inputs */
        [data-baseweb="select"] > div,
        [data-baseweb="input"] > div,
        .stTextInput input,
        .stDateInput input {{
            background: {COLORS['surface_alt']} !important;
            border-color: {COLORS['border']} !important;
            color: {COLORS['white']} !important;
            font-family: 'Poppins', sans-serif !important;
        }}
        .stTextInput input:focus,
        .stDateInput input:focus {{
            border-color: {COLORS['coral']} !important;
            box-shadow: 0 0 0 1px {COLORS['coral']}33 !important;
        }}

        /* Multiselect tags */
        [data-baseweb="tag"] {{
            background: {COLORS['coral']}22 !important;
            border: 1px solid {COLORS['coral']}66 !important;
            color: {COLORS['coral']} !important;
            font-family: 'Poppins', sans-serif !important;
        }}

        /* DataFrame */
        .stDataFrame, [data-testid="stDataFrame"] {{
            border: 1px solid {COLORS['border']};
            border-radius: 12px;
            overflow: hidden;
        }}

        /* Tabs */
        button[data-baseweb="tab"] {{
            font-family: 'Poppins', sans-serif !important;
            font-weight: 600 !important;
            letter-spacing: 0.08em;
            color: {COLORS['muted']} !important;
        }}
        button[data-baseweb="tab"][aria-selected="true"] {{
            color: {COLORS['white']} !important;
        }}
        [data-baseweb="tab-highlight"] {{
            background: {COLORS['coral']} !important;
        }}

        hr {{ border-color: {COLORS['border']} !important; }}
        a {{ color: {COLORS['coral']} !important; text-decoration: none; }}

        /* Header brand */
        .kj-header {{
            display: flex; align-items: center; gap: 16px;
            padding: 10px 0 22px 0;
            border-bottom: 1px solid {COLORS['border']};
            margin-bottom: 28px;
        }}
        .kj-header svg {{ height: 38px; width: auto; }}
        .kj-header-sub {{
            margin-left: auto;
            color: {COLORS['muted']};
            font-size: 11px;
            letter-spacing: 0.18em;
            font-weight: 500;
            text-transform: uppercase;
        }}
        .kj-pill {{
            display: inline-flex; align-items: center; gap: 6px;
            background: {COLORS['surface']};
            border: 1px solid {COLORS['border']};
            border-radius: 999px;
            padding: 4px 12px;
            font-size: 10px;
            color: {COLORS['muted']};
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }}
        .kj-pill-dot {{
            width: 6px; height: 6px; border-radius: 50%;
            background: {COLORS['coral']};
            box-shadow: 0 0 8px {COLORS['coral']};
        }}

        /* Login page */
        .kj-login-bg {{
            position: fixed; inset: 0; z-index: -1;
            background:
                radial-gradient(circle at 20% 30%, {COLORS['coral']}11 0%, transparent 40%),
                radial-gradient(circle at 80% 70%, {COLORS['coral']}08 0%, transparent 50%),
                {COLORS['bg']};
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
            color: {COLORS['muted']};
            text-transform: uppercase;
            margin-bottom: 4px;
        }}
        .kj-login-sub {{
            font-family: 'Poppins', sans-serif;
            font-weight: 600;
            letter-spacing: 0.08em;
            font-size: 13px;
            color: {COLORS['white']};
            margin-bottom: 28px;
        }}
        .kj-login-divider {{
            width: 40px; height: 2px;
            background: {COLORS['coral']};
            margin: 0 auto 28px;
            border-radius: 2px;
        }}
        .kj-login-footer {{
            margin-top: 32px;
            color: {COLORS['dim']};
            font-size: 10px;
            letter-spacing: 0.16em;
            text-transform: uppercase;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def header() -> None:
    logo = load_svg("logo_ligne_blanc.svg")
    st.markdown(
        f"""
        <div class="kj-header">
          {logo}
          <span class="kj-pill"><span class="kj-pill-dot"></span> Analytics réseau</span>
          <span class="kj-header-sub">Tableau de bord</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
