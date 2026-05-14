"""Composants UI custom — tables stylées style kajiro-bron-dashboard."""
from __future__ import annotations

from typing import Any

import streamlit as st

from theme import COLORS

RANK_COLORS = {1: COLORS["gold"], 2: COLORS["silver"], 3: COLORS["bronze"]}


def _fmt_eur(v: float, k: bool = False) -> str:
    if k:
        return f"{v/1000:,.1f} K€".replace(",", " ")
    return f"{int(round(v)):,} €".replace(",", " ")


def _fmt_int(v: int | float) -> str:
    return f"{int(round(v)):,}".replace(",", " ")


def render_product_table(
    rows: list[dict[str, Any]],
    sort_key: str = "ht",
    show_photos: bool = True,
) -> None:
    """Table produits façon Bron : miniature, rang coloré, sparkbar, CA / unités / prix moy / %CA."""
    if not rows:
        return

    max_val = max((r.get(sort_key, 0) or 0) for r in rows) or 1
    photo_w = "44px" if show_photos else "0"
    grid = f"40px {photo_w} 1fr 120px 100px 90px 80px"

    parts: list[str] = [f'<div class="kj-table" style="--cols: {grid};">']
    parts.append('<div class="kj-tr kj-thead">')
    parts.append('<div>#</div>')
    if show_photos:
        parts.append('<div></div>')
    parts.append('<div>PRODUIT</div>')
    parts.append('<div class="kj-h-hi">CA HT</div>')
    parts.append('<div>UNITÉS</div>')
    parts.append('<div>PRIX MOY.</div>')
    parts.append('<div>% CA</div>')
    parts.append('</div>')

    for i, r in enumerate(rows, start=1):
        rank_color = RANK_COLORS.get(i, COLORS["muted"])
        is_top3 = i <= 3
        weight = "700" if is_top3 else "400"
        spark_pct = ((r.get(sort_key, 0) or 0) / max_val) * 100
        parts.append('<div class="kj-tr">')
        parts.append(
            f'<div class="kj-rank" style="color:{rank_color};font-weight:{("800" if is_top3 else "500")};">'
            f"{i}</div>"
        )
        if show_photos:
            img = r.get("img") or ""
            if img:
                parts.append(
                    f'<div><img src="{img}" style="width:40px;height:40px;'
                    f'object-fit:cover;border-radius:6px;border:1px solid {COLORS["border"]};"></div>'
                )
            else:
                parts.append(
                    f'<div style="width:40px;height:40px;border-radius:6px;'
                    f'background:{COLORS["surface_alt"]};border:1px solid {COLORS["border"]};"></div>'
                )
        parts.append(
            f'<div class="kj-name-cell">'
            f'<div style="font-weight:{weight};">{r.get("nom", "")}</div>'
            f'<div class="kj-spark"><div class="kj-spark-fill" style="width:{spark_pct:.0f}%;"></div></div>'
            f'</div>'
        )
        # CA HT
        ca = r.get("ht", 0)
        parts.append(
            f'<div style="color:{COLORS["coral"]};font-weight:700;">'
            f"{_fmt_eur(ca)}</div>"
        )
        # Unités
        parts.append(f'<div style="color:{COLORS["white"]};font-weight:500;">{_fmt_int(r.get("qte", 0))} u.</div>')
        # Prix moyen
        parts.append(f'<div style="color:{COLORS["muted"]};">{r.get("prix_moy", 0):.2f} €</div>')
        # % CA
        pct = r.get("pct_ca", 0)
        if pct > 5:
            tag_color = COLORS["coral"]
        elif pct > 2:
            tag_color = COLORS["amber"]
        else:
            tag_color = COLORS["muted"]
        parts.append(
            f'<div><span style="background:{tag_color}22;color:{tag_color};'
            f'border:1px solid {tag_color}44;padding:2px 8px;border-radius:4px;'
            f'font-size:11px;font-weight:700;letter-spacing:0.04em;">'
            f"{pct:.2f}%</span></div>"
        )
        parts.append('</div>')

    parts.append('</div>')
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_ranking_table(
    rows: list[dict[str, Any]],
    columns: list[dict[str, Any]],
    spark_field: str = "ca_ttc",
    footer: dict[str, Any] | None = None,
) -> None:
    """Rend une table HTML stylée (rangs colorés top 3, sparkbars, hover coral).

    `rows` : liste de dicts {nom, ...valeurs colonnes}
    `columns` : [{key, label, fmt: "eur" | "eur_k" | "int" | "pct" | "days", highlight?: bool}]
    `spark_field` : champ utilisé pour la sparkbar sous le nom
    `footer` : ligne de totaux optionnelle, mêmes clés que les colonnes
    """
    if not rows:
        return

    grid = "40px 1fr " + " ".join("130px" if c.get("fmt") in ("eur", "eur_k") else "100px" for c in columns)
    max_spark = max((r.get(spark_field, 0) for r in rows), default=1) or 1

    parts: list[str] = [f'<div class="kj-table" style="--cols: {grid};">']
    # Header
    parts.append('<div class="kj-tr kj-thead">')
    parts.append('<div>#</div><div>RESTAURANT</div>')
    for c in columns:
        cls = "kj-h-hi" if c.get("highlight") else ""
        parts.append(f'<div class="{cls}">{c["label"]}</div>')
    parts.append('</div>')

    # Rows
    for i, r in enumerate(rows, start=1):
        rank_color = RANK_COLORS.get(i, COLORS["muted"])
        is_top3 = i <= 3
        weight = "700" if is_top3 else "400"
        spark_pct = (r.get(spark_field, 0) / max_spark) * 100 if max_spark else 0
        parts.append('<div class="kj-tr">')
        parts.append(
            f'<div class="kj-rank" style="color:{rank_color};font-weight:{("800" if is_top3 else "500")};">'
            f"{i}</div>"
        )
        parts.append(
            f'<div class="kj-name-cell">'
            f'<div style="font-weight:{weight};">{r.get("nom", "")}</div>'
            f'<div class="kj-spark"><div class="kj-spark-fill" style="width:{spark_pct:.0f}%;"></div></div>'
            f'</div>'
        )
        for c in columns:
            val = r.get(c["key"], 0)
            fmt = c.get("fmt", "int")
            highlight = c.get("highlight")
            color = COLORS["coral"] if highlight else COLORS["white"]
            wgt = "700" if highlight else "500"
            if fmt == "eur":
                txt = _fmt_eur(val)
            elif fmt == "eur_k":
                txt = _fmt_eur(val, k=True)
            elif fmt == "pct":
                txt = f"{val:.1f}%"
            elif fmt == "days":
                txt = f"{int(val)} j"
            elif fmt == "money2":
                txt = f"{val:.2f} €"
            else:
                txt = _fmt_int(val)
            parts.append(f'<div style="color:{color};font-weight:{wgt};">{txt}</div>')
        parts.append('</div>')

    # Footer
    if footer:
        parts.append('<div class="kj-tr kj-tfoot">')
        parts.append(f'<div></div><div style="color:{COLORS["muted"]};font-weight:700;">TOTAL — {len(rows)}</div>')
        for c in columns:
            val = footer.get(c["key"])
            if val is None:
                parts.append('<div></div>')
                continue
            fmt = c.get("fmt", "int")
            color = COLORS["coral"] if c.get("highlight") else COLORS["white"]
            if fmt == "eur":
                txt = _fmt_eur(val)
            elif fmt == "eur_k":
                txt = _fmt_eur(val, k=True)
            elif fmt == "pct":
                txt = f"{val:.1f}%"
            elif fmt == "days":
                txt = f"{int(val)} j"
            elif fmt == "money2":
                txt = f"{val:.2f} €"
            else:
                txt = _fmt_int(val)
            parts.append(f'<div style="color:{color};font-weight:700;">{txt}</div>')
        parts.append('</div>')

    parts.append('</div>')
    st.markdown("".join(parts), unsafe_allow_html=True)
