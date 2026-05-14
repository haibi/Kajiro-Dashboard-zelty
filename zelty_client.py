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
from datetime import date, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

import cache

PARIS = ZoneInfo("Europe/Paris")
API_VERSION = "2.10"
PER_PAGE = 200
MAX_DAYS_PER_REQUEST = 31         # /orders refuse les intervalles > 31 j
# Rate-limit Zelty mesuré : ~5 req par burst de 1 sec, recovery ~5 sec.
# Throttle 1 req/sec = aucun 429 en régime stable.
THROTTLE_SECONDS = 1.5  # plus conservateur — le rate-limit Zelty est imprévisible

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


def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    """GET avec throttle proactif + retry court sur 429.

    Pas de retry sur timeout/connectionerror — on laisse remonter pour ne pas
    bloquer 5×30s par appel raté. Le mark_synced est protégé par try/finally.
    """
    url = f"{_base_url()}{path}"
    time.sleep(THROTTLE_SECONDS)
    resp = None
    for attempt in range(3):
        resp = requests.get(url, headers=_headers(), params=params, timeout=15)
        if resp.status_code == 429:
            # On plafonne à 10s même si Zelty demande plus — sinon ça bloque tout
            wait_s = min(int(resp.headers.get("Retry-After", "5")), 10)
            time.sleep(max(wait_s, 3))
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


def _sync_closures_for_resto(rid: int, date_from: date, date_to: date) -> None:
    """Synchronise les closures manquantes pour un resto vers la DB."""
    today = date.today()
    ranges = cache.missing_ranges(rid, "closures", date_from, date_to)
    for cf, ct in ranges:
        for chunk_from, chunk_to in _date_chunks(cf, ct):
            ok = False
            try:
                payload = _get(f"/{API_VERSION}/closures", params={
                    "restaurant_id": rid,
                    "from": _fmt_date(chunk_from),
                    "to": _fmt_date(chunk_to),
                })
                items = payload.get("closures", []) if isinstance(payload, dict) else []
                rows = [{
                    "date": c.get("date"),
                    "restaurant_id": int(c.get("id_restaurant")),
                    "turnover": _to_float(c.get("turnover")) / 100.0,
                    "taxes": _to_float(c.get("taxes")) / 100.0,
                } for c in items if c.get("date")]
                cache.store_closures(rows)
                ok = True
            finally:
                if ok:
                    synced = []
                    d = chunk_from
                    while d <= chunk_to:
                        if d < today:
                            synced.append(d)
                        d += timedelta(days=1)
                    cache.mark_synced("closures", rid, synced)


def fetch_closures(
    restaurant_ids: tuple[int, ...],
    date_from: date,
    date_to: date,
    on_progress: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    """CA et taxes quotidiens — cache-first, serial."""
    if not restaurant_ids:
        return pd.DataFrame(columns=["date", "restaurant_id", "turnover", "taxes"])

    cache.init_db()
    n = len(restaurant_ids)
    for i, rid in enumerate(restaurant_ids, start=1):
        if on_progress:
            on_progress(f"💰 Closures · resto {i}/{n} (id {rid})")
        try:
            _sync_closures_for_resto(rid, date_from, date_to)
        except ZeltyError as e:
            if on_progress:
                on_progress(f"⚠ resto {rid} closures : {e}")

    rows = cache.query_closures(list(restaurant_ids), date_from, date_to)
    if not rows:
        return pd.DataFrame(columns=["date", "restaurant_id", "turnover", "taxes"])
    return pd.DataFrame(rows).sort_values(["restaurant_id", "date"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Orders (résumés uniquement — pas de lignes produits dans v2.10)
# ---------------------------------------------------------------------------


def _sync_orders_for_resto(
    rid: int,
    date_from: date,
    date_to: date,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Sync incrémentale des commandes — marque les jours synchronisés même
    si la pagination échoue partiellement."""
    today = date.today()
    ranges = cache.missing_ranges(rid, "orders", date_from, date_to)
    for cf, ct in ranges:
        if cf == today and ct == today:
            cache.delete_orders_for_day(rid, today)

        for chunk_from, chunk_to in _date_chunks(cf, ct):
            chunk_completed = False
            try:
                offset = 0
                page_num = 1
                while True:
                    if on_progress:
                        on_progress(
                            f"  · {chunk_from:%d/%m}–{chunk_to:%d/%m} page {page_num} (offset {offset})"
                        )
                    payload = _get(f"/{API_VERSION}/orders", params={
                        "restaurant_id": rid,
                        "from": _fmt_date(chunk_from),
                        "to": _fmt_date(chunk_to),
                        "limit": 200,
                        "offset": offset,
                    })
                    orders = payload.get("orders", []) if isinstance(payload, dict) else []
                    if not orders:
                        chunk_completed = True
                        break
                    rows = []
                    for o in orders:
                        closed_at = o.get("closed_at") or ""
                        closed_date = closed_at[:10] if closed_at else _fmt_date(chunk_from)
                        price = o.get("price") or {}
                        rows.append({
                            "order_id": int(o.get("id")),
                            "restaurant_id": int(o.get("id_restaurant", rid)),
                            "closed_at": closed_at,
                            "closed_date": closed_date,
                            "mode": o.get("mode"),
                            "source": o.get("source"),
                            "origin": o.get("origin_name"),
                            "ttc": _to_float(price.get("final_amount_inc_tax")) / 100.0,
                            "ht": _to_float(price.get("final_amount_exc_tax")) / 100.0,
                        })
                    cache.store_orders(rows)
                    if len(orders) < 200:
                        chunk_completed = True
                        break
                    offset += 200
                    page_num += 1
                    if offset > 100000:  # safety — pas plus de 100k orders / chunk
                        break
            finally:
                # Marquer synchronisés les jours < today que le chunk a couverts.
                # Important : on le fait même en cas d'exception/rate-limit pour
                # ne pas re-fetch indéfiniment ce qui est déjà partiellement stocké.
                if chunk_completed:
                    synced = []
                    d = chunk_from
                    while d <= chunk_to:
                        if d < today:
                            synced.append(d)
                        d += timedelta(days=1)
                    cache.mark_synced("orders", rid, synced)


def fetch_orders_summary(
    restaurant_ids: tuple[int, ...],
    date_from: date,
    date_to: date,
    on_progress: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    """Commandes — cache-first, serial."""
    if not restaurant_ids:
        return pd.DataFrame()

    cache.init_db()
    n = len(restaurant_ids)
    for i, rid in enumerate(restaurant_ids, start=1):
        if on_progress:
            on_progress(f"🧾 Commandes · resto {i}/{n} (id {rid})")
        try:
            _sync_orders_for_resto(rid, date_from, date_to, on_progress=on_progress)
        except ZeltyError as e:
            if on_progress:
                on_progress(f"⚠ resto {rid} orders : {e}")

    rows = cache.query_orders(list(restaurant_ids), date_from, date_to)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ---------------------------------------------------------------------------
# Catalog (plats avec photos + descriptions)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_catalog_items() -> pd.DataFrame:
    """Retourne tous les plats (type=dish) de tous les catalogues, dédupliqués.

    Colonnes : id, internal_id, nom, description, img, prix, color
    """
    catalogs_payload = _get(f"/{API_VERSION}/catalogs")
    catalogs = catalogs_payload.get("catalogs", []) if isinstance(catalogs_payload, dict) else []

    seen: dict[str, dict] = {}
    for cat in catalogs:
        cid = cat.get("id")
        if not cid:
            continue
        try:
            detail = _get(f"/{API_VERSION}/catalogs/{cid}")
        except ZeltyError:
            continue
        items = (detail.get("catalog") or {}).get("items", [])
        if isinstance(items, str):  # parfois stringifié
            import ast
            try:
                items = ast.literal_eval(items)
            except Exception:  # noqa: BLE001
                continue
        for it in items:
            if it.get("type") != "dish":
                continue
            iid = it.get("id") or it.get("internal_id")
            if not iid or iid in seen:
                continue
            price_obj = it.get("price") or {}
            price_cents = _to_float(price_obj.get("price") if isinstance(price_obj, dict) else 0)
            seen[iid] = {
                "id": iid,
                "internal_id": it.get("internal_id"),
                "nom": (it.get("name") or "").strip(),
                "description": it.get("description") or "",
                "img": it.get("img") or "",
                "prix": price_cents / 100.0,
                "color": it.get("color") or "",
            }
    return pd.DataFrame(list(seen.values()))


def match_csv_to_catalog(csv_df: pd.DataFrame, catalog_df: pd.DataFrame) -> pd.DataFrame:
    """Enrichit un dataframe CSV produit (col 'nom') avec img + description du catalogue.

    Matching : exact (lowercase strip) puis substring (CSV name appears in catalog name).
    """
    if csv_df.empty:
        return csv_df

    csv = csv_df.copy()
    if catalog_df.empty:
        csv["img"] = ""
        csv["description"] = ""
        return csv

    cat = catalog_df.copy()
    cat["_norm"] = cat["nom"].str.lower().str.strip()
    cat_map_exact = dict(zip(cat["_norm"], cat[["img", "description"]].to_dict("records")))

    def lookup(name: str) -> dict[str, str]:
        n = (name or "").lower().strip()
        if n in cat_map_exact:
            return cat_map_exact[n]
        # Substring match (left = right or right contains left)
        for cat_norm, row in cat_map_exact.items():
            if n and (n in cat_norm or cat_norm in n):
                return row
        return {"img": "", "description": ""}

    enriched = csv["nom"].apply(lookup)
    csv["img"] = enriched.apply(lambda r: r["img"])
    csv["description"] = enriched.apply(lambda r: r["description"])
    return csv


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
