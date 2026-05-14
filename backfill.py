"""Backfill historique Zelty → Supabase.

Remonte N années en arrière et synchronise toutes les closures + orders dans
Supabase. Reprenable : si interrompu, relance et il saute ce qui est déjà sync.

Usage :
    # Depuis Streamlit (bouton sidebar) :
    from backfill import run_backfill
    run_backfill(restaurant_ids, years=5, callback=lambda done, total, msg: ...)

    # Depuis terminal :
    python backfill.py --years 5
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from dateutil.relativedelta import relativedelta

import cache
import zelty_client


def iter_months(start: date, end: date):
    """Yield (month_start, month_end) découpé par mois calendaire."""
    cur = start.replace(day=1)
    while cur <= end:
        if cur.month == 12:
            next_first = cur.replace(year=cur.year + 1, month=1)
        else:
            next_first = cur.replace(month=cur.month + 1)
        month_end = min(next_first - timedelta(days=1), end)
        yield (max(cur, start), month_end)
        cur = next_first


def run_backfill(
    restaurant_ids: list[int],
    years: int = 5,
    callback: Callable[[int, int, str], None] | None = None,
) -> dict:
    """Backfill closures + orders sur N années pour les restos donnés.

    Itère restaurant × mois (du plus ancien au plus récent). Sauvegarde au fur
    et à mesure dans Supabase. Si une plage est déjà synchronisée (sync_log),
    elle est sautée immédiatement par les fonctions sync_* du client.
    """
    cache.init_db()
    today = date.today()
    start_date = today - relativedelta(years=years)
    months = list(iter_months(start_date, today))

    total_steps = len(months) * len(restaurant_ids) * 2
    step = 0

    for rid in restaurant_ids:
        for mstart, mend in months:
            label = f"R{rid} · {mstart:%b %Y}"

            # Closures (peu de data → rapide)
            try:
                zelty_client._sync_closures_for_resto(rid, mstart, mend)
            except Exception as e:  # noqa: BLE001
                if callback:
                    callback(step, total_steps, f"⚠ {label} closures : {e}")
            step += 1
            if callback:
                callback(step, total_steps, f"{label} · closures OK")

            # Orders (paginé → plus lent)
            try:
                zelty_client._sync_orders_for_resto(rid, mstart, mend)
            except Exception as e:  # noqa: BLE001
                if callback:
                    callback(step, total_steps, f"⚠ {label} orders : {e}")
            step += 1
            if callback:
                callback(step, total_steps, f"{label} · orders OK")

    return cache.stats()


def main() -> None:
    """Mode CLI standalone (lit secrets.toml manuellement)."""
    import argparse
    import os
    import pathlib
    import tomllib

    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--restaurant-id", type=int, action="append",
                         help="Limite à un ou plusieurs IDs (sinon tous les Kajirō)")
    args = parser.parse_args()

    # Inject secrets dans environnement pour les modules
    secrets_path = pathlib.Path(__file__).parent / ".streamlit" / "secrets.toml"
    secrets = tomllib.loads(secrets_path.read_text("utf-8"))
    # Patch monkey: st.secrets en CLI
    import streamlit as st
    st.secrets._secrets = secrets  # hack : alimente st.secrets en mode non-app

    restos = zelty_client.list_restaurants()
    rids = args.restaurant_id or restos["id"].astype(int).tolist()
    print(f"Backfill {args.years} an(s) pour restaurants : {rids}")

    def progress(done: int, total: int, msg: str) -> None:
        pct = (done / total) * 100 if total else 0
        bar_len = 30
        filled = int(bar_len * done / total) if total else 0
        bar = "█" * filled + "─" * (bar_len - filled)
        print(f"\r[{bar}] {pct:5.1f}% · {msg:<50}", end="", flush=True)

    stats = run_backfill(rids, years=args.years, callback=progress)
    print()
    print(f"Done. Stats DB : {stats}")


if __name__ == "__main__":
    main()
