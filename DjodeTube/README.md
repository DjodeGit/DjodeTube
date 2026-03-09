# DjodeTube - Téléchargeur de Vidéos

DjodeTube est une application complète pour télécharger des vidéos depuis plusieurs plateformes. Elle propose deux interfaces : une interface en ligne de commande (CLI) et une interface web.

---

## Fichiers Principaux

### 📥 downloader.py

Module de téléchargement en **ligne de commande (CLI)**.

**Fonctionnalités principales :**

| Fonctionnalité | Description |
|----------------|-------------|
| **Téléchargement simple** | Télécharger une vidéo depuis son URL |
| **Téléchargement par lot** | Télécharger plusieurs vidéos depuis un fichier texte |
| **Multi-threads** | Support de connexions simultanées (jusqu'à 16) |
| **Reprise automatique** | Reprendre les téléchargements interrompus |
| **Détection de plateforme** | Identifie automatiquement YouTube, Vimeo, Dailymotion, Twitter, Facebook, Instagram, TikTok, Twitch, Reddit, etc. |
| **Information vidéo** | Récupère titre, durée, uploader, nombre de vues, taille, miniature |
| **Liste des formats** | Affiche tous les formats disponibles pour une vidéo |
| **Mode interactif** | Interface菜单 pour guidée les téléchargements |

**Utilisation CLI :**

```bash
# Télécharger une vidéo
python downloader.py "https://youtube.com/watch?v=..."

# Mode interactif
python downloader.py -i

# Télécharger depuis un fichier
python downloader.py -b urls.txt

# Spécifier le format
python downloader.py "url" -f best

# Spécifier le répertoire de sortie
python downloader.py "url" -o ~/Videos

# Lister les formats disponibles
python downloader.py "url" -l
```

---

### 🌐 app.py

Application **Flask** avec interface **web**.

**Fonctionnalités principales :**

| Fonctionnalité | Description |
|----------------|-------------|
| **Interface web** | Design moderne avec Bootstrap 5 et Font Awesome |
| **Analyse vidéo** | Affiche miniature, titre, durée, taille, nombre de vues |
| **Choix de qualité** | Meilleure qualité, 1080p, 720p, 480p, 360p, audio-only |
| **Suivi de progression** | Barre de progression en temps réel avec vitesse de téléchargement |
| **API REST** | Endpoints pour info, téléchargement et progression |
| **Téléchargement asynchrone** | Téléchargements en arrière-plan avec ThreadPoolExecutor |

**Lancer le serveur web :**

```bash
python app.py
```

Puis ouvrez : `http://localhost:5000`

**API Endpoints :**

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/info?url=...` | GET | Récupère les informations de la vidéo |
| `/api/download` | POST |Démarre le téléchargement |
| `/api/progress/<session_id>` | GET | Retourne la progression |

---

## Installation

```bash
pip install -r requirements.txt
```

**Dépendances nécessaires :**
- `yt-dlp` - Moteur de téléchargement
- `flask` - Framework web
- `requests` - Requêtes HTTP
- `tqdm` - Barres de progression
- `colorama` - Couleurs dans le terminal

---

## Comparaison des Interfaces

| Critère | downloader.py (CLI) | app.py (Web) |
|---------|---------------------|--------------|
| **Interface** | Terminal | Navigateur web |
| **Facilité d'utilisation** | Pour utilisateurs avancés | Pour tous |
| **Visuel** | Texte avec couleurs | Graphique moderne |
| **Automation** | ✓ Idéale pour scripts | ✓ Via API |

---

## Licence

Version 1.0 - Propulsé par [yt-dlp](https://github.com/yt-dlp/yt-dlp)

