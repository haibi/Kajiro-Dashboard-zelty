"""Kajirō Dashboard — analytics réseau multi-restaurants depuis l'API Zelty (v2.10)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

import backfill
import cache
import periods
import zelty_client
from auth import allowed_restaurant_ids, logout, require_login
from components import render_product_table, render_ranking_table
from theme import COLORS, header, inject_css

FAVICON = Path(__file__).parent / "assets" / "favicon.svg"

TOP_PRESETS = [15, 30, 50, 100]


@st.dialog("👥 Gestion des utilisateurs", width="large")
def users_dialog(all_restos: list[dict]) -> None:
    """Panneau admin : liste, ajout, modif, suppression d'utilisateurs."""
    st.caption(
        "Définis qui peut se connecter avec son compte Google et à quels "
        "restaurants. Un utilisateur sans entrée ici se voit refuser l'accès."
    )
    users = cache.list_users()
    id_to_name = {r["id"]: r["name"] for r in all_restos}

    # --- Liste des users existants ---
    if users:
        for u in users:
            email = u["email"]
            role = u["role"]
            rids = u.get("restaurant_ids")
            scope = "Tous" if rids is None else (
                "Aucun" if not rids else ", ".join(
                    id_to_name.get(int(r), f"#{r}") for r in rids
                )
            )
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.markdown(f"**{email}**  \n_{role.upper()} · {scope}_")
                if c2.button("Modifier", key=f"edit_{email}"):
                    st.session_state["edit_user"] = email
                    st.rerun()
                if c3.button("Supprimer", key=f"del_{email}", type="secondary"):
                    cache.delete_user(email)
                    st.rerun()

    st.markdown("---")

    # --- Form d'édition (si on a cliqué "Modifier") ou de création ---
    editing = st.session_state.get("edit_user", "")
    existing = next((u for u in users if u["email"] == editing), None) if editing else None

    title = f"Modifier {editing}" if existing else "Ajouter un utilisateur"
    st.markdown(f"#### {title}")

    email = st.text_input(
        "Email Google",
        value=existing["email"] if existing else "",
        disabled=bool(existing),
        placeholder="prenom.nom@kajirosushi.com",
    )
    role = st.radio(
        "Rôle",
        options=["viewer", "admin"],
        index=0 if not existing else (0 if existing["role"] == "viewer" else 1),
        horizontal=True,
        help="admin = accès complet + peut gérer les utilisateurs. viewer = lecture seule.",
    )
    scope = st.radio(
        "Accès aux restaurants",
        options=["Tous", "Sélection"],
        index=0 if (not existing or existing.get("restaurant_ids") is None) else 1,
        horizontal=True,
    )
    selected_rids: list[int] | None = None
    if scope == "Sélection":
        current_rids = set(int(r) for r in (existing.get("restaurant_ids") or []))
        chosen_names = st.multiselect(
            "Restaurants autorisés",
            options=[r["name"] for r in all_restos],
            default=[r["name"] for r in all_restos if r["id"] in current_rids],
        )
        selected_rids = [r["id"] for r in all_restos if r["name"] in chosen_names]

    cs, cc = st.columns(2)
    if cs.button("💾 Enregistrer", type="primary", use_container_width=True):
        try:
            cache.upsert_user(email, role, selected_rids)
            st.session_state.pop("edit_user", None)
            st.rerun()
        except ValueError as e:
            st.error(str(e))
    if cc.button("Annuler", use_container_width=True):
        st.session_state.pop("edit_user", None)
        st.rerun()

st.set_page_config(
    page_title="Kajirō Sushi · Analytics",
    page_icon=str(FAVICON) if FAVICON.exists() else None,
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_css()

user = require_login()

header()

# ------------------------------------------------------------------
# Restaurants
# ------------------------------------------------------------------
with st.spinner("Connexion à Zelty…"):
    try:
        restos_df = zelty_client.list_restaurants()
    except zelty_client.ZeltyError as e:
        st.error(f"Impossible de joindre Zelty: {e}")
        st.stop()

if restos_df.empty:
    st.warning("Aucun restaurant retourné par l'API.")
    st.stop()

# La liste complète est utile pour le panneau admin (gérer les accès)
all_restos_df = restos_df.copy()
all_ids = restos_df["id"].astype(int).tolist()

# Filtrage selon les droits du user
user_ids = allowed_restaurant_ids(user, all_ids)
restos_df = restos_df[restos_df["id"].isin(user_ids)].reset_index(drop=True)
if restos_df.empty:
    st.error(
        "Ton compte n'a accès à aucun restaurant. "
        "Contacte un administrateur pour étendre tes droits."
    )
    st.stop()

# ------------------------------------------------------------------
# Filtres globaux
# ------------------------------------------------------------------
fc1, fc2 = st.columns([1.2, 3])

with fc1:
    preset = st.selectbox("Période", periods.PRESETS, index=0, key="period_preset")
    custom_range = None
    if preset == "Personnalisé":
        today = date.today()
        custom_range = st.date_input(
            "Plage",
            value=(today.replace(day=1), today),
            key="period_custom",
            format="DD/MM/YYYY",
        )
        if not isinstance(custom_range, tuple) or len(custom_range) != 2:
            st.info("Sélectionne une date de début ET de fin.")
            st.stop()
    period = periods.from_preset(preset, custom_range)

with fc2:
    all_names = restos_df["name"].tolist()
    selected_names = st.multiselect(
        "Restaurants",
        all_names,
        default=all_names,
        key="restos",
    )

if not selected_names:
    st.warning("Sélectionne au moins un restaurant.")
    st.stop()

selected_ids = tuple(
    restos_df.loc[restos_df["name"].isin(selected_names), "id"].astype(int).tolist()
)
id_to_name = dict(zip(restos_df["id"], restos_df["name"]))

st.caption(
    f"Période : **{period.start:%d/%m/%Y} → {period.end:%d/%m/%Y}** "
    f"({period.days} j) · {len(selected_names)}/{len(all_names)} restaurants"
)

# ------------------------------------------------------------------
# Onglets
# ------------------------------------------------------------------
tab_reseau, tab_produits = st.tabs(["RÉSEAU", "PRODUITS"])

# =============================================================================
# TAB 1 — Réseau (depuis closures + orders)
# =============================================================================
with tab_reseau:
    with st.spinner(f"Récupération CA · {len(selected_ids)} restos · {period.days} j…"):
        try:
            closures = zelty_client.fetch_closures(selected_ids, period.start, period.end)
        except zelty_client.ZeltyError as e:
            st.error(f"Closures: {e}")
            closures = pd.DataFrame()

        try:
            orders = zelty_client.fetch_orders_summary(selected_ids, period.start, period.end)
        except zelty_client.ZeltyError as e:
            st.warning(f"Orders: {e}")
            orders = pd.DataFrame()

    if closures.empty and orders.empty:
        st.info("Aucune donnée sur cette période pour les restaurants sélectionnés.")
        st.stop()

    # KPIs
    total_ttc = closures["turnover"].sum() if not closures.empty else orders["ttc"].sum()
    total_taxes = closures["taxes"].sum() if not closures.empty else 0
    total_ht = (total_ttc - total_taxes) if total_taxes else orders.get("ht", pd.Series(dtype=float)).sum()
    n_orders = len(orders)
    ticket_moyen = (total_ttc / n_orders) if n_orders else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("CA TTC réseau", f"{total_ttc/1000:,.1f} K€".replace(",", " "))
    k2.metric("CA HT", f"{total_ht/1000:,.1f} K€".replace(",", " ") if total_ht else "—")
    k3.metric("Commandes", f"{n_orders:,}".replace(",", " ") if n_orders else "—")
    k4.metric("Ticket moyen", f"{ticket_moyen:.2f} €" if ticket_moyen else "—")

    # Tableau par restaurant
    if not closures.empty:
        per_resto = (
            closures.groupby("restaurant_id")
            .agg(ca_ttc=("turnover", "sum"), taxes=("taxes", "sum"), jours=("date", "nunique"))
            .reset_index()
        )
        per_resto["nom"] = per_resto["restaurant_id"].map(id_to_name)
        per_resto["ca_ht"] = per_resto["ca_ttc"] - per_resto["taxes"]
        per_resto["pct"] = per_resto["ca_ttc"] / per_resto["ca_ttc"].sum() * 100
        if not orders.empty:
            cmd_count = orders.groupby("restaurant_id").size().rename("cmds")
            per_resto = per_resto.merge(cmd_count, on="restaurant_id", how="left").fillna({"cmds": 0})
            per_resto["ticket_moyen"] = per_resto.apply(
                lambda r: r["ca_ttc"] / r["cmds"] if r["cmds"] else 0, axis=1
            )
        per_resto = per_resto.sort_values("ca_ttc", ascending=False).reset_index(drop=True)

        rows = per_resto.to_dict("records")
        columns = [
            {"key": "ca_ttc", "label": "CA TTC", "fmt": "eur", "highlight": True},
            {"key": "ca_ht", "label": "CA HT", "fmt": "eur"},
            {"key": "cmds", "label": "CMDS", "fmt": "int"},
            {"key": "ticket_moyen", "label": "TICKET MOY.", "fmt": "money2"},
            {"key": "pct", "label": "% CA", "fmt": "pct"},
            {"key": "jours", "label": "JOURS", "fmt": "days"},
        ]
        # Filtrer colonnes absentes (ex: orders pas dispo)
        columns = [c for c in columns if c["key"] in per_resto.columns]
        footer = {
            "ca_ttc": per_resto["ca_ttc"].sum(),
            "ca_ht": per_resto["ca_ht"].sum() if "ca_ht" in per_resto.columns else None,
            "cmds": per_resto["cmds"].sum() if "cmds" in per_resto.columns else None,
            "ticket_moyen": (per_resto["ca_ttc"].sum() / per_resto["cmds"].sum())
                if "cmds" in per_resto.columns and per_resto["cmds"].sum() else None,
            "pct": 100.0,
            "jours": per_resto["jours"].max() if "jours" in per_resto.columns else None,
        }
        render_ranking_table(rows, columns, spark_field="ca_ttc", footer=footer)

        # Évolution CA par jour
        st.markdown("---")
        st.markdown(
            f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:6px;'>"
            f"CA quotidien · réseau</div>",
            unsafe_allow_html=True,
        )
        daily = (
            closures.assign(nom=closures["restaurant_id"].map(id_to_name))
            .groupby(["date", "nom"], as_index=False)["turnover"].sum()
        )
        fig = px.area(
            daily,
            x="date", y="turnover", color="nom",
            color_discrete_sequence=px.colors.sequential.Sunsetdark,
        )
        fig.update_layout(
            paper_bgcolor=COLORS["bg"],
            plot_bgcolor=COLORS["surface"],
            font=dict(family="Poppins, sans-serif", color=COLORS["white"]),
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(gridcolor=COLORS["border"], title=None),
            yaxis=dict(gridcolor=COLORS["border"], title="CA TTC (€)"),
            legend=dict(orientation="h", yanchor="bottom", y=-0.25, font=dict(size=10)),
            height=380,
        )
        st.plotly_chart(fig, use_container_width=True)

# =============================================================================
# TAB 2 — Produits (CSV fallback — l'endpoint Zelty dishes n'est pas trouvé)
# =============================================================================
with tab_produits:
    st.markdown(
        f"<div style='background:{COLORS['surface']};border:1px solid {COLORS['border']};"
        f"border-radius:10px;padding:12px 16px;margin-bottom:18px;'>"
        f"<div style='color:{COLORS['coral']};font-size:11px;font-weight:600;"
        f"letter-spacing:0.1em;text-transform:uppercase;margin-bottom:6px;'>"
        f"⚠ Données produit · mode CSV</div>"
        f"<div style='color:{COLORS['muted']};font-size:12px;line-height:1.5;'>"
        f"L'API Zelty v2.10 ne semble pas exposer les ventes par produit via les endpoints standards "
        f"(<code>/orders</code> ne renvoie que des résumés). En attendant d'identifier le bon endpoint, "
        f"importe ici les exports CSV <em>Les Produits</em> du back-office Zelty.</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Initialisation du store CSV en session
    if "csv_data" not in st.session_state:
        st.session_state["csv_data"] = {}  # {restaurant_name: dataframe}

    uploaded = st.file_uploader(
        "Importer un ou plusieurs CSV Zelty (un par restaurant)",
        type=["csv"],
        accept_multiple_files=True,
        key="csv_upload",
    )

    if uploaded:
        for f in uploaded:
            try:
                text = f.read().decode("latin1", errors="replace")
                df = zelty_client.parse_zelty_csv(text)
                if not df.empty:
                    # Tente de matcher le nom du resto sur le nom du fichier
                    matched = None
                    fname_lower = f.name.lower()
                    for name in all_names:
                        if name.lower().replace("kajiro", "").strip() in fname_lower:
                            matched = name
                            break
                    label = matched or f.name
                    st.session_state["csv_data"][label] = df
            except Exception as e:  # noqa: BLE001
                st.error(f"{f.name} — {e}")

    csv_data: dict[str, pd.DataFrame] = st.session_state["csv_data"]

    if not csv_data:
        st.info("Importe les CSV pour voir les best sellers réseau (ou par restaurant).")
        st.stop()

    # Sélecteur sites CSV
    csv_keys = list(csv_data.keys())
    selected_csv = st.multiselect(
        "Restaurants à inclure (CSV importés)",
        csv_keys,
        default=csv_keys,
    )

    if not selected_csv:
        st.stop()

    # Fusion
    merged: dict[str, dict[str, float]] = {}
    for k in selected_csv:
        for _, row in csv_data[k].iterrows():
            acc = merged.setdefault(row["nom"], {"qte": 0.0, "ht": 0.0})
            acc["qte"] += row["qte"]
            acc["ht"] += row["ht"]
    data = pd.DataFrame([
        {"nom": n, "qte": int(v["qte"]), "ht": v["ht"],
         "prix_moy": v["ht"] / v["qte"] if v["qte"] else 0}
        for n, v in merged.items()
    ])
    total_ht = data["ht"].sum() or 1
    data["pct_ca"] = data["ht"] / total_ht * 100

    # Contrôles tri / topN / recherche
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        search = st.text_input("Rechercher", "", placeholder="Filtrer par nom…", label_visibility="collapsed")
    with c2:
        top_n = st.selectbox(
            "Top N", TOP_PRESETS + [9999], index=2,
            format_func=lambda n: "TOUT" if n == 9999 else f"TOP {n}",
        )
    with c3:
        sort_by = st.selectbox(
            "Trier par", ["ht", "qte", "prix_moy", "pct_ca"],
            format_func={"ht": "CA HT", "qte": "Unités", "prix_moy": "Prix moy.", "pct_ca": "% CA"}.get,
        )
    with c4:
        sort_dir = st.selectbox(
            "Sens", ["desc", "asc"],
            format_func={"desc": "↓", "asc": "↑"}.get,
        )

    filtered = data.copy()
    if search:
        filtered = filtered[filtered["nom"].str.contains(search, case=False, na=False)]
    filtered = filtered.sort_values(sort_by, ascending=(sort_dir == "asc")).reset_index(drop=True)
    if top_n != 9999:
        filtered = filtered.head(top_n)

    # Enrichissement avec photos depuis le catalogue Zelty
    try:
        catalog = zelty_client.fetch_catalog_items()
        filtered = zelty_client.match_csv_to_catalog(filtered, catalog)
        nb_matched = (filtered["img"].astype(bool)).sum()
        if nb_matched:
            st.caption(f"📷 {nb_matched}/{len(filtered)} produits enrichis avec photo depuis le catalogue Zelty.")
    except zelty_client.ZeltyError as e:
        st.caption(f"Catalogue non chargé : {e}")
        filtered["img"] = ""

    # KPIs produits
    pk1, pk2, pk3, pk4 = st.columns(4)
    pk1.metric("CA HT total", f"{total_ht/1000:,.1f} K€".replace(",", " "))
    pk2.metric("Unités", f"{int(data['qte'].sum()):,}".replace(",", " "))
    pk3.metric("Références", f"{len(data)}")
    pk4.metric(f"Top {len(filtered)} couvre", f"{(filtered['ht'].sum()/total_ht*100):.1f}%")

    # Table produits avec photos
    render_product_table(filtered.to_dict("records"), sort_key=sort_by, show_photos=True)

    # Chart
    chart_n = min(20, len(filtered))
    if chart_n > 0:
        st.markdown("---")
        col_value = "qte" if sort_by == "qte" else "ht"
        chart_data = filtered.head(chart_n).iloc[::-1]
        fig = px.bar(
            chart_data, x=col_value, y="nom", orientation="h",
            color_discrete_sequence=[COLORS["coral"]],
        )
        fig.update_layout(
            paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["surface"],
            font=dict(family="Poppins, sans-serif", color=COLORS["white"]),
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(gridcolor=COLORS["border"], title=None),
            yaxis=dict(gridcolor=COLORS["border"], title=None, tickfont=dict(size=11)),
            height=max(280, chart_n * 22), showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Kajirō Analytics")
    # User card
    if user.get("picture"):
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;padding:8px 0;'>"
            f"<img src='{user['picture']}' style='width:32px;height:32px;border-radius:50%;border:1px solid {COLORS['border']};'>"
            f"<div><div style='color:{COLORS['white']};font-size:12px;font-weight:600;'>{user['name']}</div>"
            f"<div style='color:{COLORS['muted']};font-size:10px;letter-spacing:0.05em;'>{user['role'].upper()}</div></div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div style='color:{COLORS['white']};font-size:12px;'>{user['name']}</div>"
            f"<div style='color:{COLORS['muted']};font-size:10px;'>{user['role'].upper()} · {user['email']}</div>",
            unsafe_allow_html=True,
        )
    st.markdown(
        f"<div style='color:{COLORS['muted']};font-size:11px;margin-top:8px;'>"
        f"{len(restos_df)} restaurants · Zelty v{zelty_client.API_VERSION}"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    if st.button("🔄 Refetch today"):
        st.cache_data.clear()
        st.rerun()
    if st.button("🗑️ Vider tout le cache"):
        cache.clear_all()
        st.cache_data.clear()
        st.rerun()

    # Section Admin
    if user.get("role") == "admin":
        st.markdown("---")
        st.markdown(
            f"<div style='color:{COLORS['muted']};font-size:10px;letter-spacing:0.12em;text-transform:uppercase;'>"
            f"Administration</div>",
            unsafe_allow_html=True,
        )
        if st.button("👥 Gérer les utilisateurs", use_container_width=True):
            users_dialog(all_restos_df.to_dict("records"))

        years = st.select_slider("Backfill (années)", options=[1, 2, 3, 4, 5, 6, 7], value=5, key="bf_years")
        if st.button(f"🕰️ Backfill {years} an(s)", help="Long ~30-60 min. Garde l'onglet ouvert."):
            progress_bar = st.progress(0)
            status = st.empty()
            all_ids = restos_df["id"].astype(int).tolist()

            def _cb(done: int, total: int, msg: str) -> None:
                if total:
                    progress_bar.progress(min(1.0, done / total))
                status.text(f"{done}/{total} — {msg}")

            try:
                stats = backfill.run_backfill(all_ids, years=years, callback=_cb)
                st.success(f"✅ Fini ! {stats.get('orders')} commandes, {stats.get('closures')} closures.")
            except Exception as e:  # noqa: BLE001
                st.error(f"Backfill interrompu : {e}")
            st.cache_data.clear()

    st.markdown("---")
    if st.button("Déconnexion"):
        logout()
        st.rerun()
    st.markdown("---")

    # Cache stats
    s = cache.stats()
    st.markdown(
        f"<div style='font-size:11px;color:{COLORS['muted']};line-height:1.6;'>"
        f"<b>Cache local SQLite</b><br>"
        f"📅 {s['synced_days']} jours sync<br>"
        f"🧾 {s['orders']} commandes<br>"
        f"💰 {s['closures']} closures<br>"
        f"{('📊 ' + s['oldest'] + ' → ' + s['newest']) if s['oldest'] else ''}"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    ok, msg = zelty_client.health_check()
    icon = "🟢" if ok else "🔴"
    st.markdown(
        f"<div style='font-size:11px;color:{COLORS['muted']};'>{icon} {msg}</div>",
        unsafe_allow_html=True,
    )
