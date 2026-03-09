"""
DjodeTube - Interface Web Flask
Application web pour télécharger des vidéos depuis plusieurs plateformes
"""

import os
import sys
import json
import time
import threading
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import re

from flask import Flask, render_template_string, request, jsonify, send_file, Response, stream_with_context
from concurrent.futures import ThreadPoolExecutor, as_completed

# Importations conditionnelles
try:
    import yt_dlp as ytdl
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False

try:
    from colorama import Fore, Style, init
    init(autoreset=True)
except ImportError:
    class Fore:
        GREEN = RED = YELLOW = CYAN = MAGENTA = ''

# Configuration
app = Flask(__name__)
app.secret_key = 'djodetube_secret_key_2024'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

# Répertoire de téléchargement
DOWNLOAD_DIR = os.path.expanduser("~/Downloads")
TEMP_DIR = os.path.join(os.path.dirname(__file__), 'temp')

# Créer les répertoires si nécessaires
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Executor pour les tâches async
executor = ThreadPoolExecutor(max_workers=3)

# Sessions de téléchargement
download_sessions = {}


def detect_platform(url):
    """Détecte la plateforme de la vidéo"""
    url_lower = url.lower()
    
    platforms = {
        'YouTube': ['youtube.com', 'youtu.be', 'yewtu.be'],
        'Vimeo': ['vimeo.com'],
        'Dailymotion': ['dailymotion.com', 'dai.ly'],
        'Twitter/X': ['twitter.com', 'x.com'],
        'Facebook': ['facebook.com', 'fb.watch'],
        'Instagram': ['instagram.com'],
        'TikTok': ['tiktok.com'],
        'Twitch': ['twitch.tv'],
        'Reddit': ['reddit.com'],
    }
    
    for platform, domains in platforms.items():
        for domain in domains:
            if domain in url_lower:
                return platform
    
    return 'unknown'


def get_video_info(url):
    """Récupère les informations de la vidéo"""
    if not YTDLP_AVAILABLE:
        return {'error': 'yt-dlp non installé'}
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': os.path.join(TEMP_DIR, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with ytdl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            video_info = {
                'title': info.get('title', 'Inconnu'),
                'id': info.get('id', ''),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Inconnu'),
                'upload_date': info.get('upload_date', ''),
                'view_count': info.get('view_count', 0),
                'thumbnail': info.get('thumbnail', ''),
                'description': (info.get('description', '')[:300] + '...') if info.get('description') else '',
                'url': url,
                'platform': detect_platform(url),
                'filesize': info.get('filesize') or info.get('filesize_approx', 0),
                'format': info.get('format', 'unknown'),
                'formats': [],
            }
            
            # Formatter la durée
            if video_info['duration']:
                mins, secs = divmod(video_info['duration'], 60)
                hours, mins = divmod(mins, 60)
                video_info['duration_formatted'] = f"{hours}h {mins}m {secs}s" if hours else f"{mins}m {secs}s"
            
            # Formatter la taille
            if video_info['filesize']:
                video_info['filesize_mb'] = video_info['filesize'] / (1024 * 1024)
            
            return video_info
            
    except Exception as e:
        return {'error': str(e)}


def get_formats(url):
    """Récupère les formats disponibles"""
    if not YTDLP_AVAILABLE:
        return []
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with ytdl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            
            formatted_formats = []
            seen = set()
            
            for fmt in formats:
                ext = fmt.get('ext', 'N/A')
                res = fmt.get('resolution', 'N/A')
                filesize = fmt.get('filesize') or fmt.get('filesize_approx', 0)
                fmt_id = fmt.get('format_id', 'N/A')
                
                # Éviter les doublons
                key = (ext, res)
                if key in seen:
                    continue
                seen.add(key)
                
                format_item = {
                    'format_id': fmt_id,
                    'ext': ext,
                    'resolution': res,
                    'filesize': filesize,
                }
                
                if filesize:
                    format_item['filesize_mb'] = filesize / (1024 * 1024)
                
                formatted_formats.append(format_item)
            
            return formatted_formats
            
    except Exception as e:
        return []


def download_video_task(session_id, url, format_spec=None, quality=None):
    """Tâche de téléchargement en arrière-plan"""
    session = download_sessions.get(session_id)
    if not session:
        return
    
    session['status'] = 'downloading'
    session['progress'] = 0
    
    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [lambda d: update_progress(session_id, d)],
    }
    
    # Appliquer les options de format
    if quality == 'audio':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['outtmpl'] = os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s')
    elif quality == 'worst':
        ydl_opts['format'] = 'worstvideo+worstaudio/worst'
    elif format_spec:
        ydl_opts['format'] = format_spec
    else:
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    
    try:
        with ytdl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            session['status'] = 'completed'
            session['progress'] = 100
            session['filename'] = os.path.basename(filename)
            session['filepath'] = filename
            
    except Exception as e:
        session['status'] = 'error'
        session['error'] = str(e)


def update_progress(session_id, d):
    """Met à jour la progression du téléchargement"""
    session = download_sessions.get(session_id)
    if not session:
        return
    
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
        downloaded = d.get('downloaded_bytes', 0)
        
        if total > 0:
            session['progress'] = int((downloaded / total) * 100)
        
        session['speed'] = d.get('speed', 0)
        session['eta'] = d.get('eta', 0)
        session['filename'] = os.path.basename(d.get('filename', 'video'))
        
    elif d['status'] == 'finished':
        session['progress'] = 100


# Template HTML
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DjodeTube - Téléchargeur de Vidéos</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --primary: #ff0000;
            --dark: #212529;
            --light: #f8f9fa;
        }
        
        body {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        .navbar {
            background: rgba(0, 0, 0, 0.3) !important;
            backdrop-filter: blur(10px);
        }
        
        .hero-section {
            padding: 80px 0;
            text-align: center;
        }
        
        .hero-title {
            font-size: 3.5rem;
            font-weight: 800;
            background: linear-gradient(45deg, #ff0000, #ff6b6b);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 20px;
        }
        
        .hero-subtitle {
            color: #adb5bd;
            font-size: 1.2rem;
            margin-bottom: 40px;
        }
        
        .download-card {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            padding: 40px;
            backdrop-filter: blur(10px);
        }
        
        .url-input {
            background: rgba(255, 255, 255, 0.1) !important;
            border: 2px solid rgba(255, 255, 255, 0.2) !important;
            color: white !important;
            border-radius: 50px !important;
            padding: 15px 25px !important;
            font-size: 1.1rem !important;
        }
        
        .url-input::placeholder {
            color: rgba(255, 255, 255, 0.5) !important;
        }
        
        .url-input:focus {
            border-color: var(--primary) !important;
            box-shadow: 0 0 20px rgba(255, 0, 0, 0.3) !important;
        }
        
        .btn-download {
            background: linear-gradient(45deg, #ff0000, #ff4444);
            border: none;
            border-radius: 50px;
            padding: 15px 40px;
            font-size: 1.1rem;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        
        .btn-download:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(255, 0, 0, 0.4);
        }
        
        .video-card {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 15px;
            overflow: hidden;
            margin-top: 30px;
        }
        
        .video-thumbnail {
            width: 100%;
            height: 200px;
            object-fit: cover;
        }
        
        .video-info {
            padding: 20px;
        }
        
        .video-title {
            color: white;
            font-weight: 600;
            margin-bottom: 10px;
        }
        
        .video-meta {
            color: #adb5bd;
            font-size: 0.9rem;
        }
        
        .video-meta i {
            margin-right: 5px;
            color: var(--primary);
        }
        
        .format-select {
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            color: white;
            border-radius: 10px;
            padding: 10px 15px;
        }
        
        .progress-container {
            margin-top: 30px;
            display: none;
        }
        
        .progress-bar-custom {
            background: linear-gradient(45deg, #ff0000, #ff4444);
            height: 30px;
            border-radius: 15px;
        }
        
        .platform-badge {
            position: absolute;
            top: 10px;
            right: 10px;
            background: var(--primary);
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: ;
            font-weight0.8rem: 600;
        }
        
        .features-section {
            padding: 60px 0;
        }
        
        .feature-box {
            text-align: center;
            padding: 30px;
            color: white;
        }
        
        .feature-icon {
            font-size: 3rem;
            color: var(--primary);
            margin-bottom: 20px;
        }
        
        footer {
            background: rgba(0, 0, 0, 0.3);
            padding: 30px 0;
            color: #adb5bd;
        }
        
        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .status-text {
            color: white;
            margin-top: 10px;
        }
        
        .alert-custom {
            background: rgba(255, 0, 0, 0.2);
            border: 1px solid rgba(255, 0, 0, 0.3);
            color: white;
            border-radius: 10px;
        }
    </style>
</head>
<body>
    <!-- Navigation -->
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-play-circle text-danger"></i> DjodeTube
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav ms-auto">
                    <li class="nav-item">
                        <a class="nav-link" href="#features">Fonctionnalités</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="#about">À propos</a>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <!-- Hero Section -->
    <section class="hero-section">
        <div class="container">
            <h1 class="hero-title">
                <i class="fas fa-download"></i> DjodeTube
            </h1>
            <p class="hero-subtitle">Téléchargez vos vidéos préférées depuis n'importe quelle plateforme</p>
            
            <div class="row justify-content-center">
                <div class="col-lg-8">
                    <div class="download-card">
                        <form id="downloadForm">
                            <div class="input-group mb-4">
                                <input type="text" class="form-control url-input" id="videoUrl" 
                                       placeholder="Collez l'URL de la vidéo ici..." required>
                                <button type="submit" class="btn btn-download ms-3" id="getInfoBtn">
                                    <i class="fas fa-search"></i> Analyser
                                </button>
                            </div>
                        </form>
                        
                        <!-- Loading Spinner -->
                        <div id="loading" class="text-center" style="display: none;">
                            <div class="spinner"></div>
                            <p class="status-text">Analyse de la vidéo...</p>
                        </div>
                        
                        <!-- Error Alert -->
                        <div id="errorAlert" class="alert alert-custom alert-dismissible" style="display: none;">
                            <i class="fas fa-exclamation-triangle"></i> <span id="errorText"></span>
                            <button type="button" class="btn-close" onclick="$('#errorAlert').hide()"></button>
                        </div>
                        
                        <!-- Video Info -->
                        <div id="videoInfo" class="video-card" style="display: none;">
                            <div class="position-relative">
                                <img id="videoThumbnail" class="video-thumbnail" src="" alt="Thumbnail">
                                <span class="platform-badge" id="platformBadge"></span>
                            </div>
                            <div class="video-info">
                                <h5 class="video-title" id="videoTitle"></h5>
                                <div class="video-meta mb-3">
                                    <p><i class="fas fa-user"></i> <span id="videoUploader"></span></p>
                                    <p><i class="fas fa-clock"></i> Durée: <span id="videoDuration"></span></p>
                                    <p><i class="fas fa-file-video"></i> Taille: <span id="videoSize"></span></p>
                                    <p><i class="fas fa-eye"></i> Vues: <span id="videoViews"></span></p>
                                </div>
                                
                                <div class="mb-3">
                                    <label class="form-label text-white">Qualité de téléchargement:</label>
                                    <select class="form-select format-select" id="qualitySelect">
                                        <option value="best">Meilleure qualité (Vidéo + Audio)</option>
                                        <option value="1080p">1080p</option>
                                        <option value="720p">720p</option>
                                        <option value="480p">480p</option>
                                        <option value="360p">360p</option>
                                        <option value="audio">Audio uniquement (MP3)</option>
                                        <option value="worst">Qualité la plus basse</option>
                                    </select>
                                </div>
                                
                                <button class="btn btn-download w-100" id="downloadBtn">
                                    <i class="fas fa-download"></i> Télécharger
                                </button>
                            </div>
                        </div>
                        
                        <!-- Progress -->
                        <div class="progress-container" id="progressContainer">
                            <div class="d-flex justify-content-between mb-2">
                                <span class="text-white" id="progressText">Téléchargement...</span>
                                <span class="text-white" id="progressPercent">0%</span>
                            </div>
                            <div class="progress">
                                <div class="progress-bar progress-bar-custom" id="progressBar" role="progressbar" style="width: 0%"></div>
                            </div>
                            <p class="status-text mt-2" id="statusText"></p>
                        </div>
                        
                        <!-- Download Complete -->
                        <div id="downloadComplete" class="text-center" style="display: none;">
                            <i class="fas fa-check-circle text-success" style="font-size: 4rem;"></i>
                            <h4 class="text-white mt-3">Téléchargement terminé!</h4>
                            <p class="text-white" id="downloadedFile"></p>
                            <button class="btn btn-download" onclick="location.reload()">
                                <i class="fas fa-plus"></i> Nouvelle vidéo
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Features<section class="features-section" id="features">
 Section -->
            <div class="container">
            <h2 class="text-center text-white mb-5">Fonctionnalités</h2>
            <div class="row">
                <div class="col-md-4">
                    <div class="feature-box">
                        <i class="fas fa-bolt feature-icon"></i>
                        <h4>Téléchargement Rapide</h4>
                        <p class="text-muted">Téléchargez vos vidéos à haute vitesse avec support multi-connexions</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="feature-box">
                        <i class="fas fa-globe feature-icon"></i>
                        <h4>Multi-Plateformes</h4>
                        <p class="text-muted">YouTube, Vimeo, Dailymotion, Twitter, Facebook et bien plus</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="feature-box">
                        <i class="fas fa-quality-high feature-icon"></i>
                        <h4>Plusieurs Qualités</h4>
                        <p class="text-muted">Choisissez parmi différentes résolutions et formats</p>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Footer -->
    <footer id="about">
        <div class="container text-center">
            <p><i class="fas fa-play-circle text-danger"></i> <strong>DjodeTube</strong> - Téléchargeur de vidéos haute vitesse</p>
            <p class="small">Version 1.0 | Propulsé par yt-dlp</p>
        </div>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script>
        let currentUrl = '';
        let currentSessionId = '';
        
        $('#downloadForm').on('submit', function(e) {
            e.preventDefault();
            getVideoInfo();
        });
        
        function getVideoInfo() {
            const url = $('#videoUrl').val().trim();
            if (!url) return;
            
            currentUrl = url;
            $('#loading').show();
            $('#videoInfo').hide();
            $('#errorAlert').hide();
            $('#progressContainer').hide();
            $('#downloadComplete').hide();
            
            $.get('/api/info', { url: url }, function(response) {
                $('#loading').hide();
                
                if (response.error) {
                    $('#errorText').text(response.error);
                    $('#errorAlert').show();
                    return;
                }
                
                currentSessionId = response.session_id;
                
                // Afficher les infos vidéo
                $('#videoThumbnail').attr('src', response.thumbnail || 'https://via.placeholder.com/400x200');
                $('#platformBadge').text(response.platform);
                $('#videoTitle').text(response.title);
                $('#videoUploader').text(response.uploader);
                $('#videoDuration').text(response.duration_formatted || 'N/A');
                $('#videoSize').text(response.filesize_mb ? response.filesize_mb.toFixed(2) + ' MB' : 'N/A');
                $('#videoViews').text(response.view_count ? response.view_count.toLocaleString() : 'N/A');
                
                $('#videoInfo').show();
            }).fail(function() {
                $('#loading').hide();
                $('#errorText').text('Erreur lors de la récupération des informations');
                $('#errorAlert').show();
            });
        }
        
        $('#downloadBtn').on('click', function() {
            if (!currentUrl || !currentSessionId) return;
            
            const quality = $('#qualitySelect').val();
            
            $('#videoInfo').hide();
            $('#progressContainer').show();
            
            $.post('/api/download', {
                url: currentUrl,
                session_id: currentSessionId,
                quality: quality
            }, function(response) {
                if (response.success) {
                    startProgressCheck();
                } else {
                    $('#errorText').text(response.error || 'Erreur de téléchargement');
                    $('#errorAlert').show();
                }
            });
        });
        
        function startProgressCheck() {
            const checkInterval = setInterval(function() {
                $.get('/api/progress/' + currentSessionId, function(response) {
                    const percent = response.progress || 0;
                    $('#progressBar').css('width', percent + '%');
                    $('#progressPercent').text(percent + '%');
                    
                    if (response.speed) {
                        const speedMbps = (response.speed / 1024 / 1024).toFixed(2);
                        $('#statusText').text('Vitesse: ' + speedMbps + ' MB/s');
                    }
                    
                    if (response.filename) {
                        $('#progressText').text('Téléchargement: ' + response.filename);
                    }
                    
                    if (response.status === 'completed') {
                        clearInterval(checkInterval);
                        $('#progressContainer').hide();
                        $('#downloadComplete').show();
                        $('#downloadedFile').text(response.filename || 'Vidéo téléchargée');
                    }
                    
                    if (response.status === 'error') {
                        clearInterval(checkInterval);
                        $('#errorText').text(response.error || 'Erreur de téléchargement');
                        $('#errorAlert').show();
                    }
                });
            }, 1000);
        }
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    """Page d'accueil"""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/info')
def api_info():
    """API pour récupérer les informations vidéo"""
    url = request.args.get('url')
    
    if not url:
        return jsonify({'error': 'URL requise'}), 400
    
    # Créer une session
    session_id = f"session_{int(time.time())}_{hash(url) % 10000}"
    download_sessions[session_id] = {
        'url': url,
        'status': 'getting_info',
        'progress': 0,
    }
    
    video_info = get_video_info(url)
    video_info['session_id'] = session_id
    
    return jsonify(video_info)


@app.route('/api/download', methods=['POST'])
def api_download():
    """API pour démarrer le téléchargement"""
    url = request.form.get('url')
    session_id = request.form.get('session_id')
    quality = request.form.get('quality', 'best')
    format_spec = request.form.get('format')
    
    if not url or not session_id:
        return jsonify({'error': 'Paramètres manquants'}), 400
    
    if session_id not in download_sessions:
        return jsonify({'error': 'Session invalide'}), 400
    
    # Démarrer le téléchargement en arrière-plan
    executor.submit(download_video_task, session_id, url, format_spec, quality)
    
    return jsonify({'success': True, 'session_id': session_id})


@app.route('/api/progress/<session_id>')
def api_progress(session_id):
    """API pour obtenir la progression"""
    session = download_sessions.get(session_id)
    
    if not session:
        return jsonify({'error': 'Session invalide'}), 404
    
    return jsonify({
        'status': session.get('status', 'unknown'),
        'progress': session.get('progress', 0),
        'speed': session.get('speed', 0),
        'eta': session.get('eta', 0),
        'filename': session.get('filename', ''),
        'error': session.get('error', ''),
    })


@app.route('/api/shutdown')
def shutdown():
    """Arrête le serveur (pour développement)"""
    func = request.environ.get('werkzeug.server.shutdown')
    if func:
        func()
    return jsonify({'success': True})


if __name__ == '__main__':
    # Vérifier yt-dlp
    if not YTDLP_AVAILABLE:
        print("⚠️ ATTENTION: yt-dlp n'est pas installé!")
        print("Installez-le avec: pip install yt-dlp")
    
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   🟥 DjodeTube - Interface Web de téléchargement              ║
║                                                               ║
║   📁 Répertoire de téléchargement: {DOWNLOAD_DIR}   ║
║                                                               ║
║   🌐 Serveur démarré sur: http://localhost:5000               ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host='0.0.0.0', port=5000, debug=True)

