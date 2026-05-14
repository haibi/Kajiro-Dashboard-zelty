"""Kajirō Dashboard — analytics réseau multi-restaurants depuis l'API Zelty (v2.10)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

import backfill
import cache
import copilots
import periods
import zelty_client
from auth import allowed_restaurant_ids, logout, require_login
from components import render_product_table, render_ranking_table
from theme import COLORS, header, inject_css

FAVICON = Path(__file__).parent / "Images" / "favicon.svg"

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
        current_rids = set(
            int(r) for r in ((existing or {}).get("restaurant_ids") or [])
        )
        chosen_names = st.multiselect(
            "Restaurants autorisés",
            options=[r["name"] for r in all_restos],
            default=[r["name"] for r in all_restos if r["id"] in current_rids],
        )
        selected_rids = [r["id"] for r in all_restos if r["name"] in chosen_names]

    # Mot de passe
    if existing:
        password = st.text_input(
            "Nouveau mot de passe (vide = ne pas changer)",
            type="password",
            help="Laisse vide si tu ne veux pas changer le mot de passe actuel.",
        )
    else:
        password = st.text_input(
            "Mot de passe initial",
            type="password",
            help="Mot de passe que l'utilisateur devra utiliser pour se connecter. "
                 "Il pourra le changer plus tard.",
        )

    cs, cc = st.columns(2)
    if cs.button("💾 Enregistrer", type="primary", use_container_width=True):
        try:
            # Pour un nouvel utilisateur on EXIGE un mot de passe
            if not existing and not password:
                st.error("Mot de passe requis pour un nouvel utilisateur.")
            else:
                cache.upsert_user(email, role, selected_rids,
                                    password=password if password else None)
                st.session_state.pop("edit_user", None)
                st.success(f"✅ {email} enregistré")
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
    initial_sidebar_state="expanded",
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
# Boutons période rapide
# ("Jour", "Aujourd'hui") désactivé pour l'instant — sera dispo quand on aura le live
QUICK_PERIODS = [
    ("Jour", "Aujourd'hui", True),   # disabled
    ("Semaine", "Cette semaine", False),
    ("Mois", "Mois en cours", False),
    ("M-1", "Mois précédent", False),
    ("Année", "Année en cours", False),
    ("Perso", "Personnalisé", False),
]
if "period_preset" not in st.session_state:
    st.session_state["period_preset"] = "Mois en cours"

st.markdown(
    f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.12em;"
    f"text-transform:uppercase;margin-bottom:6px;'>Période</div>",
    unsafe_allow_html=True,
)
period_cols = st.columns(len(QUICK_PERIODS) + 2)
for i, (label, value, disabled) in enumerate(QUICK_PERIODS):
    is_active = st.session_state["period_preset"] == value
    if period_cols[i].button(
        label,
        key=f"period_btn_{value}",
        use_container_width=True,
        type="primary" if is_active else "secondary",
        disabled=disabled,
        help="Bientôt — nécessite le sync temps réel" if disabled else None,
    ):
        st.session_state["period_preset"] = value
        st.rerun()

preset = st.session_state["period_preset"]
custom_range = None
if preset == "Personnalisé":
    today = date.today()
    custom_range = st.date_input(
        "Plage",
        value=(today.replace(day=1), today),
        key="period_custom",
        format="DD/MM/YYYY",
        label_visibility="collapsed",
    )
    if not isinstance(custom_range, tuple) or len(custom_range) != 2:
        st.info("Sélectionne une date de début ET de fin.")
        st.stop()
period = periods.from_preset(preset, custom_range)

# Sélection restaurants (pills cliquables — toutes visibles d'un coup d'œil)
all_names = restos_df["name"].tolist()

# Init session state à tous au premier passage
if "restos_pills" not in st.session_state:
    st.session_state["restos_pills"] = list(all_names)

header_cols = st.columns([3, 1, 1])
with header_cols[0]:
    st.markdown(
        f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.12em;"
        f"text-transform:uppercase;margin:14px 0 6px;'>Restaurants</div>",
        unsafe_allow_html=True,
    )
with header_cols[1]:
    if st.button("✓ Tous", key="restos_all", use_container_width=True):
        st.session_state["restos_pills"] = list(all_names)
        st.rerun()
with header_cols[2]:
    if st.button("✕ Aucun", key="restos_none", use_container_width=True):
        st.session_state["restos_pills"] = []
        st.rerun()

selected_names = st.pills(
    "Restaurants",
    all_names,
    selection_mode="multi",
    key="restos_pills",
    label_visibility="collapsed",
) or []

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
tab_dashboard, tab_produits, tab_freq, tab_sources, tab_clients, tab_board = st.tabs(
    ["DASHBOARD", "PRODUITS", "FRÉQUENTATION", "ORIGINES", "CLIENTS", "BOARD"]
)

# =============================================================================
# TAB 1 — Réseau (depuis closures + orders)
# =============================================================================
with tab_dashboard:
    closures = zelty_client.fetch_closures(selected_ids, period.start, period.end)
    orders = zelty_client.fetch_orders_summary(selected_ids, period.start, period.end)

    # Période précédente comparable (même durée juste avant)
    prev = periods.previous_comparable(period)
    orders_prev = zelty_client.fetch_orders_summary(selected_ids, prev.start, prev.end)

    if closures.empty and orders.empty:
        st.info("Aucune donnée en cache pour cette période. Clique 🔄 Sync today dans le sidebar pour aujourd'hui.")
        st.stop()

    # KPIs courants — orders comme source de vérité
    total_ttc = orders["ttc"].sum() if not orders.empty else 0
    total_ht = orders["ht"].sum() if not orders.empty else 0
    n_orders = len(orders)
    ticket_moyen = (total_ttc / n_orders) if n_orders else 0

    # KPIs période précédente
    p_ttc = orders_prev["ttc"].sum() if not orders_prev.empty else 0
    p_ht = orders_prev["ht"].sum() if not orders_prev.empty else 0
    p_n = len(orders_prev)
    p_tm = (p_ttc / p_n) if p_n else 0

    def _delta(curr, prev_v):
        if not prev_v:
            return None
        d = (curr - prev_v) / prev_v * 100
        return f"{d:+.1f}%"

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("CA TTC réseau", f"{total_ttc/1000:,.1f} K€".replace(",", " "),
              _delta(total_ttc, p_ttc), help=f"Période précédente : {p_ttc/1000:,.1f} K€".replace(",", " "))
    k2.metric("CA HT", f"{total_ht/1000:,.1f} K€".replace(",", " ") if total_ht else "—",
              _delta(total_ht, p_ht), help=f"Période précédente : {p_ht/1000:,.1f} K€".replace(",", " "))
    k3.metric("Commandes", f"{n_orders:,}".replace(",", " ") if n_orders else "—",
              _delta(n_orders, p_n), help=f"Période précédente : {p_n}")
    k4.metric("Ticket moyen", f"{ticket_moyen:.2f} €" if ticket_moyen else "—",
              _delta(ticket_moyen, p_tm), help=f"Période précédente : {p_tm:.2f} €")
    st.caption(
        f"vs période précédente : {prev.start:%d/%m} → {prev.end:%d/%m} ({prev.days} j)"
    )

    # Copilote Dashboard
    co = copilots.dashboard_copilot(orders, orders_prev, period.days)
    copilots.render_copilot_card("Réseau", co["status"], co["message"], co["recommendation"])

    # === Indicateurs clients & remises (si data dispo) ===
    if not orders.empty and "customer_id" in orders.columns:
        n_identified = orders["customer_id"].notna().sum()
        n_anonymous = orders["customer_id"].isna().sum()
        pct_anon = (n_anonymous / len(orders) * 100) if len(orders) else 0
        anon_ca = orders.loc[orders["customer_id"].isna(), "ttc"].sum()
        disc_total = orders["discount_ttc"].sum() if "discount_ttc" in orders.columns else 0
        disc_count = int(orders["discount_count"].sum()) if "discount_count" in orders.columns else 0

        ci1, ci2, ci3, ci4 = st.columns(4)
        ci1.metric("Clients identifiés", f"{int(n_identified):,}".replace(",", " "))
        ci2.metric("Cmds anonymes", f"{int(n_anonymous):,}".replace(",", " "),
                    f"{pct_anon:.0f} % du volume",
                    delta_color="off")
        ci3.metric("CA anonyme", f"{anon_ca/1000:,.1f} K€".replace(",", " "),
                    "💡 fidéliser ces clients", delta_color="off")
        ci4.metric("Remises", f"{disc_total:,.0f} €".replace(",", " "),
                    f"{disc_count} actions", delta_color="off")
    else:
        st.caption("⏳ Données clients & remises en cours de synchronisation (re-backfill avec expand[]=customer,user,price.discounts)")

    # Tableau par restaurant — source de vérité = orders (closures juste pour jours)
    if not orders.empty:
        per_resto = orders.groupby("restaurant_id").agg(
            ca_ttc=("ttc", "sum"),
            ca_ht=("ht", "sum"),
            cmds=("order_id", "count"),
        ).reset_index()
        per_resto["nom"] = per_resto["restaurant_id"].map(id_to_name)
        per_resto["ticket_moyen"] = per_resto.apply(
            lambda r: r["ca_ttc"] / r["cmds"] if r["cmds"] else 0, axis=1
        )
        per_resto["pct"] = per_resto["ca_ttc"] / per_resto["ca_ttc"].sum() * 100
        if not closures.empty:
            jours_clos = closures.groupby("restaurant_id")["date"].nunique().rename("jours")
            per_resto = per_resto.merge(jours_clos, on="restaurant_id", how="left").fillna({"jours": 0})
            per_resto["jours"] = per_resto["jours"].astype(int)
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
# TAB 2 — Produits (LIVE depuis order_items synchronisé avec expand[]=items)
# =============================================================================
with tab_produits:
    data = zelty_client.fetch_product_sales(selected_ids, period.start, period.end)

    if data.empty:
        st.info(
            "Aucune ligne produit en cache sur cette période. "
            "Si tu viens d'ajouter de la donnée, attends que le backfill termine, "
            "ou clique 🔄 Refetch today dans le sidebar."
        )
        st.stop()

    total_ht = data["ht"].sum() or 1

    # Header : titre + toggles à droite (style Bron)
    htop, hctl = st.columns([2, 3])
    with htop:
        st.markdown(
            f"<div style='color:{COLORS['muted']};font-size:10px;letter-spacing:0.12em;"
            f"text-transform:uppercase;margin-bottom:2px;'>MODULE PRODUITS</div>"
            f"<div style='color:{COLORS['white']};font-size:20px;font-weight:700;margin-bottom:2px;'>"
            f"Top / Flop produits</div>"
            f"<div style='color:{COLORS['muted']};font-size:11px;'>"
            f"{period.start:%a %d %b} → {period.end:%a %d %b} · {len(data)} produits</div>",
            unsafe_allow_html=True,
        )

    # Toggles
    if "prod_view" not in st.session_state:
        st.session_state["prod_view"] = "TOP"
    if "prod_metric" not in st.session_state:
        st.session_state["prod_metric"] = "ht"

    with hctl:
        tc1, tc2, tc3, tc4 = st.columns([1, 1, 1, 1])
        for label, val, key, state_key in [
            ("TOP", "TOP", "top", "prod_view"),
            ("FLOP", "FLOP", "flop", "prod_view"),
            ("CA", "ht", "ca", "prod_metric"),
            ("VOLUME", "qte", "vol", "prod_metric"),
        ]:
            with [tc1, tc2, tc3, tc4][["top", "flop", "ca", "vol"].index(key)]:
                active = st.session_state[state_key] == val
                if st.button(label, key=f"prod_{key}",
                              type="primary" if active else "secondary",
                              use_container_width=True):
                    st.session_state[state_key] = val
                    st.rerun()

    view = st.session_state["prod_view"]       # TOP ou FLOP
    metric = st.session_state["prod_metric"]   # 'ht' ou 'qte'

    # Enrichissement avec catalogue (photos) AVANT filtrage pour avoir les images
    try:
        catalog = zelty_client.fetch_catalog_items()
        data = zelty_client.enrich_sales_with_catalog(data, catalog)
    except zelty_client.ZeltyError:
        data["img"] = ""
        data["description"] = ""

    # Extraction d'une catégorie depuis le préfixe du nom (MP1, PB1, Box4, ...)
    def _category(name: str) -> str:
        import re
        m = re.match(r"^([A-Z]+\d*)", name or "")
        if m:
            prefix = m.group(1)
            mapping = {
                "MP": "Menu Plat", "PB": "Poké Bowl", "Box": "Box", "MM": "Menu",
                "GY": "Gyoza", "KS": "Crispy", "RM": "Ramen", "ME": "Menu Enfant",
            }
            for k, v in mapping.items():
                if prefix.startswith(k):
                    return v
            return prefix
        return "Autre"
    data["category"] = data["nom"].map(_category)
    categories = ["Toutes"] + sorted(data["category"].dropna().unique().tolist())

    # Filtres: catégorie / recherche / top N
    fc1, fc2, fc3 = st.columns([2, 3, 1])
    with fc1:
        chosen_cat = st.selectbox(
            "Catégorie", categories, index=0,
            label_visibility="collapsed",
        )
    with fc2:
        search = st.text_input("Rechercher", "", placeholder="Filtrer par nom de produit…",
                                label_visibility="collapsed")
    with fc3:
        top_n = st.selectbox(
            "Combien", [10, 20, 50, 100, 9999], index=1,
            format_func=lambda n: "Tout" if n == 9999 else f"Top {n}",
            label_visibility="collapsed",
        )

    filtered = data.copy()
    if chosen_cat != "Toutes":
        filtered = filtered[filtered["category"] == chosen_cat]
    if search:
        filtered = filtered[filtered["nom"].str.contains(search, case=False, na=False)]
    filtered = filtered.sort_values(metric, ascending=(view == "FLOP")).reset_index(drop=True)
    if top_n != 9999:
        filtered = filtered.head(top_n)

    # KPIs
    pk1, pk2, pk3, pk4 = st.columns(4)
    pk1.metric("CA HT total", f"{total_ht/1000:,.1f} K€".replace(",", " "))
    pk2.metric("Unités", f"{int(data['qte'].sum()):,}".replace(",", " "))
    pk3.metric("Références", f"{len(data)}")
    pk4.metric(f"Couverture {view} {len(filtered)}",
                f"{(filtered[metric].sum()/data[metric].sum()*100):.1f} %")

    st.markdown("")
    render_product_table(filtered.to_dict("records"), sort_key=metric, show_photos=True)

    # Copilote Produits
    co = copilots.products_copilot(data, period.days, len(selected_ids))
    copilots.render_copilot_card("Produits", co["status"], co["message"], co["recommendation"])

    # =========================================================================
    # COPILOTE PRODUITS — identifie les sous-performants + lecture de complexité
    # =========================================================================
    st.markdown("---")
    st.markdown(
        f"<div style='color:{COLORS['muted']};font-size:10px;letter-spacing:0.14em;"
        f"text-transform:uppercase;margin-bottom:4px;'>● COPILOTE</div>"
        f"<div style='color:{COLORS['white']};font-size:16px;font-weight:700;margin-bottom:10px;'>"
        f"Analyse de la carte</div>",
        unsafe_allow_html=True,
    )

    # Règle: produit sous-performant = < 300 € HT / mois / restaurant en moyenne
    n_restos = len(selected_ids)
    n_mois = max(1, period.days / 30.4)
    threshold_ht = 300 * n_mois * n_restos  # seuil ajusté à la période + au nb de restos
    losers = data[data["ht"] < threshold_ht].sort_values("ht").reset_index(drop=True)
    n_total = len(data)
    n_losers = len(losers)
    pct_losers = (n_losers / n_total * 100) if n_total else 0

    # CA capté par les sous-performants
    ca_losers = losers["ht"].sum()
    pct_ca_losers = (ca_losers / (data["ht"].sum() or 1)) * 100

    # Couverture du top 20
    top20 = data.sort_values("ht", ascending=False).head(20)
    pct_ca_top20 = (top20["ht"].sum() / (data["ht"].sum() or 1)) * 100

    # Synthèse
    cc1, cc2, cc3 = st.columns(3)
    cc1.metric("Carte totale", f"{n_total} produits")
    cc2.metric("Sous-performants", f"{n_losers}", f"{pct_losers:.0f}% de la carte")
    cc3.metric("CA capté par top 20", f"{pct_ca_top20:.0f} %")

    if n_total > 100:
        complexity = "🔴 Carte trop dense"
        complexity_txt = (
            f"**{n_total} produits actifs**, c'est lourd à gérer en cuisine et "
            f"diluer la mémorisation client. Les 20 meilleurs captent **{pct_ca_top20:.0f}% du CA** — "
            f"signe qu'une moitié de carte tire toute la performance."
        )
    elif n_total > 60:
        complexity = "🟠 Carte un peu dense"
        complexity_txt = (
            f"**{n_total} produits**, dans la zone haute. À surveiller : si le top 20 "
            f"fait > 80% du CA, c'est un signal pour simplifier."
        )
    else:
        complexity = "🟢 Carte saine"
        complexity_txt = f"**{n_total} produits**, taille raisonnable. Suivi standard."

    st.markdown(
        f"<div style='background:{COLORS['surface']};border:1px solid {COLORS['border']};"
        f"border-radius:10px;padding:14px 16px;margin-top:12px;'>"
        f"<div style='color:{COLORS['coral']};font-size:13px;font-weight:700;margin-bottom:6px;'>"
        f"{complexity}</div>"
        f"<div style='color:{COLORS['white']};font-size:13px;line-height:1.6;'>{complexity_txt}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if n_losers > 0:
        st.markdown("")
        st.markdown(
            f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.12em;"
            f"text-transform:uppercase;margin:18px 0 8px;'>"
            f"⚠ {n_losers} produits sous le seuil "
            f"(&lt; 300€ HT / mois / resto, soit &lt; {threshold_ht:.0f}€ HT sur la période)"
            f"</div>",
            unsafe_allow_html=True,
        )
        # Top 15 des pires
        worst = losers.head(15).copy()
        worst["mensuel_par_resto"] = worst["ht"] / (n_mois * n_restos)
        recos = []
        for _, r in worst.iterrows():
            recos.append({
                "img": r.get("img", ""),
                "nom": r["nom"],
                "ht": r["ht"],
                "qte": r["qte"],
                "prix_moy": r["prix_moy"],
                "pct_ca": r["pct_ca"],
            })
        render_product_table(recos, sort_key="ht", show_photos=True)
        st.caption(
            f"💡 **Recommandation** : envisager de retirer les {n_losers} produits sous-performants. "
            f"Ils ne représentent que {pct_ca_losers:.1f}% du CA et complexifient la cuisine "
            f"(stock, formation, gestes). Garde-les si ce sont des marqueurs identitaires ou "
            f"des trafic-générateurs (boissons en attente, accompagnements obligatoires)."
        )

    # Chart bar horizontal
    chart_n = min(20, len(filtered))
    if chart_n > 0:
        st.markdown("---")
        chart_data = filtered.head(chart_n).iloc[::-1]
        fig = px.bar(
            chart_data, x=metric, y="nom", orientation="h",
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

    # =========================================================================
    # Tableau remises par employé
    # =========================================================================
    if not orders.empty and "discount_count" in orders.columns:
        disc_orders = orders[orders["discount_count"] > 0]
        if not disc_orders.empty:
            st.markdown("---")
            st.markdown(
                f"<div style='color:{COLORS['muted']};font-size:10px;letter-spacing:0.14em;"
                f"text-transform:uppercase;margin-bottom:4px;'>MODULE</div>"
                f"<div style='color:{COLORS['white']};font-size:18px;font-weight:700;margin-bottom:10px;'>"
                f"Remises par employé</div>",
                unsafe_allow_html=True,
            )
            by_server = (
                disc_orders.assign(server=disc_orders["server_name"].fillna("(non identifié)"))
                .groupby("server")
                .agg(
                    ttc_remise=("discount_ttc", "sum"),
                    nb_remises=("discount_count", "sum"),
                    nb_cmds=("order_id", "count"),
                    ca_total=("ttc", "sum"),
                )
                .reset_index()
                .sort_values("ttc_remise", ascending=False)
            )
            by_server["pct_orders"] = by_server["nb_cmds"] / len(orders) * 100
            by_server["pct_remise_ca"] = by_server["ttc_remise"] / (orders["ttc"].sum() or 1) * 100

            max_disc = by_server["ttc_remise"].max() or 1
            for _, r in by_server.iterrows():
                bar = (r["ttc_remise"] / max_disc) * 100
                st.markdown(
                    f"<div style='padding:10px 0;border-bottom:1px solid {COLORS['border']};'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;'>"
                    f"<div><div style='color:{COLORS['white']};font-size:13px;font-weight:600;'>{r['server']}</div>"
                    f"<div style='color:{COLORS['muted']};font-size:11px;'>"
                    f"{int(r['nb_remises'])} remises sur {int(r['nb_cmds'])} cmds · {r['pct_remise_ca']:.1f} % du CA</div></div>"
                    f"<div style='text-align:right;color:{COLORS['coral']};font-size:14px;font-weight:700;'>"
                    f"−{r['ttc_remise']:,.0f} €</div></div>"
                    f"<div style='width:100%;height:3px;background:{COLORS['dim']};border-radius:2px;'>"
                    f"<div style='width:{bar:.0f}%;height:100%;background:{COLORS['coral']};border-radius:2px;'></div>"
                    f"</div></div>".replace(",", " "),
                    unsafe_allow_html=True,
                )
            # Copilote Remises
            co = copilots.discounts_copilot(orders)
            copilots.render_copilot_card("Remises", co["status"], co["message"], co["recommendation"])

# =============================================================================
# TAB 3 — Fréquentation (jours × heures)
# =============================================================================
DAYS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
DAYS_MAP = {
    "Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi",
    "Thursday": "Jeudi", "Friday": "Vendredi", "Saturday": "Samedi", "Sunday": "Dimanche",
}

with tab_freq:
    if orders.empty:
        st.info("Aucune commande sur la période sélectionnée.")
    else:
        df = orders.copy()
        df["dt"] = pd.to_datetime(df["closed_at"], errors="coerce")
        df = df.dropna(subset=["dt"])
        df["hour"] = df["dt"].dt.hour
        df["day_en"] = df["dt"].dt.day_name()
        df["day"] = df["day_en"].map(DAYS_MAP)

        # Header
        st.markdown(
            f"<div style='color:{COLORS['muted']};font-size:10px;letter-spacing:0.12em;"
            f"text-transform:uppercase;margin-bottom:2px;'>MODULE FRÉQUENTATION</div>"
            f"<div style='color:{COLORS['white']};font-size:20px;font-weight:700;margin-bottom:6px;'>"
            f"Quand viennent les clients</div>"
            f"<div style='color:{COLORS['muted']};font-size:11px;margin-bottom:14px;'>"
            f"{period.start:%a %d %b} → {period.end:%a %d %b} · {len(df):,} commandes</div>".replace(",", " "),
            unsafe_allow_html=True,
        )

        # === KPIs ===
        peak_hour = df.groupby("hour").size().idxmax() if not df.empty else 0
        peak_day = df.groupby("day").size().reindex(DAYS_FR, fill_value=0).idxmax()
        avg_per_day = df.groupby(df["dt"].dt.date).size().mean()
        weekend_share = df[df["day"].isin(["Samedi", "Dimanche"])].shape[0] / len(df) * 100

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Pic horaire", f"{peak_hour}h")
        k2.metric("Pic jour", peak_day)
        k3.metric("Cmds / jour (moy.)", f"{avg_per_day:.0f}")
        k4.metric("Week-end", f"{weekend_share:.0f} %")

        st.markdown("---")

        # === 2 charts côte à côte : heures + jours ===
        cc1, cc2 = st.columns(2)

        with cc1:
            st.markdown(
                f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.1em;"
                f"text-transform:uppercase;margin-bottom:4px;'>Heures de visite</div>",
                unsafe_allow_html=True,
            )
            hours_df = df.groupby("hour").size().reset_index(name="n")
            hours_df = hours_df[hours_df["n"] > 0]
            fig_h = px.bar(hours_df, x="hour", y="n",
                            color_discrete_sequence=[COLORS["coral"]])
            fig_h.update_layout(
                paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["surface"],
                font=dict(family="Poppins, sans-serif", color=COLORS["white"]),
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis=dict(gridcolor=COLORS["border"], title="Heure",
                            tickmode="linear", tick0=0, dtick=1),
                yaxis=dict(gridcolor=COLORS["border"], title="Commandes"),
                height=300, showlegend=False,
            )
            st.plotly_chart(fig_h, use_container_width=True)

        with cc2:
            st.markdown(
                f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.1em;"
                f"text-transform:uppercase;margin-bottom:4px;'>Jours de la semaine</div>",
                unsafe_allow_html=True,
            )
            days_df = df.groupby("day").size().reindex(DAYS_FR, fill_value=0).reset_index(name="n")
            fig_d = px.bar(days_df, x="day", y="n",
                            color_discrete_sequence=[COLORS["amber"]])
            fig_d.update_layout(
                paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["surface"],
                font=dict(family="Poppins, sans-serif", color=COLORS["white"]),
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis=dict(gridcolor=COLORS["border"], title=None),
                yaxis=dict(gridcolor=COLORS["border"], title="Commandes"),
                height=300, showlegend=False,
            )
            st.plotly_chart(fig_d, use_container_width=True)

        # === Heatmap ===
        st.markdown(
            f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.1em;"
            f"text-transform:uppercase;margin:8px 0 4px;'>Cartographie horaire · jour × heure</div>",
            unsafe_allow_html=True,
        )
        heat = (
            df.groupby(["day", "hour"]).size()
            .unstack(fill_value=0)
            .reindex(DAYS_FR)
            .fillna(0)
            .astype(int)
        )
        # Ne garder que les heures avec des commandes
        active_hours = [h for h in heat.columns if heat[h].sum() > 0]
        heat = heat[active_hours] if active_hours else heat
        fig_heat = px.imshow(
            heat.values,
            x=[f"{h}h" for h in heat.columns],
            y=heat.index.tolist(),
            color_continuous_scale=[[0, COLORS["bg"]], [0.5, COLORS["coral_dim"]], [1, COLORS["amber"]]],
            aspect="auto",
            text_auto=True,
        )
        fig_heat.update_layout(
            paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["surface"],
            font=dict(family="Poppins, sans-serif", color=COLORS["white"], size=11),
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(title=None, side="bottom"),
            yaxis=dict(title=None),
            coloraxis_colorbar=dict(title="Cmds"),
            height=320,
        )
        fig_heat.update_traces(textfont=dict(size=10))
        st.plotly_chart(fig_heat, use_container_width=True)

        co = copilots.frequentation_copilot(orders)
        copilots.render_copilot_card("Fréquentation", co["status"], co["message"], co["recommendation"])


# =============================================================================
# TAB 4 — Origines des ventes (canaux)
# =============================================================================
SOURCE_LABELS = {
    "pos": "Sur place / POS",
    "kiosk": "Borne",
    "web": "Site web Zelty",
    "ubereats": "UberEats",
    "deliveroo": "Deliveroo",
    "phone": "Téléphone",
    "kiosq": "Borne",
}
MODE_LABELS = {
    "eat_in": "Sur place",
    "takeaway": "À emporter",
    "delivery": "Livraison",
    "click_and_collect": "C&C",
}

with tab_sources:
    if orders.empty:
        st.info("Aucune commande sur la période sélectionnée.")
    else:
        df = orders.copy()
        df["source_label"] = df["source"].map(SOURCE_LABELS).fillna(df["source"].fillna("Inconnu"))
        df["mode_label"] = df["mode"].map(MODE_LABELS).fillna(df["mode"].fillna("Inconnu"))

        # Header
        total_ca = df["ttc"].sum()
        st.markdown(
            f"<div style='color:{COLORS['muted']};font-size:10px;letter-spacing:0.12em;"
            f"text-transform:uppercase;margin-bottom:2px;'>MODULE ORIGINES</div>"
            f"<div style='color:{COLORS['white']};font-size:20px;font-weight:700;margin-bottom:6px;'>"
            f"Plateformes &amp; canaux</div>"
            f"<div style='color:{COLORS['muted']};font-size:11px;margin-bottom:14px;'>"
            f"{period.start:%a %d %b} → {period.end:%a %d %b} · {total_ca:,.0f} € TTC · {len(df):,} tickets"
            f"</div>".replace(",", " "),
            unsafe_allow_html=True,
        )

        # === Par source (canal d'entrée) ===
        st.markdown(
            f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.1em;"
            f"text-transform:uppercase;margin:8px 0 6px;'>Par canal d'entrée</div>",
            unsafe_allow_html=True,
        )
        by_src = (
            df.groupby("source_label").agg(ca=("ttc", "sum"), n=("order_id", "count"))
            .reset_index().sort_values("ca", ascending=False)
        )
        by_src["pct"] = by_src["ca"] / by_src["ca"].sum() * 100
        by_src["ticket_moy"] = by_src["ca"] / by_src["n"]

        # Table custom
        max_ca = by_src["ca"].max() or 1
        for _, row in by_src.iterrows():
            pct_bar = (row["ca"] / max_ca) * 100
            st.markdown(
                f"<div style='padding:10px 0;border-bottom:1px solid {COLORS['border']};'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;'>"
                f"<div><div style='color:{COLORS['white']};font-size:14px;font-weight:600;'>{row['source_label']}</div>"
                f"<div style='color:{COLORS['muted']};font-size:11px;'>{int(row['n']):,} tickets · ticket moy. {row['ticket_moy']:.2f} €</div></div>"
                f"<div style='text-align:right;'>"
                f"<div style='color:{COLORS['white']};font-size:15px;font-weight:700;'>{row['ca']:,.0f} €</div>"
                f"<div style='color:{COLORS['coral']};font-size:11px;'>{row['pct']:.1f} % du CA</div>"
                f"</div></div>"
                f"<div style='width:100%;height:3px;background:{COLORS['dim']};border-radius:2px;'>"
                f"<div style='width:{pct_bar:.0f}%;height:100%;background:{COLORS['coral']};border-radius:2px;'></div>"
                f"</div></div>".replace(",", " "),
                unsafe_allow_html=True,
            )

        # === Par mode de consommation ===
        st.markdown(
            f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.1em;"
            f"text-transform:uppercase;margin:24px 0 6px;'>Par mode de consommation</div>",
            unsafe_allow_html=True,
        )
        by_mode = (
            df.groupby("mode_label").agg(ca=("ttc", "sum"), n=("order_id", "count"))
            .reset_index().sort_values("ca", ascending=False)
        )
        by_mode["pct"] = by_mode["ca"] / by_mode["ca"].sum() * 100

        # Donut chart
        fig_donut = px.pie(by_mode, values="ca", names="mode_label", hole=0.6,
                            color_discrete_sequence=[COLORS["coral"], COLORS["amber"], "#8B5CF6", "#06B6D4"])
        fig_donut.update_traces(textposition="outside", textinfo="label+percent",
                                  textfont=dict(family="Poppins", color=COLORS["white"], size=12))
        fig_donut.update_layout(
            paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["surface"],
            font=dict(family="Poppins, sans-serif", color=COLORS["white"]),
            margin=dict(l=10, r=10, t=10, b=10),
            height=320, showlegend=False,
        )
        st.plotly_chart(fig_donut, use_container_width=True)

        co = copilots.sources_copilot(orders)
        copilots.render_copilot_card("Origines", co["status"], co["message"], co["recommendation"])


# =============================================================================
# TAB 5 — Clients (style Bron)
# =============================================================================
with tab_clients:
    if orders.empty or "customer_id" not in orders.columns:
        st.info(
            "Données clients pas encore synchronisées. "
            "Re-backfill avec expand[]=customer en cours."
        )
    else:
        df = orders.copy()
        df_id = df[df["customer_id"].notna()].copy()
        df_an = df[df["customer_id"].isna()].copy()

        st.markdown(
            f"<div style='color:{COLORS['muted']};font-size:10px;letter-spacing:0.12em;"
            f"text-transform:uppercase;margin-bottom:2px;'>MODULE CLIENTS</div>"
            f"<div style='color:{COLORS['white']};font-size:20px;font-weight:700;margin-bottom:6px;'>"
            f"Base clients</div>"
            f"<div style='color:{COLORS['muted']};font-size:11px;margin-bottom:14px;'>"
            f"{period.start:%a %d %b} → {period.end:%a %d %b}</div>",
            unsafe_allow_html=True,
        )

        # Copilote Clients (en haut, vue d'ensemble)
        co = copilots.clients_copilot(orders)
        copilots.render_copilot_card("Clients", co["status"], co["message"], co["recommendation"])

        # === KPIs principaux ===
        n_id = df_id["customer_id"].nunique()
        n_anon_cmds = len(df_an)
        cmd_per_id = df_id.groupby("customer_id").size() if not df_id.empty else pd.Series(dtype=int)
        n_recurrents = int((cmd_per_id >= 2).sum())
        ca_per_id = df_id.groupby("customer_id")["ttc"].sum() if not df_id.empty else pd.Series(dtype=float)
        vip_threshold = ca_per_id.quantile(0.95) if len(ca_per_id) >= 20 else 0
        n_vip = int((ca_per_id >= vip_threshold).sum()) if vip_threshold else 0

        ck1, ck2, ck3, ck4 = st.columns(4)
        ck1.metric("Clients identifiés", f"{n_id:,}".replace(",", " "))
        ck2.metric("Cmds anonymes", f"{n_anon_cmds:,}".replace(",", " "),
                    help="Pas de compte client lié — opportunité de fidélisation")
        ck3.metric("Récurrents (≥ 2 cmds)", f"{n_recurrents:,}".replace(",", " "),
                    f"{(n_recurrents/n_id*100 if n_id else 0):.0f} % des identifiés")
        ck4.metric("VIP (top 5 %)", f"{n_vip:,}".replace(",", " "),
                    f"seuil {vip_threshold:.0f} €" if vip_threshold else "—")

        # === Panier moyen comparaison ===
        st.markdown("---")
        tm_id = df_id["ttc"].sum() / len(df_id) if len(df_id) else 0
        tm_an = df_an["ttc"].sum() / len(df_an) if len(df_an) else 0
        delta_tm = (tm_id - tm_an) / tm_an * 100 if tm_an else None

        st.markdown(
            f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.1em;"
            f"text-transform:uppercase;margin-bottom:6px;'>Panier moyen · identifiés vs anonymes</div>",
            unsafe_allow_html=True,
        )
        pc1, pc2 = st.columns(2)
        pc1.metric("Identifiés", f"{tm_id:.2f} €",
                    f"{delta_tm:+.1f} % vs anonymes" if delta_tm is not None else None)
        pc2.metric("Anonymes", f"{tm_an:.2f} €" if tm_an else "—",
                    "(non identifiés Zelty)")

        # === Répartition par engagement (segments) ===
        if not cmd_per_id.empty:
            st.markdown(
                f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.1em;"
                f"text-transform:uppercase;margin:18px 0 6px;'>Répartition par engagement</div>",
                unsafe_allow_html=True,
            )
            buckets = [
                ("1 cmd", lambda n: n == 1, "#9CA3AF"),
                ("2-4 cmds", lambda n: 2 <= n <= 4, "#60A5FA"),
                ("5-9 cmds", lambda n: 5 <= n <= 9, COLORS["amber"]),
                ("10-15 cmds", lambda n: 10 <= n <= 15, COLORS["coral"]),
                ("> 15 cmds", lambda n: n > 15, "#34D399"),
            ]
            for label, pred, color in buckets:
                count = int(cmd_per_id.apply(pred).sum())
                pct = count / n_id * 100 if n_id else 0
                st.markdown(
                    f"<div style='padding:8px 0;border-bottom:1px solid {COLORS['border']};'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;'>"
                    f"<div style='color:{COLORS['white']};font-size:13px;font-weight:500;'>{label}</div>"
                    f"<div style='color:{COLORS['muted']};font-size:12px;'>"
                    f"<span style='color:{color};font-weight:700;'>{count}</span> · {pct:.1f} %</div></div>"
                    f"<div style='width:100%;height:4px;background:{COLORS['dim']};border-radius:2px;'>"
                    f"<div style='width:{pct:.0f}%;height:100%;background:{color};border-radius:2px;'></div>"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )

        # === Top clients ===
        if not df_id.empty:
            st.markdown(
                f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.1em;"
                f"text-transform:uppercase;margin:24px 0 6px;'>Top 20 clients par CA</div>",
                unsafe_allow_html=True,
            )
            top_clients = (
                df_id.groupby(["customer_id"])
                .agg(name=("customer_name", "first"),
                     ca=("ttc", "sum"),
                     n_cmd=("order_id", "count"))
                .reset_index().sort_values("ca", ascending=False).head(20)
            )
            top_clients["panier"] = top_clients["ca"] / top_clients["n_cmd"]
            for _, r in top_clients.iterrows():
                display_name = r["name"] or f"Client #{int(r['customer_id'])}"
                ca_fmt = f"{r['ca']:,.0f} €".replace(",", " ")
                st.markdown(
                    f"<div style='padding:8px 0;border-bottom:1px solid {COLORS['border']};"
                    f"display:flex;justify-content:space-between;align-items:center;'>"
                    f"<div><div style='color:{COLORS['white']};font-size:13px;font-weight:600;'>"
                    f"{display_name}</div>"
                    f"<div style='color:{COLORS['muted']};font-size:11px;'>"
                    f"{int(r['n_cmd'])} cmds · panier {r['panier']:.2f} €</div></div>"
                    f"<div style='color:{COLORS['coral']};font-size:14px;font-weight:700;'>"
                    f"{ca_fmt}</div></div>",
                    unsafe_allow_html=True,
                )


# =============================================================================
# TAB 6 — BOARD : synthèse globale + plan d'action CT/MT/LT
# =============================================================================
with tab_board:
    products_df = zelty_client.fetch_product_sales(selected_ids, period.start, period.end)
    co_dash = copilots.dashboard_copilot(orders, orders_prev, period.days)
    co_prod = copilots.products_copilot(products_df, period.days, len(selected_ids)) if not products_df.empty else None
    co_freq = copilots.frequentation_copilot(orders)
    co_src = copilots.sources_copilot(orders)
    co_cli = copilots.clients_copilot(orders)
    co_disc = copilots.discounts_copilot(orders)

    st.markdown(
        f"<div style='color:{COLORS['muted']};font-size:10px;letter-spacing:0.12em;"
        f"text-transform:uppercase;margin-bottom:2px;'>BOARD STRATÉGIQUE</div>"
        f"<div style='color:{COLORS['white']};font-size:22px;font-weight:700;margin-bottom:6px;'>"
        f"Vue d'ensemble + plan d'actions</div>"
        f"<div style='color:{COLORS['muted']};font-size:12px;margin-bottom:18px;'>"
        f"Synthèse 1-vue de toute la période · {period.start:%d/%m} → {period.end:%d/%m} "
        f"· {len(selected_ids)}/{len(all_names)} restos</div>",
        unsafe_allow_html=True,
    )

    # === Score global ===
    statuses = [c.get("status") for c in (co_dash, co_prod, co_freq, co_src, co_cli, co_disc) if c]
    n_alerte = statuses.count("ALERTE")
    n_atten = statuses.count("ATTENTION")
    n_norm = statuses.count("NORMAL")
    if n_alerte > 0:
        score_label, score_color, score_msg = "🔴 Situation à traiter", COLORS["coral"], f"{n_alerte} alerte(s) critique(s)"
    elif n_atten >= 2:
        score_label, score_color, score_msg = "🟠 Plusieurs signaux faibles", COLORS["amber"], f"{n_atten} module(s) en zone d'attention"
    else:
        score_label, score_color, score_msg = "🟢 Réseau en bonne santé", "#34D399", f"{n_norm} module(s) au vert"

    st.markdown(
        f"<div style='background:{COLORS['surface']};border:1px solid {score_color}55;border-radius:12px;"
        f"padding:18px 20px;margin-bottom:18px;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
        f"<div><div style='color:{score_color};font-size:18px;font-weight:700;'>{score_label}</div>"
        f"<div style='color:{COLORS['muted']};font-size:13px;margin-top:4px;'>{score_msg}</div></div>"
        f"<div style='text-align:right;'>"
        f"<div style='color:{COLORS['white']};font-size:11px;letter-spacing:0.08em;'>"
        f"🔴 {n_alerte} · 🟠 {n_atten} · 🟢 {n_norm}</div></div></div></div>",
        unsafe_allow_html=True,
    )

    # === Synthèse par module (tous les copilotes empilés) ===
    st.markdown(
        f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.12em;"
        f"text-transform:uppercase;margin:24px 0 6px;'>Synthèse par module</div>",
        unsafe_allow_html=True,
    )
    for title, co in [
        ("Dashboard", co_dash), ("Produits", co_prod),
        ("Fréquentation", co_freq), ("Origines", co_src),
        ("Clients", co_cli), ("Remises", co_disc),
    ]:
        if co:
            copilots.render_copilot_card(title, co["status"], co["message"], co["recommendation"])

    # === Plan d'actions ===
    st.markdown(
        f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.12em;"
        f"text-transform:uppercase;margin:24px 0 6px;'>Plan d'actions priorisé</div>",
        unsafe_allow_html=True,
    )

    actions_ct = []  # court terme < 2 semaines
    actions_mt = []  # moyen terme 1-3 mois
    actions_lt = []  # long terme > 3 mois

    # Règles de priorisation basées sur les statuts copilotes
    if co_cli and co_cli["status"] in {"ALERTE", "ATTENTION"}:
        actions_ct.append("Activer la collecte d'opt-in client (email obligatoire sur ticket borne / web).")
        actions_mt.append("Lancer la première campagne CRM : email/SMS aux inactifs > 60j avec offre de retour.")
        actions_lt.append("Construire un programme de fidélité simple (X € = 1 point, 100 points = 1 plat offert).")
    if co_disc and co_disc["status"] == "ALERTE":
        actions_ct.append("Audit immédiat des remises du mois — identifier les abus / motifs flous.")
        actions_mt.append("Plafonner les remises par employé via le BO Zelty.")
    if co_prod and co_prod["status"] in {"ALERTE", "ATTENTION"}:
        actions_ct.append("Lister les 10 produits les plus faibles à retirer ou requalifier ce mois-ci.")
        actions_mt.append("Refonte progressive de la carte : viser < 80 références totales.")
    if co_freq and "weak_hours" in (co_freq.get("recommendation") or "").lower() or "happy" in (co_freq.get("recommendation") or "").lower():
        actions_ct.append("Tester un Happy Hour sur les créneaux faibles identifiés (14h-16h typiquement).")
    if co_src and "livraison" in (co_src.get("recommendation") or "").lower():
        actions_ct.append("Pousser le canal direct : 5% de remise première commande sur le site Zelty.")
        actions_lt.append("Évaluer si une app de commande directe (web/iOS) vaut l'investissement.")
    if co_dash and co_dash["status"] == "ALERTE":
        actions_ct.append("Réunion d'urgence directeurs restos en repli — identifier les causes (mauvaise météo? travaux? équipe?).")
    if co_dash and co_dash["status"] == "NORMAL" and not actions_ct:
        actions_ct.append("Pas d'urgence — capitaliser sur la dynamique en doublant les actions qui marchent.")

    # Si peu d'actions, ajouter des actions génériques de progression
    if len(actions_lt) < 2:
        actions_lt.append("Webhook Zelty `order.ended` → analytics temps réel (élimine le re-sync today).")
    if len(actions_mt) < 2:
        actions_mt.append("Tableau de bord par franchisé (envoi auto hebdomadaire d'un PDF synthèse).")

    plan_cols = st.columns(3)
    plan_data = [
        ("⚡ Court terme", "< 2 semaines", actions_ct, COLORS["coral"]),
        ("📅 Moyen terme", "1-3 mois", actions_mt, COLORS["amber"]),
        ("🎯 Long terme", "> 3 mois", actions_lt, "#34D399"),
    ]
    for col, (title, sub, items, color) in zip(plan_cols, plan_data):
        with col:
            st.markdown(
                f"<div style='background:{COLORS['surface']};border:1px solid {color}33;border-radius:10px;padding:14px 16px;height:100%;'>"
                f"<div style='color:{color};font-size:13px;font-weight:700;margin-bottom:2px;'>{title}</div>"
                f"<div style='color:{COLORS['muted']};font-size:10px;letter-spacing:0.08em;margin-bottom:12px;'>{sub.upper()}</div>",
                unsafe_allow_html=True,
            )
            if not items:
                st.markdown(
                    f"<div style='color:{COLORS['muted']};font-size:12px;font-style:italic;'>"
                    f"Aucune action urgente sur cet horizon.</div>",
                    unsafe_allow_html=True,
                )
            for it in items:
                st.markdown(
                    f"<div style='color:{COLORS['white']};font-size:12px;line-height:1.5;"
                    f"padding:8px 0;border-bottom:1px solid {COLORS['border']};'>"
                    f"<span style='color:{color};margin-right:6px;'>▸</span>{it}</div>",
                    unsafe_allow_html=True,
                )
            st.markdown("</div>", unsafe_allow_html=True)

    st.caption(
        "Plan généré dynamiquement depuis l'état actuel des 6 copilotes. "
        "Les actions disparaissent dès que la situation correspondante se normalise."
    )

    # === Analyse IA Claude ===
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    if api_key:
        st.markdown(
            f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.12em;"
            f"text-transform:uppercase;margin:32px 0 6px;'>"
            f"🤖 Analyse stratégique Claude</div>",
            unsafe_allow_html=True,
        )
        # Construire le payload de faits
        facts = {
            "période": f"{period.start:%d/%m/%Y} → {period.end:%d/%m/%Y} ({period.days} j)",
            "restos_sélectionnés": [id_to_name.get(rid, str(rid)) for rid in selected_ids],
            "ca_ttc_total": float(orders["ttc"].sum()) if not orders.empty else 0,
            "ca_ttc_période_précédente": float(orders_prev["ttc"].sum()) if not orders_prev.empty else 0,
            "n_commandes": len(orders),
            "n_commandes_précédent": len(orders_prev),
            "ticket_moyen": float(orders["ttc"].sum() / len(orders)) if not orders.empty else 0,
            "copilotes": {
                "dashboard": co_dash,
                "produits": co_prod,
                "fréquentation": co_freq,
                "origines": co_src,
                "clients": co_cli,
                "remises": co_disc,
            },
        }
        with st.spinner("Claude analyse votre réseau…"):
            try:
                analysis = copilots.board_ai_analysis(facts, _api_key=api_key)
            except Exception as e:  # noqa: BLE001
                analysis = f"⚠ Erreur API Claude : {e}"
        if analysis:
            st.markdown(
                f"<div style='background:{COLORS['surface']};border:1px solid {COLORS['coral']}44;"
                f"border-radius:12px;padding:18px 22px;'>{analysis}</div>",
                unsafe_allow_html=True,
            )
    else:
        st.info(
            "💡 Ajoute `ANTHROPIC_API_KEY` dans `.streamlit/secrets.toml` "
            "pour activer l'analyse stratégique générée par Claude."
        )


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
    if st.button("🔄 Sync today depuis Zelty"):
        with st.status("Synchronisation today…", expanded=True) as s:
            stats = zelty_client.sync_today(
                tuple(restos_df["id"].astype(int).tolist()),
                on_progress=s.write,
            )
            s.update(label=f"Today sync ✓ ({stats.get('orders', 0)} orders en DB)",
                     state="complete", expanded=False)
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
