"""Auth email + mot de passe (PBKDF2-SHA256) + session cookie 12h.

Plus simple et plus fiable que Google OAuth sur Streamlit Cloud.
Les utilisateurs et leurs hashes sont dans la table `users` de Supabase.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timedelta

import extra_streamlit_components as stx
import streamlit as st

import cache
from theme import load_svg

ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"

BOOTSTRAP_ADMIN_EMAIL = "hello@kajirosushi.com"
BOOTSTRAP_DEFAULT_PASSWORD = "kajiro2026"  # ⚠ à changer après 1ère connexion

COOKIE_NAME = "kj_session"
TTL_HOURS = 12


def _cookies() -> stx.CookieManager:
    """Singleton-like via session_state pour éviter de recréer le composant."""
    return stx.CookieManager(key="kj_cookie_mgr")


def _ensure_bootstrap() -> None:
    """1ère exec : crée l'admin par défaut + password initial si vide."""
    try:
        cache.init_db()
        cache.bootstrap_admin(BOOTSTRAP_ADMIN_EMAIL, default_password=BOOTSTRAP_DEFAULT_PASSWORD)
    except Exception as e:  # noqa: BLE001
        st.error(f"Impossible de connecter Supabase : {e}")
        st.stop()


# ---------------------------------------------------------------------------
# Session cookie signé
# ---------------------------------------------------------------------------
def _cookie_secret() -> str:
    return st.secrets.get("DASHBOARD_PASSWORD", "kj_default_secret_change_me_in_prod")


def _sign_token(email: str, timestamp: int) -> str:
    secret = _cookie_secret().encode()
    msg = f"{email}|{timestamp}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()[:32]


def _make_session_token(email: str) -> str:
    ts = int(time.time())
    return f"{email}|{ts}|{_sign_token(email, ts)}"


def _verify_session_token(token: object) -> str | None:
    """Retourne l'email si token valide & non expiré, sinon None."""
    if not isinstance(token, str) or token.count("|") != 2:
        return None
    try:
        email, ts_str, sig = token.split("|", 2)
        ts = int(ts_str)
    except (ValueError, AttributeError):
        return None
    if time.time() - ts > TTL_HOURS * 3600:
        return None
    if not hmac.compare_digest(sig, _sign_token(email, ts)):
        return None
    return email


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------
def current_user() -> dict | None:
    """Renvoie le user logged-in s'il existe en DB. None sinon."""
    if not st.session_state.get("auth_ok"):
        return None
    email = st.session_state.get("auth_email", "")
    if not email:
        return None
    u = cache.get_user(email)
    if not u:
        return None
    return {
        "email": email,
        "name": email.split("@")[0].replace(".", " ").title(),
        "picture": "",
        "role": u["role"],
        "restaurant_ids": u.get("restaurant_ids"),
    }


def is_admin(user: dict | None = None) -> bool:
    u = user or current_user()
    return bool(u and u.get("role") == ROLE_ADMIN)


def allowed_restaurant_ids(user: dict, all_ids: list[int]) -> list[int]:
    """Filtre les IDs restos selon le user. None = tous."""
    rids = user.get("restaurant_ids")
    if rids is None:
        return list(all_ids)
    rids_set = set(int(r) for r in rids)
    return [r for r in all_ids if r in rids_set]


def logout() -> None:
    """Efface la session + cookie."""
    try:
        _cookies().delete(COOKIE_NAME)
    except Exception:  # noqa: BLE001
        pass
    st.session_state.pop("auth_ok", None)
    st.session_state.pop("auth_email", None)


def require_login() -> dict:
    """Bloque l'app si pas connecté. Affiche le formulaire de login."""
    _ensure_bootstrap()

    # Vérif session_state déjà OK
    user = current_user()
    if user:
        return user

    # Tentative de restauration depuis cookie
    cm = _cookies()
    cookie_token = cm.get(COOKIE_NAME)
    restored_email = _verify_session_token(cookie_token)
    if restored_email and cache.get_user(restored_email):
        st.session_state["auth_ok"] = True
        st.session_state["auth_email"] = restored_email
        return current_user() or {}

    # --- Formulaire login ---
    _render_login_form(cm)
    st.stop()
    return {}


def _render_login_form(cm: stx.CookieManager) -> None:
    logo = load_svg("kajiro_logo_carre_blanc.svg")
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
        email = st.text_input("Email", placeholder="vous@kajirosushi.com",
                                key="login_email", label_visibility="collapsed")
        password = st.text_input("Mot de passe", type="password",
                                   placeholder="Mot de passe",
                                   key="login_password", label_visibility="collapsed")
        if st.button("Se connecter", type="primary", use_container_width=True):
            email_norm = (email or "").strip().lower()
            u = cache.get_user(email_norm)
            if not u:
                st.error("Identifiants invalides")
            elif not cache.verify_password(password, u.get("password_hash")):
                st.error("Identifiants invalides")
            else:
                # Login OK
                st.session_state["auth_ok"] = True
                st.session_state["auth_email"] = email_norm
                token = _make_session_token(email_norm)
                cm.set(
                    COOKIE_NAME,
                    token,
                    expires_at=datetime.now() + timedelta(hours=TTL_HOURS),
                )
                st.rerun()

    st.markdown(
        '<div class="kj-login-card" style="margin-top:24px;padding:0;">'
        '<div class="kj-login-footer">Yumea · Kajirō Sushi</div>'
        '</div>',
        unsafe_allow_html=True,
    )
