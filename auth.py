"""Auth Google OAuth (st.login) + gestion des accès via Supabase.

La whitelist d'emails + rôle + restaurants autorisés vit dans la table
`users` de Supabase. Pour ajouter/modifier un user :
- soit via le panneau "Gérer les utilisateurs" (admin), depuis l'app
- soit directement via Supabase → Table Editor → users

Le compte `hello@kajirosushi.com` est garanti admin avec accès total (bootstrap).
"""
from __future__ import annotations

import streamlit as st

import cache
from theme import load_svg

ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"

BOOTSTRAP_ADMIN_EMAIL = "hello@kajirosushi.com"


def _ensure_bootstrap() -> None:
    """Première exécution : crée l'admin par défaut si la table est vide."""
    try:
        cache.init_db()
        cache.bootstrap_admin(BOOTSTRAP_ADMIN_EMAIL)
    except Exception as e:  # noqa: BLE001
        st.error(f"Impossible de connecter Supabase : {e}")
        st.stop()


def current_user() -> dict | None:
    """Renvoie le user logged-in s'il est autorisé. None sinon.

    Format : {email, name, picture, role, restaurant_ids (None=all)}.
    """
    if not getattr(st.user, "is_logged_in", False):
        return None
    email = (getattr(st.user, "email", "") or "").lower()
    u = cache.get_user(email)
    if not u:
        return None
    return {
        "email": email,
        "name": getattr(st.user, "name", "") or email,
        "picture": getattr(st.user, "picture", "") or "",
        "role": u["role"],
        "restaurant_ids": u.get("restaurant_ids"),  # None = tous
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
    if hasattr(st, "logout"):
        st.logout()


def require_login() -> dict:
    """Bloque le rendu si user non loggé ou pas dans la whitelist DB."""
    _ensure_bootstrap()

    user = current_user()
    if user:
        return user

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
        if not getattr(st.user, "is_logged_in", False):
            if st.button("Se connecter avec Google", type="primary", use_container_width=True):
                st.login("google")
        else:
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
