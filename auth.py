"""Gate de mot de passe (calque LPMV)."""
from __future__ import annotations

import hmac

import streamlit as st


def check_password() -> bool:
    """Affiche un champ password, retourne True si correct."""
    def _verify() -> None:
        expected = st.secrets.get("DASHBOARD_PASSWORD", "")
        if hmac.compare_digest(st.session_state.get("pw", ""), expected):
            st.session_state["auth_ok"] = True
            st.session_state.pop("pw", None)
        else:
            st.session_state["auth_ok"] = False

    if st.session_state.get("auth_ok"):
        return True

    st.markdown(
        """
        <div style="max-width:360px;margin:80px auto 0;text-align:center;">
          <div style="font-size:24px;font-weight:800;letter-spacing:0.12em;">KAJIRŌ · SUSHI</div>
          <div style="color:#666;font-size:12px;letter-spacing:0.08em;margin-top:8px;">ANALYTICS · ACCÈS RESTREINT</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 2, 1])
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
            st.error("Mot de passe incorrect")
    return False
