"""Client API Zelty (v2.10).

Endpoints confirmés:
  GET /2.10/restaurants                 → liste {restaurants: [...]}
  GET /2.10/orders?from=&to=&restaurant_id=  → résumés (PAS de lignes produits)
  GET /2.10/closures?restaurant_id=&from=&to= → CA quotidien {closures: [...]}
  GET /2.10/catalogs                    → catalogues de menus
  GET /2.10/catalogs/{id}               → catalogue détaillé avec items

NOTE: l'endpoint pour les ventes par produit (best sellers) n'a pas été trouvé
dans les routes publiques. En attendant: fallback CSV (export Zelty BO).
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
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
API_VERSION = "2.10"
PER_PAGE = 200
MAX_PARALLEL = 2                  # Zelty rate-limit agressif
MAX_DAYS_PER_REQUEST = 31         # /orders refuse les intervalles > 31 j

# Restaurants accessibles via la clé groupe mais hors périmètre Kajirō.
# In Bun (id 6328) — concept séparé, ne fait pas partie des 7 enseignes Kajirō.
EXCLUDED_RESTAURANT_IDS: set[int] = {6328}


class ZeltyError(RuntimeError):
    pass


def _secret(key: str, default: str | None = None) -> str | None:
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return default


def _headers() -> dict[str, str]:
    api_key = _secret("ZELTY_API_KEY")
    scheme = _secret("ZELTY_AUTH_SCHEME", "Bearer")
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
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=15),
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
)
def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    """GET avec retry réseau + back-off long pour 429 (rate-limit Zelty)."""
    url = f"{_base_url()}{path}"
    for attempt in range(5):
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        if resp.status_code == 429:
            wait_s = int(resp.headers.get("Retry-After", "3")) + attempt * 2
            time.sleep(min(wait_s, 30))
            continue
        break
    if resp.status_code == 401:
        raise ZeltyError("Auth Zelty rejetée (401). Vérifier ZELTY_API_KEY / ZELTY_AUTH_SCHEME.")
    if resp.status_code >= 400:
        raise ZeltyError(f"Zelty {resp.status_code} sur {path}: {resp.text[:300]}")
    try:
        return resp.json()
    except ValueError as e:
        raise ZeltyError(f"Réponse non-JSON sur {path}: {resp.text[:300]}") from e


def _fmt_date(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _date_chunks(date_from: date, date_to: date, max_days: int = MAX_DAYS_PER_REQUEST) -> list[tuple[date, date]]:
    """Découpe une plage en sous-plages d'au plus `max_days` jours."""
    chunks: list[tuple[date, date]] = []
    current = date_from
    step = timedelta(days=max_days - 1)
    while current <= date_to:
        end = min(current + step, date_to)
        chunks.append((current, end))
        current = end + timedelta(days=1)
    return chunks


# ---------------------------------------------------------------------------
# Restaurants
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def list_restaurants() -> pd.DataFrame:
    """Liste des restaurants accessibles avec la clé groupe."""
    payload = _get(f"/{API_VERSION}/restaurants")
    items = payload.get("restaurants", []) if isinstance(payload, dict) else []
    rows = []
    for r in items:
        if r.get("disable"):
            continue
        rid = int(r["id"])
        if rid in EXCLUDED_RESTAURANT_IDS:
            continue
        rows.append({
            "id": rid,
            "name": r.get("name") or f"Resto {rid}",
            "currency": r.get("currency", "EUR"),
            "country": r.get("country_code", "FR"),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("name").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Closures (CA quotidien par restaurant)
# ---------------------------------------------------------------------------
def _fetch_closures_one(restaurant_id: int, date_from: date, date_to: date) -> list[dict]:
    """Closures pour un resto sur une plage (chunkée en 31j max)."""
    all_rows: list[dict] = []
    for cf, ct in _date_chunks(date_from, date_to):
        payload = _get(f"/{API_VERSION}/closures", params={
            "restaurant_id": restaurant_id,
            "from": _fmt_date(cf),
            "to": _fmt_date(ct),
        })
        if isinstance(payload, dict):
            all_rows.extend(payload.get("closures", []))
    return all_rows


@st.cache_data(ttl=900, show_spinner=False)
def fetch_closures(
    restaurant_ids: tuple[int, ...],
    date_from: date,
    date_to: date,
) -> pd.DataFrame:
    """CA et taxes quotidiens par restaurant.

    Colonnes : date, restaurant_id, turnover (€ TTC), taxes (€).
    Les montants Zelty sont en centimes — convertis en euros ici.
    """
    if not restaurant_ids:
        return pd.DataFrame(columns=["date", "restaurant_id", "turnover", "taxes"])

    all_rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futures = {
            pool.submit(_fetch_closures_one, rid, date_from, date_to): rid
            for rid in restaurant_ids
        }
        for fut in as_completed(futures):
            try:
                for c in fut.result():
                    all_rows.append({
                        "date": c.get("date"),
                        "restaurant_id": int(c.get("id_restaurant")),
                        "turnover": _to_float(c.get("turnover")) / 100.0,
                        "taxes": _to_float(c.get("taxes")) / 100.0,
                    })
            except ZeltyError as e:
                st.warning(f"Restaurant {futures[fut]} — {e}")
    if not all_rows:
        return pd.DataFrame(columns=["date", "restaurant_id", "turnover", "taxes"])
    return pd.DataFrame(all_rows).sort_values(["restaurant_id", "date"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Orders (résumés uniquement — pas de lignes produits dans v2.10)
# ---------------------------------------------------------------------------
def _fetch_orders_one(restaurant_id: int, date_from: date, date_to: date) -> list[dict]:
    """Orders pour un resto sur une plage (chunkée en 31j max)."""
    all_rows: list[dict] = []
    for cf, ct in _date_chunks(date_from, date_to):
        payload = _get(f"/{API_VERSION}/orders", params={
            "restaurant_id": restaurant_id,
            "from": _fmt_date(cf),
            "to": _fmt_date(ct),
        })
        if isinstance(payload, dict):
            all_rows.extend(payload.get("orders", []))
    return all_rows


@st.cache_data(ttl=900, show_spinner=False)
def fetch_orders_summary(
    restaurant_ids: tuple[int, ...],
    date_from: date,
    date_to: date,
) -> pd.DataFrame:
    """Résumés de commandes : nb commandes, CA HT, CA TTC, mode, source par resto."""
    if not restaurant_ids:
        return pd.DataFrame(columns=["restaurant_id", "n_orders", "ht", "ttc", "by_mode"])

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futures = {
            pool.submit(_fetch_orders_one, rid, date_from, date_to): rid
            for rid in restaurant_ids
        }
        for fut in as_completed(futures):
            rid = futures[fut]
            try:
                orders = fut.result()
            except ZeltyError as e:
                st.warning(f"Restaurant {rid} — {e}")
                continue
            for o in orders:
                price = o.get("price") or {}
                rows.append({
                    "restaurant_id": int(o.get("id_restaurant", rid)),
                    "order_id": o.get("id"),
                    "closed_at": o.get("closed_at"),
                    "mode": o.get("mode"),
                    "source": o.get("source"),
                    "origin": o.get("origin_name"),
                    "ttc": _to_float(price.get("final_amount_inc_tax")) / 100.0,
                    "ht": _to_float(price.get("final_amount_exc_tax")) / 100.0,
                })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def health_check() -> tuple[bool, str]:
    """Test la connexion à l'API."""
    try:
        df = list_restaurants()
        return True, f"OK — {len(df)} restaurant(s)"
    except ZeltyError as e:
        return False, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"Erreur: {e}"


# ---------------------------------------------------------------------------
# CSV fallback (compatibilité avec dashboard Bron original)
# ---------------------------------------------------------------------------
def parse_zelty_csv(text: str) -> pd.DataFrame:
    """Parse un export CSV Zelty 'Les Produits' (format BO)."""
    import csv
    import io

    # Skip "sep=" first line if present
    if text.startswith("sep="):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    reader = csv.reader(io.StringIO(text))
    rows = []
    next(reader, None)  # header
    for r in reader:
        if not r or not r[0].strip():
            continue
        nom = r[0].strip()
        qte = _parse_int(r[1] if len(r) > 1 else "")
        pct_qte = _parse_float((r[2] if len(r) > 2 else "").replace("%", ""))
        pct_ca = _parse_float((r[3] if len(r) > 3 else "").replace("%", ""))
        ht = _parse_float(r[5] if len(r) > 5 else "")
        if nom and (qte > 0 or ht > 0):
            rows.append({
                "nom": nom,
                "qte": qte,
                "ht": ht,
                "pct_ca": pct_ca,
                "pct_qte": pct_qte,
                "prix_moy": ht / qte if qte else 0,
            })
    return pd.DataFrame(rows)


def _parse_int(s: str) -> int:
    try:
        return int(str(s).strip().replace(" ", "").replace(",", "."))
    except (ValueError, TypeError):
        return 0


def _parse_float(s: str) -> float:
    try:
        return float(str(s).strip().replace(" ", "").replace(",", "."))
    except (ValueError, TypeError):
        return 0.0
