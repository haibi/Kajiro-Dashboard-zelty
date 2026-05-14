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

IMAGES_DIR = Path(__file__).parent / "Images"


def load_svg(name: str) -> str:
    """Retourne le contenu SVG inline-prêt (sans wrapper)."""
    path = IMAGES_DIR / name
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

        /* === MOBILE (< 768px) === */
        @media (max-width: 768px) {{
            .block-container {{
                padding: 0.5rem 0.75rem 2rem !important;
                max-width: 100% !important;
            }}
            /* Header — logo plus petit, masquer pill décorative */
            .kj-header {{
                padding: 6px 0 14px 0;
                margin-bottom: 16px;
                gap: 10px;
            }}
            .kj-header svg {{ height: 26px !important; }}
            .kj-pill {{ display: none !important; }}
            .kj-header-sub {{ font-size: 9px !important; letter-spacing: 0.12em; }}

            /* Tabs : tap target plus grand, font lisible */
            button[data-baseweb="tab"] {{
                padding: 10px 12px !important;
                font-size: 11px !important;
                min-height: 44px;
                letter-spacing: 0.04em !important;
            }}
            div[data-baseweb="tab-list"] {{
                gap: 0 !important;
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
            }}

            /* Boutons */
            .stButton > button {{
                min-height: 44px !important;
                font-size: 12px !important;
                padding: 8px 12px !important;
            }}

            /* Pills (st.pills) — plus compactes */
            div[data-testid="stPills"] button,
            [data-baseweb="button-group"] button {{
                min-height: 36px !important;
                font-size: 12px !important;
                padding: 6px 12px !important;
            }}

            /* Métriques : moins de padding, font lisible */
            div[data-testid="stMetric"] {{
                padding: 10px 12px !important;
            }}
            div[data-testid="stMetricLabel"] {{
                font-size: 9px !important;
            }}
            div[data-testid="stMetricValue"] {{
                font-size: 18px !important;
            }}
            div[data-testid="stMetricDelta"] {{
                font-size: 10px !important;
            }}

            /* Inputs : 44px min pour tap iOS */
            .stTextInput input, .stDateInput input,
            [data-baseweb="select"] > div {{
                min-height: 44px !important;
                font-size: 14px !important;  /* >= 16px évite zoom auto iOS, mais 14px reste lisible */
            }}

            /* Tables custom : plus compactes, font réduite */
            .kj-tr {{
                gap: 8px !important;
                padding: 10px 12px !important;
                font-size: 12px !important;
            }}
            .kj-name-cell > div:first-child {{
                font-size: 12px !important;
            }}
            .kj-thead {{
                font-size: 9px !important;
                letter-spacing: 0.08em !important;
            }}

            /* Login : logo + carte plus petit */
            .kj-login-card {{
                max-width: 90% !important;
                padding: 16px 14px !important;
            }}
            .kj-login-logo {{
                width: 140px !important;
                margin-bottom: 18px !important;
            }}

            /* Streamlit columns gap : moins serré */
            div[data-testid="stHorizontalBlock"] {{
                gap: 8px !important;
            }}

            /* DataFrames : scrollable horizontalement */
            .stDataFrame {{
                font-size: 11px !important;
            }}

            /* Plotly responsive — déjà use_container_width=true */
            .js-plotly-plot {{ width: 100% !important; }}

            /* Cacher l'icône "fullscreen" sur plotly mobile (encombre) */
            .modebar-container {{ display: none !important; }}

            /* Caption + markdown : un peu plus grand pour lisibilité */
            .stCaption, [data-testid="stCaptionContainer"] {{
                font-size: 11px !important;
            }}
        }}

        /* === Très petit (< 420px) — compresse encore plus === */
        @media (max-width: 420px) {{
            div[data-testid="stMetricValue"] {{
                font-size: 16px !important;
            }}
            button[data-baseweb="tab"] {{
                padding: 8px 10px !important;
                font-size: 10px !important;
            }}
            .kj-header svg {{ height: 22px !important; }}
        }}
    """).strip()


def inject_css() -> None:
    # Tags PWA — manifest + apple-touch-icon + theme-color
    # Les fichiers static/* sont servis par Streamlit via enableStaticServing=true
    pwa_head = (
        '<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=5">'
        '<link rel="manifest" href="./app/static/manifest.json">'
        '<link rel="apple-touch-icon" sizes="180x180" href="./app/static/icon-180.png">'
        '<link rel="icon" type="image/png" sizes="192x192" href="./app/static/icon-192.png">'
        '<meta name="theme-color" content="#ED7553">'
        '<meta name="apple-mobile-web-app-capable" content="yes">'
        '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">'
        '<meta name="apple-mobile-web-app-title" content="Kajirō">'
        '<meta name="mobile-web-app-capable" content="yes">'
    )
    st.markdown(pwa_head, unsafe_allow_html=True)
    st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)


def header() -> None:
    logo = load_svg("kajiro_logo_ligne_blanc.svg")
    html = (
        '<div class="kj-header">'
        f"{logo}"
        '<span class="kj-pill"><span class="kj-pill-dot"></span> Analytics réseau</span>'
        '<span class="kj-header-sub">Tableau de bord</span>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
