"""Gate de mot de passe — page d'accueil charte Kajirō."""
from __future__ import annotations

import hmac

import streamlit as st

from theme import load_svg


def check_password() -> bool:
    """Affiche la page de login, retourne True si correct."""
    def _verify() -> None:
        expected = st.secrets.get("DASHBOARD_PASSWORD", "")
        if hmac.compare_digest(st.session_state.get("pw", ""), expected):
            st.session_state["auth_ok"] = True
            st.session_state.pop("pw", None)
        else:
            st.session_state["auth_ok"] = False

    if st.session_state.get("auth_ok"):
        return True

    logo = load_svg("logo_carre_blanc.svg")

    st.markdown('<div class="kj-login-bg"></div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="kj-login-card">
          <div class="kj-login-logo">{logo}</div>
          <div class="kj-login-title">Analytics réseau</div>
          <div class="kj-login-sub">Tableau de bord</div>
          <div class="kj-login-divider"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1.6, 1])
    with col2:
        st.text_input(
            "Mot de passe",
            type="password",
            on_change=_verify,
            key="pw",
            label_visibility="collapsed",
            placeholder="Mot de passe",
        )
        if st.session_state.get("auth_ok") is False:
            st.markdown(
                '<div style="color:#ED7553;font-size:12px;text-align:center;'
                'margin-top:8px;letter-spacing:0.08em;">Mot de passe incorrect</div>',
                unsafe_allow_html=True,
            )

    st.markdown(
        '<div class="kj-login-card" style="margin-top:24px;padding:0;">'
        '<div class="kj-login-footer">Yumea · 7 établissements</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    return False
