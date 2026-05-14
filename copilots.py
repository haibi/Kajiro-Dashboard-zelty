"""Copilotes : analyses rule-based des modules + analyse IA Claude sur le Board.

Chaque copilote (rule-based) prend les dataframes pertinents + meta et retourne
un dict {status, message, recommendation}.

board_ai_analysis() appelle Claude API pour une analyse stratégique riche.
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from theme import COLORS

STATUS_COLORS = {
    "NORMAL": ("#34D399", "🟢"),
    "ATTENTION": (COLORS["amber"], "🟠"),
    "ALERTE": (COLORS["coral"], "🔴"),
    "INFO": (COLORS["muted"], "ℹ️"),
}

CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_MAX_TOKENS = 1500


@st.cache_data(ttl=900, show_spinner=False)
def board_ai_analysis(facts: dict, _api_key: str | None = None) -> str:
    """Demande à Claude une analyse stratégique structurée du board.

    `facts` : dict avec les KPIs et statuts de tous les modules.
    Le résultat est mis en cache 15 min (mêmes facts → même analyse).
    """
    if not _api_key:
        return ""
    try:
        from anthropic import Anthropic
    except ImportError:
        return "⚠ Module `anthropic` non installé. Lance `pip install anthropic`."

    client = Anthropic(api_key=_api_key)
    system = (
        "Tu es un analyste business pour un groupe de restaurants de sushis (Kajirō Sushi, "
        "7 établissements en France). Ton rôle est de produire des analyses concises, "
        "actionables et basées sur les chiffres fournis. Tu écris en français. "
        "Tu vouvoies. Tu ne diluis pas — chaque phrase doit apporter de l'info. "
        "Tu identifies les leviers concrets et les pièges. Pas de baratin."
    )
    user_msg = (
        "Voici l'état actuel du réseau Kajirō sur la période sélectionnée. "
        "Donne une **analyse stratégique en 3 sections** :\n\n"
        "## 🔎 Diagnostic\n(3-5 phrases. Signaux forts, positifs ou négatifs. "
        "Cite les chiffres. Lis l'évolution vs période précédente.)\n\n"
        "## ⚠ Risques\n(2-3 risques concrets à surveiller, en bullets.)\n\n"
        "## ✅ Leviers prioritaires\n(3-5 actions priorisées par ROI, en bullets. "
        "Mentionne l'horizon court/moyen/long terme pour chacune.)\n\n"
        f"État du réseau :\n```json\n{json.dumps(facts, ensure_ascii=False, indent=2)}\n```"
    )

    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=CLAUDE_MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    return resp.content[0].text if resp.content else ""


def render_copilot_card(
    title: str,
    status: str,
    message: str,
    recommendation: str | None = None,
) -> None:
    """Rend une carte CO-PILOTE style Bron : badge + analyse + reco."""
    color, _ = STATUS_COLORS.get(status, STATUS_COLORS["INFO"])
    reco_html = ""
    if recommendation:
        reco_html = (
            f"<div style='color:{COLORS['muted']};font-size:12px;font-style:italic;"
            f"line-height:1.5;margin-top:8px;border-top:1px solid {COLORS['border']};"
            f"padding-top:8px;'>"
            f"💡 {recommendation}</div>"
        )
    st.markdown(
        f"<div style='background:{COLORS['surface']};border:1px solid {COLORS['border']};"
        f"border-radius:10px;padding:14px 16px;margin:14px 0;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;'>"
        f"<div style='display:flex;align-items:center;gap:8px;'>"
        f"<span style='width:8px;height:8px;border-radius:50%;background:{color};'></span>"
        f"<span style='color:{COLORS['muted']};font-size:10px;letter-spacing:0.14em;"
        f"text-transform:uppercase;font-weight:700;'>CO-PILOTE</span>"
        f"<span style='color:{COLORS['white']};font-size:12px;font-weight:600;'>{title}</span>"
        f"</div>"
        f"<span style='background:{color}22;color:{color};border:1px solid {color}44;"
        f"padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;letter-spacing:0.06em;'>"
        f"{status}</span></div>"
        f"<div style='color:{COLORS['white']};font-size:13px;line-height:1.6;'>{message}</div>"
        f"{reco_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


# ===========================================================================
# Copilotes par module
# ===========================================================================
def dashboard_copilot(orders: pd.DataFrame, orders_prev: pd.DataFrame, period_days: int) -> dict:
    """Analyse globale du CA réseau + comparaison vs N-1."""
    if orders.empty:
        return {"status": "INFO", "message": "Pas de données pour analyser.", "recommendation": None}

    ttc = orders["ttc"].sum()
    n = len(orders)
    tm = ttc / n if n else 0
    p_ttc = orders_prev["ttc"].sum() if not orders_prev.empty else 0
    p_n = len(orders_prev)
    p_tm = p_ttc / p_n if p_n else 0
    delta_ca = (ttc - p_ttc) / p_ttc * 100 if p_ttc else 0
    delta_n = (n - p_n) / p_n * 100 if p_n else 0
    delta_tm = (tm - p_tm) / p_tm * 100 if p_tm else 0

    if delta_ca > 5:
        status, opener = "NORMAL", "Période en croissance"
    elif delta_ca < -10:
        status, opener = "ALERTE", "Période en repli marqué"
    elif delta_ca < 0:
        status, opener = "ATTENTION", "Légère baisse"
    else:
        status, opener = "NORMAL", "Période stable"

    # Identifier le driver
    if abs(delta_n) > abs(delta_tm) and abs(delta_n) > 3:
        driver = f"le volume ({delta_n:+.1f}% de commandes)"
    elif abs(delta_tm) > 3:
        driver = f"le panier moyen ({delta_tm:+.1f}%)"
    else:
        driver = "volume et panier stables"

    msg = (
        f"<b>{opener}</b> : {ttc/1000:,.1f} K€ TTC sur {n:,} commandes "
        f"({delta_ca:+.1f}% vs période précédente). Le delta est porté par {driver}."
    ).replace(",", " ")

    reco = None
    if status == "ALERTE":
        reco = (
            f"Identifier le ou les restaurants qui plongent. "
            f"Vérifier qu'aucune fermeture exceptionnelle ne fausse la comparaison. "
            f"Côté trafic : ouvrir une promo flash sur le canal le plus performant."
        )
    elif status == "ATTENTION":
        reco = (
            "Activer un levier court terme : push UberEats / promo borne / animation week-end."
        )
    elif delta_ca > 15:
        reco = "Capitaliser sur la dynamique : doubler les actions qui fonctionnent (promo, plat phare, canal en croissance)."

    return {"status": status, "message": msg, "recommendation": reco}


def products_copilot(
    products: pd.DataFrame, period_days: int, n_restos: int
) -> dict:
    """Synthèse complexité carte + sous-performants."""
    if products.empty:
        return {"status": "INFO", "message": "Pas de produits sur cette période.", "recommendation": None}

    n_total = len(products)
    threshold_ht = 300 * (period_days / 30.4) * n_restos
    losers = products[products["ht"] < threshold_ht]
    n_losers = len(losers)
    pct_losers = (n_losers / n_total * 100) if n_total else 0
    top20 = products.sort_values("ht", ascending=False).head(20)
    pct_top20 = (top20["ht"].sum() / (products["ht"].sum() or 1)) * 100

    if n_total > 100 and pct_top20 > 75:
        status = "ALERTE"
        msg = (
            f"Carte trop dense : <b>{n_total} produits actifs</b> mais le top 20 capte "
            f"<b>{pct_top20:.0f}% du CA</b>. {n_losers} produits sous-performent (< 300€/mois/resto, "
            f"soit {pct_losers:.0f}% de la carte)."
        )
        reco = (
            f"Retirer une dizaine de sous-performants dans le mois. "
            f"Cuisine plus rapide, stock plus simple, panier moyen souvent en hausse."
        )
    elif n_total > 60 and pct_losers > 30:
        status = "ATTENTION"
        msg = (
            f"<b>{n_losers} produits sur {n_total}</b> ({pct_losers:.0f}%) sous le seuil de 300€/mois/resto. "
            f"Le top 20 fait {pct_top20:.0f}% du CA."
        )
        reco = "Tester un retrait progressif des 5 plus faibles produits ce mois-ci et mesurer l'impact."
    else:
        status = "NORMAL"
        msg = (
            f"Carte saine : <b>{n_total} produits</b>, top 20 = {pct_top20:.0f}% du CA, "
            f"{n_losers} sous-performants."
        )
        reco = None

    return {"status": status, "message": msg, "recommendation": reco}


def frequentation_copilot(orders: pd.DataFrame) -> dict:
    """Analyse pics horaires, créneaux faibles, week-end."""
    if orders.empty or "closed_at" not in orders.columns:
        return {"status": "INFO", "message": "Données insuffisantes.", "recommendation": None}

    df = orders.copy()
    df["dt"] = pd.to_datetime(df["closed_at"], errors="coerce")
    df = df.dropna(subset=["dt"])
    if df.empty:
        return {"status": "INFO", "message": "Pas de timestamps valides.", "recommendation": None}

    df["hour"] = df["dt"].dt.hour
    by_hour = df.groupby("hour").size()
    peak_hour = by_hour.idxmax()
    peak_val = by_hour.max()
    second = by_hour.nlargest(2).iloc[1] if len(by_hour) > 1 else 0
    concentration = peak_val / by_hour.sum() * 100

    # Gap-creneau : heures avec moins de 30% du pic dans la plage 11-21
    weak_hours = [int(h) for h, v in by_hour.items() if 11 <= h <= 21 and v < peak_val * 0.3]

    # Week-end vs semaine
    df["day_en"] = df["dt"].dt.day_name()
    weekend = df[df["day_en"].isin(["Saturday", "Sunday"])]
    weekday = df[~df["day_en"].isin(["Saturday", "Sunday"])]
    weekend_share = len(weekend) / len(df) * 100
    we_days = weekend["dt"].dt.date.nunique() or 1
    wd_days = weekday["dt"].dt.date.nunique() or 1
    we_per_day = len(weekend) / we_days
    wd_per_day = len(weekday) / wd_days
    we_premium = (we_per_day - wd_per_day) / wd_per_day * 100 if wd_per_day else 0

    msg = (
        f"<b>Pic à {peak_hour}h</b> ({peak_val} cmds, {concentration:.0f}% de la journée). "
    )
    if we_premium > 20:
        msg += f"Week-end : <b>+{we_premium:.0f}% de fréquentation</b> vs semaine."
        status = "NORMAL"
    elif we_premium < -10:
        msg += f"Week-end <b>en sous-régime</b> ({we_premium:+.0f}% vs semaine)."
        status = "ATTENTION"
    else:
        msg += f"Week-end équivalent à la semaine ({we_premium:+.0f}%)."
        status = "NORMAL"

    reco = None
    if weak_hours:
        wh_str = ", ".join(f"{h}h" for h in weak_hours[:3])
        reco = (
            f"Créneaux faibles : {wh_str}. "
            f"Tester un happy hour / menu déjeuner / push notification borne sur ces heures."
        )
    if we_premium < -10:
        reco = (
            "Le week-end est sous-exploité. Vérifier les horaires d'ouverture, "
            "la dispo livraison, ou lancer une offre famille week-end."
        )

    return {"status": status, "message": msg, "recommendation": reco}


def sources_copilot(orders: pd.DataFrame) -> dict:
    """Analyse mix canaux + ticket moyen par canal."""
    if orders.empty:
        return {"status": "INFO", "message": "Pas de données.", "recommendation": None}

    by_src = orders.groupby("source").agg(ca=("ttc", "sum"), n=("order_id", "count"))
    by_src["pct"] = by_src["ca"] / by_src["ca"].sum() * 100
    by_src["tm"] = by_src["ca"] / by_src["n"]

    if by_src.empty:
        return {"status": "INFO", "message": "Pas de canal identifié.", "recommendation": None}

    by_src_sorted = by_src.sort_values("ca", ascending=False)
    dom_src = by_src_sorted.index[0]
    dom = by_src_sorted.iloc[0]
    SOURCE_LABELS = {
        "pos": "POS", "kiosk": "Borne", "web": "Site web Zelty",
        "ubereats": "UberEats", "deliveroo": "Deliveroo", "phone": "Téléphone",
    }
    dom_label = SOURCE_LABELS.get(dom_src, dom_src or "Inconnu")
    # Best ticket avg
    best_tm_src = by_src["tm"].idxmax()
    best_tm_label = SOURCE_LABELS.get(best_tm_src, best_tm_src or "Inconnu")
    best_tm = by_src.loc[best_tm_src, "tm"]

    delivery_share = 0
    for k in ("ubereats", "deliveroo"):
        if k in by_src.index:
            delivery_share += by_src.loc[k, "pct"]

    msg = (
        f"Canal dominant : <b>{dom_label}</b> ({dom['pct']:.0f}% du CA, "
        f"{int(dom['n'])} tickets · ticket moy. {dom['tm']:.2f}€). "
        f"Ticket moyen le plus élevé : <b>{best_tm_label}</b> ({best_tm:.2f}€)."
    )

    status = "NORMAL"
    reco = None
    if delivery_share > 30:
        status = "ATTENTION"
        reco = (
            f"Livraison externe ({delivery_share:.0f}% du CA) = ~25-30% de commission. "
            f"Pousser le canal direct (site web Zelty, app maison) pour reprendre la marge."
        )
    elif "kiosk" in by_src.index and by_src.loc["kiosk", "pct"] > 50:
        reco = (
            "Les bornes captent la majorité du CA — c'est sain. "
            "Vérifier que le site web et l'app suivent en up-sell digital."
        )

    return {"status": status, "message": msg, "recommendation": reco}


def clients_copilot(orders: pd.DataFrame) -> dict:
    """Analyse base clients, anonymat, fidélité."""
    if orders.empty or "customer_id" not in orders.columns:
        return {"status": "INFO", "message": "Données clients pas encore disponibles.", "recommendation": None}

    df = orders.copy()
    n_total = len(df)
    n_anon = df["customer_id"].isna().sum()
    pct_anon = n_anon / n_total * 100 if n_total else 0
    df_id = df[df["customer_id"].notna()]
    n_id_unique = df_id["customer_id"].nunique()
    if n_id_unique == 0:
        return {
            "status": "ALERTE",
            "message": "Aucun client identifié — toute la base est anonyme.",
            "recommendation": "Activer la collecte d'opt-in (email/téléphone) à la borne et sur la fiche commande."
        }
    cmd_per_id = df_id.groupby("customer_id").size()
    recurrent = (cmd_per_id >= 2).sum()
    recurrent_pct = recurrent / n_id_unique * 100

    tm_id = df_id["ttc"].sum() / len(df_id)
    tm_an = df.loc[df["customer_id"].isna(), "ttc"].sum() / n_anon if n_anon else 0
    delta_tm = (tm_id - tm_an) / tm_an * 100 if tm_an else 0

    if pct_anon > 60:
        status = "ALERTE"
        msg = (
            f"<b>{pct_anon:.0f}% de commandes anonymes</b> sur {n_total:,} tickets. "
            f"Tu n'as aucun levier CRM pour les réactiver. Panier identifié = "
            f"{tm_id:.2f}€ vs anonyme {tm_an:.2f}€ ({delta_tm:+.0f}%)."
        ).replace(",", " ")
        reco = (
            "Priorité 1 : collecter l'opt-in sur borne/web (champ email obligatoire pour la facture). "
            "Priorité 2 : SMS/email de relance sur les inactifs > 60j."
        )
    elif pct_anon > 40:
        status = "ATTENTION"
        msg = (
            f"{pct_anon:.0f}% d'anonymes — moitié de la base est invisible côté CRM. "
            f"{recurrent_pct:.0f}% des identifiés sont récurrents."
        )
        reco = "Améliorer la collecte d'opt-in : récompense (5% de remise) contre inscription."
    else:
        status = "NORMAL"
        msg = (
            f"Base CRM saine : {pct_anon:.0f}% d'anonymes, {n_id_unique:,} clients identifiés, "
            f"<b>{recurrent_pct:.0f}% de récurrents</b>."
        ).replace(",", " ")
        reco = None

    return {"status": status, "message": msg, "recommendation": reco}


def discounts_copilot(orders: pd.DataFrame) -> dict:
    """Analyse remises : taux global, employés top, anomalies."""
    if orders.empty or "discount_ttc" not in orders.columns:
        return {"status": "INFO", "message": "Pas de données remises.", "recommendation": None}

    df = orders[orders["discount_count"] > 0].copy()
    if df.empty:
        return {
            "status": "NORMAL",
            "message": "Aucune remise appliquée sur la période.",
            "recommendation": None,
        }

    total_disc = df["discount_ttc"].sum()
    total_ca = orders["ttc"].sum()
    rate = total_disc / total_ca * 100 if total_ca else 0
    n_disc = len(df)
    by_server = (
        df.assign(s=df["server_name"].fillna("(non identifié)"))
        .groupby("s")["discount_ttc"].sum().sort_values(ascending=False)
    )
    if by_server.empty:
        return {"status": "INFO", "message": "Pas d'employé identifié sur les remises.", "recommendation": None}

    top_emp = by_server.index[0]
    top_emp_amount = by_server.iloc[0]
    top_emp_pct = top_emp_amount / total_disc * 100

    if rate > 5:
        status = "ALERTE"
        msg = (
            f"<b>{rate:.1f}% de taux de remise</b> ({total_disc:,.0f}€ sur {total_ca:,.0f}€). "
            f"Élevé — vérifier qu'aucune remise abusive ne plombe la marge. "
            f"Top contributeur : <b>{top_emp}</b> ({top_emp_pct:.0f}%)."
        ).replace(",", " ")
        reco = (
            "Auditer les remises de ce mois : motif (geste co / employé / promo) "
            "et croiser avec le profil client. Mettre une limite par employé."
        )
    elif rate > 2:
        status = "ATTENTION"
        msg = (
            f"Taux de remise à {rate:.1f}% — dans la zone haute. "
            f"{n_disc} commandes avec remise sur la période. Top : {top_emp} ({top_emp_pct:.0f}% du total)."
        )
        reco = "Confirmer que les remises ont du sens (geste client, promo planifiée, formation employé)."
    else:
        status = "NORMAL"
        msg = (
            f"Taux de remise à {rate:.1f}% — sain. "
            f"{n_disc} actions sur la période, {total_disc:,.0f}€ total."
        ).replace(",", " ")
        reco = None

    return {"status": status, "message": msg, "recommendation": reco}
