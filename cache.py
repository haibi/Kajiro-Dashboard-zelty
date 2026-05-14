"""Cache persistant Postgres (Supabase) pour les ventes Zelty.

Stratégie identique à la version SQLite, mais en ligne :
- Les ventes passées (< today) sont **immuables** → stockées une fois, jamais re-fetchées
- Aujourd'hui est toujours re-synchronisé (delete then insert)
- Survit aux redéploiements Streamlit Cloud (DB hébergée chez Supabase)
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from typing import Iterator

import psycopg
import streamlit as st
from psycopg_pool import ConnectionPool


# ---------------------------------------------------------------------------
# Connection pool (singleton via st.cache_resource)
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _pool() -> ConnectionPool:
    url = st.secrets.get("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL manquant dans .streamlit/secrets.toml")
    return ConnectionPool(
        url,
        min_size=1,
        max_size=4,
        timeout=30,
        # NOTE: prepare_threshold=None désactive les prepared statements ;
        # obligatoire avec le pooler Supabase en mode transaction (port 6543).
        kwargs={"connect_timeout": 10, "prepare_threshold": None},
        open=True,
    )


@contextmanager
def _conn() -> Iterator[psycopg.Connection]:
    pool = _pool()
    with pool.connection() as c:
        yield c


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS closures (
    date         DATE        NOT NULL,
    restaurant_id INTEGER    NOT NULL,
    turnover     NUMERIC(14,2) NOT NULL,
    taxes        NUMERIC(14,2) NOT NULL,
    PRIMARY KEY (date, restaurant_id)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id      BIGINT      PRIMARY KEY,
    restaurant_id INTEGER     NOT NULL,
    closed_at     TIMESTAMPTZ,
    closed_date   DATE        NOT NULL,
    mode          TEXT,
    source        TEXT,
    origin        TEXT,
    ttc           NUMERIC(12,2),
    ht            NUMERIC(12,2),
    server_name   TEXT,
    customer_id   BIGINT,
    customer_name TEXT,
    discount_ttc  NUMERIC(12,2) DEFAULT 0,
    discount_count INTEGER DEFAULT 0
);
-- Migration: ajouter colonnes si table existait sans (idempotent)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS server_name TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_id BIGINT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_name TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS discount_ttc NUMERIC(12,2) DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS discount_count INTEGER DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_orders_resto_date
    ON orders (restaurant_id, closed_date);

CREATE TABLE IF NOT EXISTS sync_log (
    resource      TEXT        NOT NULL,
    restaurant_id INTEGER     NOT NULL,
    date          DATE        NOT NULL,
    synced_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (resource, restaurant_id, date)
);

-- Lignes de commande (items) — un produit = une ligne dans une commande
-- Récupérées via ?expand[]=items sur l'API Zelty
CREATE TABLE IF NOT EXISTS order_items (
    line_id       BIGINT      PRIMARY KEY,
    order_id      BIGINT      NOT NULL,
    restaurant_id INTEGER     NOT NULL,
    closed_date   DATE        NOT NULL,
    item_id       TEXT,
    name          TEXT        NOT NULL,
    item_type     TEXT,
    ttc           NUMERIC(12,2) NOT NULL DEFAULT 0,
    tax_amount    NUMERIC(12,2) NOT NULL DEFAULT 0,
    modifiers     JSONB
);
CREATE INDEX IF NOT EXISTS idx_items_resto_date ON order_items (restaurant_id, closed_date);
CREATE INDEX IF NOT EXISTS idx_items_item_id ON order_items (item_id);
CREATE INDEX IF NOT EXISTS idx_items_order_id ON order_items (order_id);

-- Utilisateurs autorisés + scope d'accès
-- restaurant_ids NULL = accès à tous les restaurants
-- restaurant_ids = []  = aucun accès (lock-out explicite)
-- restaurant_ids = [id, id, ...] = uniquement ceux-là
CREATE TABLE IF NOT EXISTS users (
    email          TEXT        PRIMARY KEY,
    role           TEXT        NOT NULL DEFAULT 'viewer'
                               CHECK (role IN ('admin', 'viewer')),
    restaurant_ids INTEGER[],
    password_hash  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
"""


@st.cache_resource(show_spinner=False)
def init_db() -> bool:
    """Crée les tables si elles n'existent pas. Idempotent. Retour True si OK."""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(_SCHEMA)
    return True


# ---------------------------------------------------------------------------
# Sync state
# ---------------------------------------------------------------------------
def synced_days(resource: str, restaurant_id: int, date_from: date, date_to: date) -> set[date]:
    """Renvoie l'ensemble des jours déjà synchronisés (donc à NE PAS refaire)."""
    today = date.today()
    cutoff = min(date_to, today - timedelta(days=1))
    if cutoff < date_from:
        return set()
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT date FROM sync_log "
                "WHERE resource=%s AND restaurant_id=%s AND date BETWEEN %s AND %s",
                (resource, restaurant_id, date_from, cutoff),
            )
            return {row[0] for row in cur.fetchall()}


def mark_synced(resource: str, restaurant_id: int, days: list[date]) -> None:
    if not days:
        return
    with _conn() as c:
        with c.cursor() as cur:
            cur.executemany(
                "INSERT INTO sync_log (resource, restaurant_id, date) VALUES (%s, %s, %s) "
                "ON CONFLICT (resource, restaurant_id, date) DO UPDATE SET synced_at = NOW()",
                [(resource, restaurant_id, d) for d in days],
            )


def missing_ranges(restaurant_id: int, resource: str, date_from: date, date_to: date) -> list[tuple[date, date]]:
    """Sous-plages [start, end] NON synchronisées + today (toujours)."""
    today = date.today()
    synced = synced_days(resource, restaurant_id, date_from, date_to)

    missing: list[date] = []
    d = date_from
    while d <= date_to:
        if d == today:
            pass
        elif d not in synced:
            missing.append(d)
        d += timedelta(days=1)

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

    if date_from <= today <= date_to:
        ranges.append((today, today))

    return ranges


# ---------------------------------------------------------------------------
# Closures
# ---------------------------------------------------------------------------
def store_closures(rows: list[dict]) -> None:
    if not rows:
        return
    with _conn() as c:
        with c.cursor() as cur:
            cur.executemany(
                "INSERT INTO closures (date, restaurant_id, turnover, taxes) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (date, restaurant_id) DO UPDATE "
                "SET turnover = EXCLUDED.turnover, taxes = EXCLUDED.taxes",
                [(r["date"], r["restaurant_id"], r["turnover"], r["taxes"]) for r in rows],
            )


def query_closures(restaurant_ids: list[int], date_from: date, date_to: date) -> list[dict]:
    if not restaurant_ids:
        return []
    with _conn() as c:
        with c.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                "SELECT date, restaurant_id, turnover, taxes FROM closures "
                "WHERE restaurant_id = ANY(%s) AND date BETWEEN %s AND %s "
                "ORDER BY restaurant_id, date",
                (restaurant_ids, date_from, date_to),
            )
            rows = cur.fetchall()
    # Convert Decimal → float pour pandas
    for r in rows:
        r["date"] = r["date"].isoformat() if r["date"] else None
        r["turnover"] = float(r["turnover"])
        r["taxes"] = float(r["taxes"])
    return rows


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
def store_orders(rows: list[dict]) -> None:
    if not rows:
        return
    with _conn() as c:
        with c.cursor() as cur:
            cur.executemany(
                """INSERT INTO orders
                   (order_id, restaurant_id, closed_at, closed_date, mode, source, origin, ttc, ht,
                    server_name, customer_id, customer_name, discount_ttc, discount_count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (order_id) DO UPDATE SET
                     restaurant_id  = EXCLUDED.restaurant_id,
                     closed_at      = EXCLUDED.closed_at,
                     closed_date    = EXCLUDED.closed_date,
                     mode           = EXCLUDED.mode,
                     source         = EXCLUDED.source,
                     origin         = EXCLUDED.origin,
                     ttc            = EXCLUDED.ttc,
                     ht             = EXCLUDED.ht,
                     server_name    = EXCLUDED.server_name,
                     customer_id    = EXCLUDED.customer_id,
                     customer_name  = EXCLUDED.customer_name,
                     discount_ttc   = EXCLUDED.discount_ttc,
                     discount_count = EXCLUDED.discount_count""",
                [(
                    r["order_id"], r["restaurant_id"],
                    r.get("closed_at") or None, r["closed_date"],
                    r.get("mode"), r.get("source"), r.get("origin"),
                    r.get("ttc") or 0, r.get("ht") or 0,
                    r.get("server_name"), r.get("customer_id"), r.get("customer_name"),
                    r.get("discount_ttc") or 0, r.get("discount_count") or 0,
                ) for r in rows],
            )


def delete_orders_for_day(restaurant_id: int, day: date) -> None:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "DELETE FROM orders WHERE restaurant_id=%s AND closed_date=%s",
                (restaurant_id, day),
            )


def store_items(rows: list[dict]) -> None:
    """Stocke les lignes-produit (1 ligne = 1 dish dans une commande)."""
    if not rows:
        return
    import json as _json
    with _conn() as c:
        with c.cursor() as cur:
            cur.executemany(
                """INSERT INTO order_items
                   (line_id, order_id, restaurant_id, closed_date, item_id, name, item_type, ttc, tax_amount, modifiers)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (line_id) DO UPDATE SET
                     order_id      = EXCLUDED.order_id,
                     restaurant_id = EXCLUDED.restaurant_id,
                     closed_date   = EXCLUDED.closed_date,
                     item_id       = EXCLUDED.item_id,
                     name          = EXCLUDED.name,
                     item_type     = EXCLUDED.item_type,
                     ttc           = EXCLUDED.ttc,
                     tax_amount    = EXCLUDED.tax_amount,
                     modifiers     = EXCLUDED.modifiers""",
                [(
                    r["line_id"], r["order_id"], r["restaurant_id"], r["closed_date"],
                    r.get("item_id"), r["name"], r.get("item_type"),
                    r.get("ttc") or 0, r.get("tax_amount") or 0,
                    _json.dumps(r.get("modifiers") or [], ensure_ascii=False),
                ) for r in rows],
            )


def delete_items_for_day(restaurant_id: int, day: date) -> None:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "DELETE FROM order_items WHERE restaurant_id=%s AND closed_date=%s",
                (restaurant_id, day),
            )


def query_product_sales(
    restaurant_ids: list[int],
    date_from: date,
    date_to: date,
) -> list[dict]:
    """Agrège les ventes par produit : nom, item_id, quantité, CA TTC, CA HT."""
    if not restaurant_ids:
        return []
    with _conn() as c:
        with c.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                """SELECT
                     COALESCE(item_id, name) AS key,
                     MAX(item_id)            AS item_id,
                     name                    AS nom,
                     COUNT(*)                AS qte,
                     SUM(ttc)                AS ttc,
                     SUM(ttc - tax_amount)   AS ht,
                     MAX(item_type)          AS type
                   FROM order_items
                   WHERE restaurant_id = ANY(%s)
                     AND closed_date BETWEEN %s AND %s
                   GROUP BY name, COALESCE(item_id, name)
                   ORDER BY ttc DESC""",
                (restaurant_ids, date_from, date_to),
            )
            rows = cur.fetchall()
    for r in rows:
        r["qte"] = int(r["qte"])
        r["ttc"] = float(r["ttc"] or 0)
        r["ht"] = float(r["ht"] or 0)
        r["prix_moy"] = (r["ttc"] / r["qte"]) if r["qte"] else 0
    return rows


def query_orders(restaurant_ids: list[int], date_from: date, date_to: date) -> list[dict]:
    if not restaurant_ids:
        return []
    with _conn() as c:
        with c.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                "SELECT order_id, restaurant_id, closed_at, closed_date, mode, source, origin, "
                "ttc, ht, server_name, customer_id, customer_name, discount_ttc, discount_count "
                "FROM orders WHERE restaurant_id = ANY(%s) "
                "AND closed_date BETWEEN %s AND %s",
                (restaurant_ids, date_from, date_to),
            )
            rows = cur.fetchall()
    for r in rows:
        r["closed_date"] = r["closed_date"].isoformat() if r["closed_date"] else None
        r["closed_at"] = r["closed_at"].isoformat() if r["closed_at"] else None
        r["ttc"] = float(r["ttc"]) if r["ttc"] is not None else 0
        r["ht"] = float(r["ht"]) if r["ht"] is not None else 0
        r["discount_ttc"] = float(r["discount_ttc"]) if r["discount_ttc"] is not None else 0
        r["discount_count"] = int(r["discount_count"]) if r["discount_count"] is not None else 0
    return rows


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
def stats() -> dict:
    try:
        init_db()
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM closures")
                n_closures = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM orders")
                n_orders = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM sync_log")
                n_synced = cur.fetchone()[0]
                cur.execute("SELECT MIN(date), MAX(date) FROM closures")
                oldest, newest = cur.fetchone()
        return {
            "closures": n_closures,
            "orders": n_orders,
            "synced_days": n_synced,
            "oldest": oldest.isoformat() if oldest else None,
            "newest": newest.isoformat() if newest else None,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:120], "closures": 0, "orders": 0, "synced_days": 0,
                "oldest": None, "newest": None}


def clear_all() -> None:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("TRUNCATE closures, orders, sync_log")


# ---------------------------------------------------------------------------
# Users (gestion des accès)
# ---------------------------------------------------------------------------
import hashlib
import hmac as _hmac
import secrets as _secrets


def hash_password(plain: str) -> str:
    """PBKDF2-SHA256 avec salt aléatoire 128 bits, 100k itérations."""
    if not plain:
        raise ValueError("Mot de passe vide")
    salt = _secrets.token_hex(16)
    iters = 100_000
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt.encode(), iters)
    return f"pbkdf2_sha256${iters}${salt}${dk.hex()}"


def verify_password(plain: str, hashed: str | None) -> bool:
    """Vérifie un mot de passe contre un hash stocké."""
    if not hashed or not plain:
        return False
    try:
        algo, iters_str, salt, hash_hex = hashed.split("$", 3)
    except (ValueError, AttributeError):
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        iters = int(iters_str)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt.encode(), iters)
    return _hmac.compare_digest(dk.hex(), hash_hex)


def set_password(email: str, plain: str) -> None:
    """Définit le mot de passe d'un utilisateur."""
    email = (email or "").strip().lower()
    if not email:
        raise ValueError("Email vide")
    hashed = hash_password(plain)
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash=%s, updated_at=NOW() WHERE email=%s",
                (hashed, email),
            )
            if cur.rowcount == 0:
                raise ValueError(f"Utilisateur {email} introuvable")


def bootstrap_admin(email: str, default_password: str | None = None) -> None:
    """Garantit qu'un compte admin avec accès total existe.

    Si aucun admin n'existe : crée `email` comme admin avec tous les restos.
    Si `default_password` fourni ET aucun password_hash : le pose.
    Idempotent.
    """
    email = (email or "").strip().lower()
    if not email:
        return
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
            (n_admins,) = cur.fetchone()
            if n_admins == 0:
                cur.execute(
                    "INSERT INTO users (email, role, restaurant_ids) "
                    "VALUES (%s, 'admin', NULL) ON CONFLICT (email) DO UPDATE "
                    "SET role = 'admin', restaurant_ids = NULL",
                    (email,),
                )
            # Si default password fourni et user n'a pas encore de hash, on le pose
            if default_password:
                cur.execute("SELECT password_hash FROM users WHERE email=%s", (email,))
                row = cur.fetchone()
                if row and not row[0]:
                    hashed = hash_password(default_password)
                    cur.execute(
                        "UPDATE users SET password_hash=%s WHERE email=%s",
                        (hashed, email),
                    )


def get_user(email: str) -> dict | None:
    email = (email or "").strip().lower()
    if not email:
        return None
    with _conn() as c:
        with c.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                "SELECT email, role, restaurant_ids, password_hash FROM users WHERE email = %s",
                (email,),
            )
            return cur.fetchone()


def list_users() -> list[dict]:
    with _conn() as c:
        with c.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                "SELECT email, role, restaurant_ids, created_at "
                "FROM users ORDER BY role DESC, email"
            )
            return cur.fetchall()


def upsert_user(
    email: str,
    role: str,
    restaurant_ids: list[int] | None,
    password: str | None = None,
) -> None:
    """Crée/met à jour un user. `restaurant_ids=None` = accès à tous.
    Si `password` est fourni, il est haché et stocké."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("Email invalide")
    if role not in {"admin", "viewer"}:
        raise ValueError("role doit être 'admin' ou 'viewer'")
    hashed = hash_password(password) if password else None
    with _conn() as c:
        with c.cursor() as cur:
            if hashed:
                cur.execute(
                    "INSERT INTO users (email, role, restaurant_ids, password_hash) "
                    "VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (email) DO UPDATE SET "
                    "  role = EXCLUDED.role, "
                    "  restaurant_ids = EXCLUDED.restaurant_ids, "
                    "  password_hash = EXCLUDED.password_hash, "
                    "  updated_at = NOW()",
                    (email, role, restaurant_ids, hashed),
                )
            else:
                cur.execute(
                    "INSERT INTO users (email, role, restaurant_ids) "
                    "VALUES (%s, %s, %s) "
                    "ON CONFLICT (email) DO UPDATE SET "
                    "  role = EXCLUDED.role, "
                    "  restaurant_ids = EXCLUDED.restaurant_ids, "
                    "  updated_at = NOW()",
                    (email, role, restaurant_ids),
                )


def delete_user(email: str) -> None:
    email = (email or "").strip().lower()
    if not email:
        return
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("DELETE FROM users WHERE email = %s", (email,))
