"""Kajirō Dashboard — analytics réseau multi-restaurants depuis l'API Zelty (v2.10)."""
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
        per_resto.insert(0, "#", range(1, len(per_resto) + 1))

        display_cols = ["#", "nom", "ca_ttc", "ca_ht", "cmds", "ticket_moyen", "pct", "jours"]
        existing_cols = [c for c in display_cols if c in per_resto.columns]
        display = per_resto[existing_cols].rename(columns={
            "nom": "Restaurant",
            "ca_ttc": "CA TTC (€)",
            "ca_ht": "CA HT (€)",
            "cmds": "Cmds",
            "ticket_moyen": "Ticket moy. (€)",
            "pct": "% CA",
            "jours": "Jours",
        })
        st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
            column_config={
                "CA TTC (€)": st.column_config.ProgressColumn(
                    format="%.0f €", min_value=0, max_value=float(display["CA TTC (€)"].max() or 1),
                ),
                "CA HT (€)": st.column_config.NumberColumn(format="%.0f €"),
                "Cmds": st.column_config.NumberColumn(format="%d"),
                "Ticket moy. (€)": st.column_config.NumberColumn(format="%.2f €"),
                "% CA": st.column_config.NumberColumn(format="%.2f %%"),
                "Jours": st.column_config.NumberColumn(format="%d j"),
            },
        )

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

    # KPIs produits
    pk1, pk2, pk3, pk4 = st.columns(4)
    pk1.metric("CA HT total", f"{total_ht/1000:,.1f} K€".replace(",", " "))
    pk2.metric("Unités", f"{int(data['qte'].sum()):,}".replace(",", " "))
    pk3.metric("Références", f"{len(data)}")
    pk4.metric(f"Top {len(filtered)} couvre", f"{(filtered['ht'].sum()/total_ht*100):.1f}%")

    # Table
    display = filtered.copy()
    display.insert(0, "#", range(1, len(display) + 1))
    display = display.rename(columns={
        "nom": "Produit", "qte": "Unités", "ht": "CA HT (€)",
        "prix_moy": "Prix moy. (€)", "pct_ca": "% CA",
    })[["#", "Produit", "CA HT (€)", "Unités", "Prix moy. (€)", "% CA"]]

    st.dataframe(
        display, hide_index=True, use_container_width=True,
        height=min(600, 60 + len(display) * 36),
        column_config={
            "CA HT (€)": st.column_config.ProgressColumn(
                format="%.0f €", min_value=0,
                max_value=float(display["CA HT (€)"].max() or 1),
            ),
            "Unités": st.column_config.NumberColumn(format="%d"),
            "Prix moy. (€)": st.column_config.NumberColumn(format="%.2f €"),
            "% CA": st.column_config.NumberColumn(format="%.2f %%"),
        },
    )

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
    st.markdown(
        f"<div style='color:{COLORS['muted']};font-size:11px;'>"
        f"{len(restos_df)} restaurants connectés via Zelty (v{zelty_client.API_VERSION})"
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
