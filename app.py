"""Kajirō Dashboard — analytics réseau multi-restaurants depuis l'API Zelty."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

import periods
import zelty_client
from auth import check_password, logout
from theme import COLORS, header, inject_css

FAVICON = Path(__file__).parent / "assets" / "favicon.svg"

# Liste de référence pour mappage nom → ID si Zelty ne retourne pas les noms attendus
KAJIRO_SITES = ["Tain", "Roussillon", "Davézieux", "Vienne", "Condrieu", "Veauche", "Bron"]

TOP_PRESETS = [15, 30, 50, 100]

st.set_page_config(
    page_title="Kajirō Sushi · Analytics",
    page_icon=str(FAVICON) if FAVICON.exists() else None,
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_css()

if not check_password():
    st.stop()

header()

# ------------------------------------------------------------------
# 1. Charger les restaurants (cache 1h)
# ------------------------------------------------------------------
with st.spinner("Connexion à Zelty…"):
    try:
        restos_df = zelty_client.list_restaurants()
    except zelty_client.ZeltyError as e:
        st.error(f"Impossible de joindre Zelty: {e}")
        st.info(
            "Vérifie `.streamlit/secrets.toml` — `ZELTY_API_KEY`, `ZELTY_AUTH_SCHEME` "
            "(`Basic` ou `Bearer`), `ZELTY_BASE_URL`."
        )
        st.stop()

if restos_df.empty:
    st.warning("Aucun restaurant retourné par l'API. Vérifie le périmètre de la clé.")
    st.stop()

# ------------------------------------------------------------------
# 2. Onglets
# ------------------------------------------------------------------
tab_produits, = st.tabs(["PRODUITS"])

with tab_produits:
    st.markdown(
        f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.1em;margin-bottom:6px;'>"
        f"BEST SELLERS · {len(restos_df)} ÉTABLISSEMENTS</div>",
        unsafe_allow_html=True,
    )

    # ----- Filtres -----
    fc1, fc2, fc3 = st.columns([1.2, 2, 1.4])

    with fc1:
        preset = st.selectbox(
            "Période",
            periods.PRESETS,
            index=0,
            key="period_preset",
        )
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

    with fc3:
        top_n = st.selectbox(
            "Top N",
            TOP_PRESETS + [9999],
            index=2,
            format_func=lambda n: "TOUT" if n == 9999 else f"TOP {n}",
            key="topn",
        )

    fc4, fc5, fc6 = st.columns([2, 1, 1])
    with fc4:
        search = st.text_input("Rechercher", "", placeholder="Filtrer par nom…", label_visibility="collapsed")
    with fc5:
        sort_by = st.selectbox(
            "Trier par",
            ["ht", "qte", "prix_moy", "pct_ca"],
            format_func={"ht": "CA HT", "qte": "Unités", "prix_moy": "Prix moy.", "pct_ca": "% CA"}.get,
            key="sort_by",
        )
    with fc6:
        sort_dir = st.selectbox(
            "Sens",
            ["desc", "asc"],
            format_func={"desc": "↓ Décroissant", "asc": "↑ Croissant"}.get,
            key="sort_dir",
        )

    st.caption(
        f"Période : {period.start:%d/%m/%Y} → {period.end:%d/%m/%Y} "
        f"({period.days} j) · {len(selected_names)}/{len(all_names)} restaurants"
    )

    if not selected_names:
        st.warning("Sélectionne au moins un restaurant.")
        st.stop()

    selected_ids = tuple(
        restos_df.loc[restos_df["name"].isin(selected_names), "id"].astype(int).tolist()
    )

    # ----- Fetch -----
    with st.spinner(f"Récupération Zelty · {len(selected_ids)} restaurants · {period.days} j…"):
        try:
            data = zelty_client.fetch_sales_by_product(
                restaurant_ids=selected_ids,
                date_from=period.start,
                date_to=period.end,
            )
        except zelty_client.ZeltyError as e:
            st.error(f"Erreur Zelty: {e}")
            st.stop()

    if data.empty:
        st.info("Aucune vente sur cette période pour les restaurants sélectionnés.")
        st.stop()

    # ----- Search + sort + top N -----
    filtered = data.copy()
    if search:
        filtered = filtered[filtered["nom"].str.contains(search, case=False, na=False)]
    filtered = filtered.sort_values(sort_by, ascending=(sort_dir == "asc")).reset_index(drop=True)
    if top_n != 9999:
        filtered = filtered.head(top_n)

    # ----- KPIs -----
    total_ht = data["ht"].sum()
    total_qte = int(data["qte"].sum())
    n_refs = len(data)
    shown_ht = filtered["ht"].sum()
    pct_shown = (shown_ht / total_ht * 100) if total_ht > 0 else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("CA HT (sélection)", f"{total_ht/1000:,.0f} K€".replace(",", " "))
    k2.metric("Unités vendues", f"{total_qte:,}".replace(",", " "))
    k3.metric("Références actives", f"{n_refs}")
    k4.metric(f"Couvert. top {len(filtered)}", f"{pct_shown:.1f}%")

    # ----- Table -----
    display = filtered.copy()
    display.insert(0, "#", range(1, len(display) + 1))
    display = display.rename(columns={
        "nom": "Produit",
        "qte": "Unités",
        "ht": "CA HT (€)",
        "prix_moy": "Prix moy. (€)",
        "pct_ca": "% CA",
    })[["#", "Produit", "CA HT (€)", "Unités", "Prix moy. (€)", "% CA"]]

    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        height=min(600, 60 + len(display) * 36),
        column_config={
            "#": st.column_config.NumberColumn(width="small"),
            "Produit": st.column_config.TextColumn(width="large"),
            "CA HT (€)": st.column_config.ProgressColumn(
                format="%.0f €",
                min_value=0,
                max_value=float(display["CA HT (€)"].max() or 1),
            ),
            "Unités": st.column_config.NumberColumn(format="%d"),
            "Prix moy. (€)": st.column_config.NumberColumn(format="%.2f €"),
            "% CA": st.column_config.NumberColumn(format="%.2f %%"),
        },
    )

    # ----- Footer totals -----
    f1, f2, f3, f4 = st.columns(4)
    f1.markdown(
        f"<div style='color:{COLORS['muted']};font-size:11px;'>TOTAL AFFICHÉ — {len(filtered)} refs</div>",
        unsafe_allow_html=True,
    )
    f2.markdown(
        f"<div style='color:{COLORS['coral']};font-size:14px;font-weight:700;'>"
        f"{shown_ht:,.0f} €</div>".replace(",", " "),
        unsafe_allow_html=True,
    )
    f3.markdown(
        f"<div style='color:{COLORS['white']};font-size:14px;font-weight:700;'>"
        f"{int(filtered['qte'].sum()):,} u.</div>".replace(",", " "),
        unsafe_allow_html=True,
    )
    f4.markdown(
        f"<div style='color:{COLORS['coral']};font-size:13px;font-weight:700;'>"
        f"{pct_shown:.1f}% du CA</div>",
        unsafe_allow_html=True,
    )

    # ----- Graphique : top par CA -----
    st.markdown("---")
    chart_n = min(20, len(filtered))
    if chart_n > 0:
        st.markdown(
            f"<div style='color:{COLORS['muted']};font-size:11px;letter-spacing:0.1em;margin-bottom:6px;'>"
            f"TOP {chart_n} · {('UNITÉS' if sort_by == 'qte' else 'CA HT')}</div>",
            unsafe_allow_html=True,
        )
        col_value = "qte" if sort_by == "qte" else "ht"
        chart_data = filtered.head(chart_n).iloc[::-1]
        fig = px.bar(
            chart_data,
            x=col_value,
            y="nom",
            orientation="h",
            color_discrete_sequence=[COLORS["coral"]],
            hover_data={"qte": True, "ht": ":.0f", "prix_moy": ":.2f", "pct_ca": ":.2f"},
        )
        fig.update_layout(
            paper_bgcolor=COLORS["bg"],
            plot_bgcolor=COLORS["surface"],
            font=dict(family="DM Mono, monospace", color=COLORS["white"]),
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(gridcolor=COLORS["border"], title=None),
            yaxis=dict(gridcolor=COLORS["border"], title=None, tickfont=dict(size=11)),
            height=max(280, chart_n * 22),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "Source : API Zelty · agrégation lignes de commande sur statuts fermés · "
        "% CA = part dans la sélection (restaurants × période)"
    )

# ------------------------------------------------------------------
# Footer
# ------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"### Kajirō Analytics")
    st.markdown(
        f"<div style='color:{COLORS['muted']};font-size:11px;'>"
        f"{len(restos_df)} restaurants connectés via Zelty"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    if st.button("🔄 Rafraîchir les données"):
        st.cache_data.clear()
        st.rerun()
    if st.button("Déconnexion"):
        logout()
        st.rerun()
    st.markdown("---")
    ok, msg = zelty_client.health_check()
    icon = "🟢" if ok else "🔴"
    st.markdown(
        f"<div style='font-size:11px;color:{COLORS['muted']};'>{icon} {msg}</div>",
        unsafe_allow_html=True,
    )
