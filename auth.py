"""Gate de mot de passe + session persistante 12h via cookie signé HMAC."""
from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timedelta

import extra_streamlit_components as stx
import streamlit as st

from theme import load_svg

COOKIE_NAME = "kj_session"
TTL_HOURS = 12
TTL_SECONDS = TTL_HOURS * 3600


@st.cache_resource
def _cookies() -> stx.CookieManager:
    return stx.CookieManager(key="kj_cookie_mgr")


def _sign(timestamp: int, secret: str) -> str:
    return hmac.new(secret.encode(), str(timestamp).encode(), hashlib.sha256).hexdigest()[:32]


def _make_token(secret: str) -> str:
    ts = int(time.time())
    return f"{ts}.{_sign(ts, secret)}"


def _verify_token(token: object, secret: str) -> bool:
    if not isinstance(token, str) or "." not in token or not secret:
        return False
    try:
        ts_str, sig = token.split(".", 1)
        ts = int(ts_str)
    except (ValueError, TypeError):
        return False
    if time.time() - ts > TTL_SECONDS:
        return False
    return hmac.compare_digest(sig, _sign(ts, secret))


def logout() -> None:
    """Efface la session côté serveur ET le cookie côté navigateur."""
    try:
        _cookies().delete(COOKIE_NAME)
    except Exception:
        pass
    st.session_state.pop("auth_ok", None)


def check_password() -> bool:
    secret = st.secrets.get("DASHBOARD_PASSWORD", "")
    cm = _cookies()

    # Restore session from cookie
    token = cm.get(COOKIE_NAME)
    if _verify_token(token, secret):
        st.session_state["auth_ok"] = True
        return True

    if st.session_state.get("auth_ok"):
        return True

    def _verify() -> None:
        pw = st.session_state.get("pw", "")
        if secret and hmac.compare_digest(pw, secret):
            st.session_state["auth_ok"] = True
            cm.set(
                COOKIE_NAME,
                _make_token(secret),
                expires_at=datetime.now() + timedelta(hours=TTL_HOURS),
            )
            st.session_state.pop("pw", None)
        else:
            st.session_state["auth_ok"] = False

    logo = load_svg("logo_carre_blanc.svg")
    st.markdown('<div class="kj-login-bg"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="kj-login-card">'
        f'<div class="kj-login-logo">{logo}</div>'
        '<div class="kj-login-title">Analytics réseau</div>'
        '<div class="kj-login-sub">Tableau de bord</div>'
        '<div class="kj-login-divider"></div>'
        '</div>',
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
        '<div class="kj-login-footer">Yumea · 7 établissements · Session 12h</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    return False
