"""Client API Zelty pour le dashboard Kajiro.

Doc: https://docs.zelty.fr (gated). Le client cible la base publique https://api.zelty.fr
avec auth Basic (la clé Zelty est déjà du base64 `chain_id:secret`). Endpoints typiques:
  GET /v2/restaurants
  GET /v2/orders?status=255&restaurant_id=...&date_from=...&date_to=...&page=...&per_page=...

Si l'API réelle diffère, ajuster ENDPOINTS ci-dessous sans toucher au reste.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

PARIS = ZoneInfo("Europe/Paris")

ENDPOINTS = {
    "restaurants": "/v2/restaurants",
    "orders": "/v2/orders",
    "articles": "/v2/articles",
}

# Status code "fermé/payé" — confirmé par la doc KEYBAN
ORDER_STATUS_CLOSED = 255

PER_PAGE = 200
MAX_PARALLEL = 4


class ZeltyError(RuntimeError):
    pass


def _secret(key: str, default: str | None = None) -> str | None:
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return default


def _headers() -> dict[str, str]:
    api_key = _secret("ZELTY_API_KEY")
    scheme = _secret("ZELTY_AUTH_SCHEME", "Basic")
    if not api_key:
        raise ZeltyError("ZELTY_API_KEY manquant dans .streamlit/secrets.toml")
    return {
        "Authorization": f"{scheme} {api_key}",
        "Accept": "application/json",
        "User-Agent": "Kajiro-Dashboard/1.0",
    }


def _base_url() -> str:
    return (_secret("ZELTY_BASE_URL", "https://api.zelty.fr") or "").rstrip("/")


@retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
)
def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    url = f"{_base_url()}{path}"
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", "2"))
        time.sleep(retry_after)
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    if resp.status_code == 401:
        raise ZeltyError("Auth Zelty rejetée (401). Vérifier ZELTY_API_KEY / ZELTY_AUTH_SCHEME.")
    if resp.status_code >= 400:
        raise ZeltyError(f"Zelty {resp.status_code} sur {path}: {resp.text[:300]}")
    try:
        return resp.json()
    except ValueError as e:
        raise ZeltyError(f"Réponse non-JSON sur {path}: {resp.text[:300]}") from e


def _unwrap_list(payload: Any) -> list[dict]:
    """Zelty enveloppe parfois la liste dans {data: [...]} ou {results: [...]}."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("data", "results", "items", "restaurants", "orders", "articles"):
            if isinstance(payload.get(k), list):
                return payload[k]
    return []


@st.cache_data(ttl=3600, show_spinner=False)
def list_restaurants() -> pd.DataFrame:
    """Liste les restaurants accessibles par la clé groupe."""
    raw = _get(ENDPOINTS["restaurants"])
    items = _unwrap_list(raw)
    rows = []
    for r in items:
        rows.append({
            "id": r.get("id") or r.get("restaurant_id"),
            "name": r.get("name") or r.get("label") or f"Resto {r.get('id')}",
            "city": r.get("city") or r.get("address", {}).get("city") if isinstance(r.get("address"), dict) else r.get("city"),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.dropna(subset=["id"]).reset_index(drop=True)
    df["id"] = df["id"].astype(int)
    return df


def _fmt_date(d: date | datetime) -> str:
    if isinstance(d, datetime):
        return d.astimezone(PARIS).strftime("%Y-%m-%dT%H:%M:%S")
    return d.strftime("%Y-%m-%d")


def _fetch_orders_page(restaurant_id: int, date_from: date, date_to: date, page: int) -> list[dict]:
    params = {
        "restaurant_id": restaurant_id,
        "status": ORDER_STATUS_CLOSED,
        "date_from": _fmt_date(date_from),
        "date_to": _fmt_date(date_to),
        "page": page,
        "per_page": PER_PAGE,
    }
    payload = _get(ENDPOINTS["orders"], params=params)
    return _unwrap_list(payload)


def _fetch_all_orders(restaurant_id: int, date_from: date, date_to: date) -> list[dict]:
    all_orders: list[dict] = []
    page = 1
    while True:
        batch = _fetch_orders_page(restaurant_id, date_from, date_to, page)
        if not batch:
            break
        all_orders.extend(batch)
        if len(batch) < PER_PAGE:
            break
        page += 1
        if page > 200:  # safety
            break
    return all_orders


@st.cache_data(ttl=900, show_spinner=False)
def fetch_sales_by_product(
    restaurant_ids: tuple[int, ...],
    date_from: date,
    date_to: date,
) -> pd.DataFrame:
    """Agrège les ventes par produit sur la période + ensemble de restaurants.

    Retourne un DataFrame: nom, qte, ht, ttc, prix_moy, pct_ca, pct_qte
    """
    if not restaurant_ids:
        return pd.DataFrame(columns=["nom", "qte", "ht", "ttc", "prix_moy", "pct_ca", "pct_qte"])

    rows_by_product: dict[str, dict[str, float]] = {}

    def process_orders(orders: list[dict]) -> None:
        for o in orders:
            lines = o.get("lines") or o.get("items") or o.get("order_lines") or []
            for line in lines:
                name = (line.get("name") or line.get("article_name") or line.get("label") or "").strip()
                if not name:
                    continue
                qty = _to_float(line.get("quantity") or line.get("qty") or 0)
                if qty <= 0:
                    continue
                ht = _to_float(line.get("total_ht") or line.get("ht") or line.get("amount_ht") or 0) / 100.0
                ttc = _to_float(line.get("total") or line.get("total_ttc") or line.get("amount") or 0) / 100.0
                if ht == 0 and ttc > 0:
                    # estimation HT à 10% TVA resto si HT non fourni
                    ht = ttc / 1.10
                acc = rows_by_product.setdefault(name, {"qte": 0.0, "ht": 0.0, "ttc": 0.0})
                acc["qte"] += qty
                acc["ht"] += ht
                acc["ttc"] += ttc

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futures = {
            pool.submit(_fetch_all_orders, rid, date_from, date_to): rid
            for rid in restaurant_ids
        }
        for fut in as_completed(futures):
            try:
                process_orders(fut.result())
            except ZeltyError as e:
                st.warning(f"Restaurant {futures[fut]} — {e}")

    if not rows_by_product:
        return pd.DataFrame(columns=["nom", "qte", "ht", "ttc", "prix_moy", "pct_ca", "pct_qte"])

    df = pd.DataFrame([
        {"nom": name, "qte": int(v["qte"]), "ht": v["ht"], "ttc": v["ttc"]}
        for name, v in rows_by_product.items()
    ])
    total_ht = df["ht"].sum() or 1
    total_qte = df["qte"].sum() or 1
    df["prix_moy"] = df.apply(lambda r: r["ht"] / r["qte"] if r["qte"] else 0, axis=1)
    df["pct_ca"] = df["ht"] / total_ht * 100
    df["pct_qte"] = df["qte"] / total_qte * 100
    df = df.sort_values("ht", ascending=False).reset_index(drop=True)
    return df


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def health_check() -> tuple[bool, str]:
    """Test la connexion à l'API. Retourne (ok, message)."""
    try:
        df = list_restaurants()
        return True, f"OK — {len(df)} restaurant(s) accessible(s)"
    except ZeltyError as e:
        return False, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"Erreur inattendue: {e}"
