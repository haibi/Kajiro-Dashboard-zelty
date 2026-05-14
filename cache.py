"""Cache SQLite local pour Zelty.

Les ventes passées sont **immuables** : une fois une journée fermée (clôture passée),
les données ne bougent plus. On les stocke localement et on n'interroge plus l'API
pour ces dates.

Stratégie :
- Pour chaque (resource, restaurant_id, date) on note qu'on a synchronisé
- Aujourd'hui (date courante) n'est JAMAIS marqué synchronisé → toujours re-fetch
- Hier et avant : si déjà en base, retour direct sans appel API

DB location : ./data/zelty_cache.db (gitignoré). Persistant entre les reruns
Streamlit, wipé seulement aux redéploiements Streamlit Cloud (acceptable).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

DB_PATH = Path(__file__).parent / "data" / "zelty_cache.db"


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS closures (
            date TEXT NOT NULL,
            restaurant_id INTEGER NOT NULL,
            turnover REAL NOT NULL,
            taxes REAL NOT NULL,
            PRIMARY KEY (date, restaurant_id)
        );
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY,
            restaurant_id INTEGER NOT NULL,
            closed_at TEXT,
            closed_date TEXT NOT NULL,
            mode TEXT,
            source TEXT,
            origin TEXT,
            ttc REAL,
            ht REAL
        );
        CREATE INDEX IF NOT EXISTS idx_orders_resto_date
            ON orders (restaurant_id, closed_date);
        CREATE TABLE IF NOT EXISTS sync_log (
            resource TEXT NOT NULL,
            restaurant_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            synced_at TEXT NOT NULL,
            PRIMARY KEY (resource, restaurant_id, date)
        );
        """)


# ---------------------------------------------------------------------------
# Sync state
# ---------------------------------------------------------------------------
def synced_days(resource: str, restaurant_id: int, date_from: date, date_to: date) -> set[date]:
    """Renvoie l'ensemble des jours déjà synchronisés (donc à NE PAS refaire)."""
    today = date.today()
    cutoff = min(date_to, today - timedelta(days=1))  # aujourd'hui jamais "définitivement" sync
    if cutoff < date_from:
        return set()
    with _conn() as c:
        cur = c.execute(
            "SELECT date FROM sync_log WHERE resource=? AND restaurant_id=? AND date BETWEEN ? AND ?",
            (resource, restaurant_id, date_from.isoformat(), cutoff.isoformat()),
        )
        return {date.fromisoformat(row["date"]) for row in cur.fetchall()}


def mark_synced(resource: str, restaurant_id: int, days: list[date]) -> None:
    if not days:
        return
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _conn() as c:
        c.executemany(
            "INSERT OR REPLACE INTO sync_log (resource, restaurant_id, date, synced_at) VALUES (?, ?, ?, ?)",
            [(resource, restaurant_id, d.isoformat(), now) for d in days],
        )


def missing_ranges(restaurant_id: int, resource: str, date_from: date, date_to: date) -> list[tuple[date, date]]:
    """Retourne les sous-plages [start, end] NON synchronisées + today (toujours).

    Aujourd'hui est toujours inclus comme une plage à fetch (1 jour).
    """
    today = date.today()
    synced = synced_days(resource, restaurant_id, date_from, date_to)

    missing: list[date] = []
    d = date_from
    while d <= date_to:
        if d == today:  # toujours re-fetch today
            pass
        elif d not in synced:
            missing.append(d)
        d += timedelta(days=1)

    # Regrouper les jours consécutifs
    ranges: list[tuple[date, date]] = []
    if missing:
        start = missing[0]
        prev = missing[0]
        for d in missing[1:]:
            if (d - prev).days == 1:
                prev = d
            else:
                ranges.append((start, prev))
                start = d
                prev = d
        ranges.append((start, prev))

    # Aujourd'hui à part (toujours)
    if date_from <= today <= date_to:
        ranges.append((today, today))

    return ranges


# ---------------------------------------------------------------------------
# Closures storage
# ---------------------------------------------------------------------------
def store_closures(rows: list[dict]) -> None:
    if not rows:
        return
    with _conn() as c:
        c.executemany(
            "INSERT OR REPLACE INTO closures (date, restaurant_id, turnover, taxes) VALUES (?, ?, ?, ?)",
            [(r["date"], r["restaurant_id"], float(r["turnover"]), float(r["taxes"])) for r in rows],
        )


def query_closures(restaurant_ids: list[int], date_from: date, date_to: date) -> list[dict]:
    if not restaurant_ids:
        return []
    placeholders = ",".join("?" * len(restaurant_ids))
    with _conn() as c:
        cur = c.execute(
            f"SELECT date, restaurant_id, turnover, taxes FROM closures "
            f"WHERE restaurant_id IN ({placeholders}) AND date BETWEEN ? AND ? "
            f"ORDER BY restaurant_id, date",
            [*restaurant_ids, date_from.isoformat(), date_to.isoformat()],
        )
        return [dict(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Orders storage
# ---------------------------------------------------------------------------
def store_orders(rows: list[dict]) -> None:
    if not rows:
        return
    with _conn() as c:
        c.executemany(
            """INSERT OR REPLACE INTO orders
               (order_id, restaurant_id, closed_at, closed_date, mode, source, origin, ttc, ht)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(
                r["order_id"], r["restaurant_id"],
                r.get("closed_at"), r["closed_date"],
                r.get("mode"), r.get("source"), r.get("origin"),
                float(r.get("ttc") or 0), float(r.get("ht") or 0),
            ) for r in rows],
        )


def delete_orders_for_day(restaurant_id: int, day: date) -> None:
    """Pour today on supprime puis on réinsère (commandes mises à jour en live)."""
    with _conn() as c:
        c.execute(
            "DELETE FROM orders WHERE restaurant_id=? AND closed_date=?",
            (restaurant_id, day.isoformat()),
        )


def query_orders(restaurant_ids: list[int], date_from: date, date_to: date) -> list[dict]:
    if not restaurant_ids:
        return []
    placeholders = ",".join("?" * len(restaurant_ids))
    with _conn() as c:
        cur = c.execute(
            f"SELECT order_id, restaurant_id, closed_at, closed_date, mode, source, origin, ttc, ht "
            f"FROM orders WHERE restaurant_id IN ({placeholders}) "
            f"AND closed_date BETWEEN ? AND ?",
            [*restaurant_ids, date_from.isoformat(), date_to.isoformat()],
        )
        return [dict(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
def stats() -> dict:
    init_db()
    with _conn() as c:
        n_closures = c.execute("SELECT COUNT(*) AS n FROM closures").fetchone()["n"]
        n_orders = c.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"]
        n_synced = c.execute("SELECT COUNT(*) AS n FROM sync_log").fetchone()["n"]
        oldest = c.execute("SELECT MIN(date) AS d FROM closures").fetchone()["d"]
        newest = c.execute("SELECT MAX(date) AS d FROM closures").fetchone()["d"]
    return {
        "closures": n_closures,
        "orders": n_orders,
        "synced_days": n_synced,
        "oldest": oldest,
        "newest": newest,
    }


def clear_all() -> None:
    """Pour le bouton 'Rafraîchir' — vide tout le cache."""
    with _conn() as c:
        c.execute("DELETE FROM closures")
        c.execute("DELETE FROM orders")
        c.execute("DELETE FROM sync_log")
