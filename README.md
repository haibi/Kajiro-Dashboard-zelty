# Kajirō Dashboard

Dashboard analytics pour le réseau Kajirō Sushi (7 restaurants) — connecté à l'API Zelty.

## Stack

- **Python 3.11+** · Streamlit · Pandas · Plotly · Requests · Tenacity
- Cache Streamlit (`st.cache_data`) — restaurants 1h, ventes 15 min
- Déploiement : Streamlit Cloud

## Lancer en local

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
streamlit run app.py
```

L'app ouvre <http://localhost:8501>. Mot de passe : voir `.streamlit/secrets.toml`.

## Secrets

Le fichier `.streamlit/secrets.toml` (jamais committé) doit contenir :

```toml
ZELTY_API_KEY = "<clé Basic groupe Zelty>"
ZELTY_AUTH_SCHEME = "Basic"          # ou "Bearer" selon le mode d'auth
ZELTY_BASE_URL = "https://api.zelty.fr"
DASHBOARD_PASSWORD = "<mot de passe d'accès>"
```

Sur Streamlit Cloud, coller le même contenu dans **Settings → Secrets**.

## Architecture

| Fichier | Rôle |
| --- | --- |
| `app.py` | Entrée Streamlit · onglet Produits · filtres · KPIs · table · chart |
| `auth.py` | Gate mot de passe (calque LPMV) |
| `zelty_client.py` | Client API · auth · pagination · agrégation ventes par produit |
| `periods.py` | Périodes : mois en cours, mois précédent, année en cours, personnalisé |
| `theme.py` | Palette + CSS dark coral/red |
| `.streamlit/config.toml` | Thème Streamlit |

## Onglet Produits

- **Filtre période** : mois en cours · mois précédent · année en cours · plage personnalisée
- **Filtre restaurants** : multi-select (7 sites par défaut)
- **Tri** : CA HT / Unités / Prix moy. / % CA (asc/desc)
- **Recherche** : par nom de produit
- **Top N** : 15 / 30 / 50 / 100 / TOUT
- **KPIs** : CA HT · Unités · Réf. actives · Couverture des top N
- **Chart** : top 20 horizontal coral

## Points à valider après le premier run

Le client Zelty est codé sur la base de la doc publique partielle. Si la première
connexion échoue ou renvoie des données vides :

1. **Auth scheme** — la clé Kajirō est au format `chain_id:secret` base64, ce qui colle avec
   `Authorization: Basic <key>`. Si refusée, basculer `ZELTY_AUTH_SCHEME = "Bearer"` dans `secrets.toml`.
2. **Endpoints** — voir `ENDPOINTS` en haut de `zelty_client.py`. Ajuster si l'API publique
   utilise `/api/v2/...` au lieu de `/v2/...`.
3. **Format des lignes** — la fonction `fetch_sales_by_product` tolère plusieurs noms de
   champs (`lines`/`items`, `total_ht`/`ht`, etc.). Si la table reste vide, regarder une
   réponse brute via le log Streamlit pour identifier le schéma réel.

## Déploiement Streamlit Cloud

1. `git init && git add . && git commit -m "init"` (le `.gitignore` exclut déjà `secrets.toml`)
2. Push sur GitHub
3. <https://share.streamlit.io> → New app → pointer sur `app.py`
4. Settings → Secrets → coller le contenu de `secrets.toml`
5. Deploy

## Roadmap

- [ ] Onglet **Restaurants** : CA quotidien, comparaison N vs N-1
- [ ] Onglet **Catégories** : breakdown par famille de produits
- [ ] Comparateur mensuel (≠ même période N-1)
- [ ] Export CSV de la sélection courante
- [ ] Webhook Zelty pour invalider le cache à la fermeture de caisse
