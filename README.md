# Kajirō Dashboard

Dashboard analytics pour le réseau Kajirō Sushi (7 restaurants) — connecté à l'API Zelty v2.10. Auth via Google OAuth SSO.

**Prod** : <https://kajiro-dashboard.streamlit.app>
**Repo** : <https://github.com/YOUR_USERNAME/Kajiro-Dashboard-zelty>

## Stack

- **Python ≥ 3.11** · **Streamlit ≥ 1.42** · Pandas · Plotly · Requests · Tenacity · Authlib
- Cache : restaurants 1 h, ventes 15 min
- Auth : Google OAuth via `st.login()` natif, whitelist d'emails
- Déploiement : Streamlit Cloud

## Lancer en local

```powershell
cd "C:\Users\maxim\Desktop\Programme\Kajiro Dashboar"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Configurer secrets (voir section ci-dessous)
cp .streamlit\secrets.example.toml .streamlit\secrets.toml
# puis éditer .streamlit\secrets.toml avec les vraies valeurs

streamlit run app.py
```

Accès sur <http://localhost:8501>. Le login utilise ton compte Google.

## Setup Google OAuth (une seule fois)

1. Aller sur <https://console.cloud.google.com/apis/credentials>
2. Créer ou sélectionner un projet (ex: "Kajiro Dashboard")
3. **APIs & Services → OAuth consent screen**
   - User type : **External** (ou Internal si Workspace Yumea)
   - App name : `Kajirō Dashboard`
   - User support email : `hello@kajirosushi.com`
   - Authorized domains : `streamlit.app`
   - Scopes : `openid`, `email`, `profile`
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**
   - Application type : **Web application**
   - Name : `Kajiro Dashboard`
   - Authorized redirect URIs (les 2 obligatoires) :
     - `http://localhost:8501/oauth2callback`
     - `https://kajiro-dashboard.streamlit.app/oauth2callback`
5. Copier **Client ID** et **Client secret** dans `.streamlit/secrets.toml`

## Setup Streamlit Cloud

1. Pousser ce repo sur GitHub (voir `DEPLOY.md` plus bas)
2. Se connecter à <https://share.streamlit.io>
3. **New app** → choisir le repo `Kajiro-Dashboard-zelty`
4. App URL : `kajiro-dashboard.streamlit.app`
5. Main file : `app.py`
6. Python version : 3.11
7. **Advanced settings → Secrets** : coller le contenu complet de `.streamlit/secrets.toml`
   (modifier `redirect_uri` en `https://kajiro-dashboard.streamlit.app/oauth2callback`)
8. Deploy

## Gérer les accès

Modifier la section `[auth_allowed_users]` dans Streamlit Cloud (Settings → Secrets) :

```toml
[auth_allowed_users]
"hello@kajirosushi.com" = "admin"
"nouveau@kajirosushi.com" = "viewer"
```

Rôles :
- `admin` — accès complet
- `viewer` — lecture seule (UI à venir)

Tout email non listé reçoit un message d'accès refusé. Pas de redéploiement nécessaire — les changements de secrets sont pris en compte immédiatement.

## Architecture

| Fichier | Rôle |
| --- | --- |
| `app.py` | Entrée Streamlit · 2 onglets (Réseau, Produits) · sidebar user |
| `auth.py` | Auth Google OAuth · whitelist · `require_login()` / `current_user()` |
| `zelty_client.py` | Client API Zelty 2.10 · restaurants · closures · orders · CSV fallback |
| `periods.py` | Périodes : mois en cours, mois précédent, année, plage personnalisée |
| `theme.py` | Palette + CSS (Poppins + coral officiel #ED7553) |
| `assets/` | Logos SVG (line, square) + favicon K |
| `.streamlit/config.toml` | Thème Streamlit |
| `.streamlit/secrets.toml` | **NON COMMITÉ** — clés + auth |
| `.streamlit/secrets.example.toml` | Template public |

## Onglet "Réseau"

CA TTC/HT du réseau, classement par restaurant, ticket moyen, évolution quotidienne — depuis `/2.10/closures` + `/2.10/orders`. Live.

## Onglet "Produits"

L'API Zelty v2.10 publique ne semble pas exposer les ventes par produit (l'endpoint `/orders` ne renvoie que des résumés). En attendant identification de l'endpoint :

**Mode CSV** — déposer les exports "Les Produits" du back-office Zelty (un par restaurant). Le nom du resto est matché automatiquement sur le nom du fichier. Agrégation réseau ou par sélection de sites.

## Filtres globaux

- **Période** : Mois en cours · Mois précédent · Année en cours · Plage personnalisée
- **Restaurants** : multi-select (7 sites Kajirō — In Bun exclu)

## Sécurité

- ✅ Pas de mot de passe stocké (Google gère le 2FA)
- ✅ Whitelist d'emails — un compte Google sans droits voit "Accès refusé"
- ✅ Audit trail Google côté admin Workspace
- ✅ Secrets gérés en dehors du code (UI Streamlit Cloud)
- ✅ Pre-commit hook qui bloque tout commit contenant la signature de la clé Zelty
- ✅ Cookie de session signé par Streamlit (cookie_secret aléatoire)

## Tests rapides

```powershell
# Vérifier l'auth Zelty
python -c "import zelty_client; print(zelty_client.health_check())"

# Vérifier que la clé n'est dans aucun fichier tracké
git grep -l "MjE0NDI6" || echo "OK aucune fuite"
```
