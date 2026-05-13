"""Palette et CSS pour reproduire le look kajiro-bron-dashboard."""
from __future__ import annotations

import streamlit as st

COLORS = {
    "bg": "#0A0A0A",
    "surface": "#111111",
    "surface_alt": "#161616",
    "border": "#222222",
    "red": "#C0392B",
    "coral": "#E8604C",
    "amber": "#E8A04C",
    "white": "#F5F5F0",
    "muted": "#666666",
    "dim": "#333333",
    "gold": "#FFD700",
    "silver": "#C0C0C0",
    "bronze": "#CD7F32",
}


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        html, body, [class*="css"], .stApp {{
            font-family: 'DM Mono', 'Courier New', monospace !important;
            background: {COLORS['bg']} !important;
            color: {COLORS['white']} !important;
        }}
        .block-container {{
            padding-top: 1.2rem !important;
            padding-bottom: 2rem !important;
            max-width: 1180px !important;
        }}
        h1, h2, h3, h4 {{
            color: {COLORS['white']} !important;
            font-weight: 700 !important;
            letter-spacing: 0.04em;
        }}
        section[data-testid="stSidebar"] {{
            background: {COLORS['surface']} !important;
            border-right: 1px solid {COLORS['border']};
        }}
        div[data-testid="stMetric"] {{
            background: {COLORS['surface']};
            border: 1px solid {COLORS['border']};
            border-radius: 10px;
            padding: 14px 16px;
        }}
        div[data-testid="stMetricLabel"] {{
            color: {COLORS['muted']} !important;
            font-size: 10px !important;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }}
        div[data-testid="stMetricValue"] {{
            color: {COLORS['white']} !important;
            font-size: 22px !important;
            font-weight: 700 !important;
        }}
        div[data-testid="stMetricDelta"] {{
            font-size: 11px !important;
        }}
        button[kind="primary"], .stButton > button {{
            background: {COLORS['coral']} !important;
            color: white !important;
            border: none !important;
            border-radius: 6px !important;
            font-weight: 700 !important;
            letter-spacing: 0.04em;
        }}
        .stButton > button:hover {{
            background: {COLORS['red']} !important;
        }}
        [data-baseweb="select"] > div {{
            background: {COLORS['surface_alt']} !important;
            border-color: {COLORS['border']} !important;
        }}
        .stDataFrame, [data-testid="stDataFrame"] {{
            border: 1px solid {COLORS['border']};
            border-radius: 10px;
            overflow: hidden;
        }}
        hr {{ border-color: {COLORS['border']} !important; }}
        a {{ color: {COLORS['coral']} !important; }}
        /* badges in markdown */
        .kj-tag {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.05em;
            margin-right: 4px;
        }}
        .kj-tag-coral {{ background: {COLORS['coral']}22; color: {COLORS['coral']}; border: 1px solid {COLORS['coral']}44; }}
        .kj-tag-amber {{ background: {COLORS['amber']}22; color: {COLORS['amber']}; border: 1px solid {COLORS['amber']}44; }}
        .kj-tag-muted {{ background: {COLORS['muted']}22; color: {COLORS['muted']}; border: 1px solid {COLORS['muted']}44; }}
        .kj-header {{
            display: flex; align-items: center; gap: 10px;
            padding: 14px 0 18px 0;
            border-bottom: 1px solid {COLORS['border']};
            margin-bottom: 24px;
        }}
        .kj-logo {{
            font-size: 18px; font-weight: 800; letter-spacing: 0.12em;
        }}
        .kj-dot {{
            width: 6px; height: 6px; border-radius: 50%;
            background: {COLORS['coral']}; display: inline-block;
        }}
        .kj-sub {{
            color: {COLORS['muted']}; font-size: 11px; letter-spacing: 0.08em;
            margin-left: auto;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def header() -> None:
    st.markdown(
        """
        <div class="kj-header">
          <span class="kj-logo">KAJIRŌ</span>
          <span class="kj-dot"></span>
          <span class="kj-logo">SUSHI</span>
          <span class="kj-sub">ANALYTICS · RÉSEAU</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
