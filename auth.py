"""Auth Google OAuth via st.login() (Streamlit ≥ 1.42).

La config OAuth est dans .streamlit/secrets.toml sous [auth].
La whitelist d'emails + rôles est dans [auth_allowed_users].
Pas de gestion de mot de passe — Google fournit le 2FA et l'audit.
"""
from __future__ import annotations

import streamlit as st

from theme import load_svg


ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"


def _allowed_users() -> dict[str, str]:
    """Retourne {email_lowercase: role} depuis secrets [auth_allowed_users]."""
    try:
        raw = st.secrets["auth_allowed_users"]
    except (KeyError, FileNotFoundError):
        return {}
    return {str(email).strip().lower(): str(role).strip().lower() for email, role in raw.items()}


def current_user() -> dict[str, str] | None:
    """Renvoie {email, name, picture, role} si l'utilisateur est loggé et autorisé."""
    if not getattr(st.user, "is_logged_in", False):
        return None
    email = (getattr(st.user, "email", "") or "").lower()
    role = _allowed_users().get(email)
    if not role:
        return None
    return {
        "email": email,
        "name": getattr(st.user, "name", "") or email,
        "picture": getattr(st.user, "picture", "") or "",
        "role": role,
    }


def is_admin() -> bool:
    u = current_user()
    return bool(u and u.get("role") == ROLE_ADMIN)


def logout() -> None:
    """Déconnexion : st.logout() efface la session Streamlit + redirige."""
    if hasattr(st, "logout"):
        st.logout()


def require_login() -> dict[str, str]:
    """Bloque le rendu si l'utilisateur n'est pas connecté avec un email whitelisté.

    Affiche la page de login (logo + bouton Google) et `st.stop()`. Sinon renvoie
    le dict utilisateur.
    """
    user = current_user()
    if user:
        return user

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
        if not getattr(st.user, "is_logged_in", False):
            # Pas encore connecté
            if st.button("Se connecter avec Google", type="primary", use_container_width=True):
                st.login("google")
        else:
            # Connecté côté Google mais email pas dans la whitelist
            connected_email = getattr(st.user, "email", "?")
            st.markdown(
                f'<div style="color:#ED7553;font-size:13px;text-align:center;'
                f'margin:12px 0;letter-spacing:0.04em;line-height:1.5;">'
                f"Le compte <b>{connected_email}</b><br>n'est pas autorisé.<br>"
                f"<span style=\"font-size:11px;color:#7A7A7A;\">Contacte hello@kajirosushi.com</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if st.button("Changer de compte Google", use_container_width=True):
                st.logout()

    st.markdown(
        '<div class="kj-login-card" style="margin-top:24px;padding:0;">'
        '<div class="kj-login-footer">Yumea · Kajirō Sushi · Accès SSO Google</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.stop()
    return {}  # unreachable
