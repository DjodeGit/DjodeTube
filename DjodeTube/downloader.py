"""
Module de téléchargement de vidéos haute vitesse
Télécharge des vidéos depuis plusieurs plateformes en utilisant
le téléchargement multi-fils et la reprise automatique

Interface CLI complète avec support de téléchargement rapide
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Importations conditionnelles pour la compatibilité
try:
    import yt_dlp as ytdl
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False
    print("⚠️ yt-dlp n'est pas installé")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

try:
    from colorama import Fore, Style, init
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    # Fallback colors
    class Fore:
        GREEN = RED = YELLOW = CYAN = MAGENTA = ''
        RESET = ''
    class Style:
        BRIGHT = DIM = NORMAL = ''


class VideoDownloader:
    """
    Classe principale pour le téléchargement de vidéos
    Supporte le téléchargement multi-fils et la reprise automatique
    """
    
    def __init__(self, output_dir=None, num_connections=8, resume=True):
        """
        Initialise le téléchargeur de vidéos
        
        Args:
            output_dir: Répertoire de sauvegarde des vidéos
            num_connections: Nombre de connexions simultanées
            resume: Activer la reprise automatique
        """
        self.output_dir = output_dir or os.path.expanduser("~/Downloads")
        self.num_connections = max(1, min(num_connections, 16))
        self.resume = resume
        self.active_downloads = {}
        self.download_stats = {}
        self.download_lock = threading.Lock()
        
        # Créer le répertoire de sortie si nécessaire
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        # Configurer yt-dlp
        self.ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(self.output_dir, '%(title)s.%(ext)s'),
            'noplaylist': True,
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'concurrent_fragment_downloads': num_connections,
        }
    
    def detect_platform(self, url):
        """
        Détecte la plateforme de la vidéo
        
        Args:
            url: URL de la vidéo
            
        Returns:
            Nom de la plateforme ou 'unknown'
        """
        url_lower = url.lower()
        
        platforms = {
            'YouTube': ['youtube.com', 'youtu.be', 'yewtu.be', 'invidious.snopyta.org', 'yewtu.be'],
            'Vimeo': ['vimeo.com'],
            'Dailymotion': ['dailymotion.com', 'dai.ly'],
            'Twitter/X': ['twitter.com', 'x.com'],
            'Facebook': ['facebook.com', 'fb.watch'],
            'Instagram': ['instagram.com'],
            'TikTok': ['tiktok.com'],
            'Twitch': ['twitch.tv'],
            'Reddit': ['reddit.com', 'old.reddit.com'],
            'Pornhub': ['pornhub.com'],
            'xvideos': ['xvideos.com'],
            'xhamster': ['xhamster.com'],
        }
        
        for platform, domains in platforms.items():
            for domain in domains:
                if domain in url_lower:
                    return platform
        
        return 'unknown'
    
    def get_video_info(self, url, verbose=True):
        """
        Récupère les informations de la vidéo
        
        Args:
            url: URL de la vidéo
            verbose: Afficher les informations
            
        Returns:
            Dict avec les informations de la vidéo
        """
        if not YTDLP_AVAILABLE:
            print(f"{Fore.RED}❌ ERREUR: yt-dlp n'est pas installé")
            print(f"Installez-le avec: pip install yt-dlp")
            return None
        
        if verbose:
            print(f"\n{Fore.CYAN}🔍 Analyse de: {Fore.WHITE}{url}")
            print(f"{Fore.YELLOW}🌐 Plateforme: {Fore.WHITE}{self.detect_platform(url)}")
        
        ydl_opts = self.ydl_opts.copy()
        ydl_opts['quiet'] = not verbose
        
        try:
            with ytdl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                video_info = {
                    'title': info.get('title', 'Unknown'),
                    'id': info.get('id', ''),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'upload_date': info.get('upload_date', ''),
                    'view_count': info.get('view_count', 0),
                    'like_count': info.get('like_count', 0),
                    'thumbnail': info.get('thumbnail', ''),
                    'description': (info.get('description', '')[:200] + '...') if info.get('description') else '',
                    'url': url,
                    'platform': self.detect_platform(url),
                    'filesize': info.get('filesize') or info.get('filesize_approx', 0),
                    'format': info.get('format', 'unknown'),
                    'formats': info.get('formats', []),
                }
                
                if verbose:
                    self._print_video_info(video_info)
                
                return video_info
                
        except Exception as e:
            print(f"{Fore.RED}❌ Erreur lors de la récupération des infos: {e}")
            return None
    
    def _print_video_info(self, video_info):
        """Affiche les informations de la vidéo de manière stylisée"""
        print(f"\n{Fore.GREEN}📹 Titre: {Fore.WHITE}{video_info['title']}")
        print(f"{Fore.GREEN}👤 Uploader: {Fore.WHITE}{video_info['uploader']}")
        
        if video_info['duration']:
            mins, secs = divmod(video_info['duration'], 60)
            hours, mins = divmod(mins, 60)
            duration_str = f"{hours}h {mins}m {secs}s" if hours else f"{mins}m {secs}s"
            print(f"{Fore.GREEN}⏱️ Durée: {Fore.WHITE}{duration_str}")
        
        if video_info['filesize']:
            size_mb = video_info['filesize'] / (1024 * 1024)
            print(f"{Fore.GREEN}💾 Taille approx: {Fore.WHITE}{size_mb:.2f} MB")
        
        if video_info['view_count']:
            print(f"{Fore.GREEN}👁️ Vues: {Fore.WHITE}{video_info['view_count']:,}")
        
        print(f"{Fore.GREEN}🔗 URL: {Fore.WHITE}{video_info['url']}")
        print()
    
    def download_video(self, url, filename=None, format_spec=None, progress_callback=None, quiet=False):
        """
        Télécharge une vidéo avec support multi-fils
        
        Args:
            url: URL de la vidéo
            filename: Nom de fichier personnalisé (optionnel)
            format_spec: Spécification de format (optionnel)
            progress_callback: Fonction de callback pour la progression
            quiet: Mode silencieux
            
        Returns:
            Chemin du fichier téléchargé ou None en cas d'erreur
        """
        if not YTDLP_AVAILABLE:
            print(f"{Fore.RED}❌ ERREUR: yt-dlp n'est pas installé")
            print(f"Installez-le avec: pip install yt-dlp")
            return None
        
        # Obtenir les informations vidéo
        info = self.get_video_info(url, verbose=not quiet)
        if not info:
            return None
        
        # Préparer les options de téléchargement
        download_opts = self.ydl_opts.copy()
        
        if format_spec:
            download_opts['format'] = format_spec
        
        if filename:
            output_template = os.path.join(self.output_dir, filename)
            if not output_template.endswith('.%(ext)s'):
                output_template += '.%(ext)s'
            download_opts['outtmpl'] = output_template
        
        # Ajouter le hook de progression
        progress_bar = None
        pbar_lock = threading.Lock()
        
        def progress_hook(d):
            nonlocal progress_bar
            
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                speed = d.get('speed', 0)
                eta = d.get('eta', 0)
                
                if progress_callback:
                    progress_callback({
                        'status': 'downloading',
                        'total': total,
                        'downloaded': downloaded,
                        'speed': speed,
                        'eta': eta,
                        'filename': d.get('filename', ''),
                    })
                
                # Afficher la progression avec tqdm
                if total > 0 and TQDM_AVAILABLE:
                    with pbar_lock:
                        if progress_bar is None:
                            filename = d.get('filename', 'video')
                            progress_bar = tqdm(
                                total=total,
                                unit='B',
                                unit_scale=True,
                                unit_divisor=1024,
                                desc=filename[:30],
                                leave=True
                            )
                        progress_bar.update(downloaded - progress_bar.n)
                
                # Afficher la progression textuelle
                if total > 0 and not quiet:
                    percent = (downloaded / total) * 100
                    speed_str = f"{speed/1024/1024:.2f} MB/s" if speed else "N/A"
                    eta_str = f"{eta}s" if eta else "N/A"
                    sys.stdout.write(f"\r{Fore.CYAN}📥 {percent:.1f}% | {speed_str} | ETA: {eta_str}")
                    sys.stdout.flush()
                    
            elif d['status'] == 'finished':
                if progress_bar:
                    progress_bar.close()
                if not quiet:
                    print(f"\n{Fore.GREEN}✅ Téléchargement terminé!")
        
        download_opts['progress_hooks'] = [progress_hook]
        
        try:
            if not quiet:
                print(f"{Fore.YELLOW}⬇️ Début du téléchargement...")
            
            with ytdl.YoutubeDL(download_opts) as ydl:
                result = ydl.download([url])
            
            if result == 0:
                if not quiet:
                    print(f"{Fore.GREEN}✅ Vidéo téléchargée avec succès!")
                return os.path.join(self.output_dir, info['title'] + '.mp4')
            else:
                if not quiet:
                    print(f"{Fore.RED}❌ Erreur lors du téléchargement")
                return None
                
        except Exception as e:
            print(f"{Fore.RED}❌ Erreur: {e}")
            if progress_bar:
                progress_bar.close()
            return None
    
    def download_batch(self, urls, format_spec=None, max_workers=3, quiet=False):
        """
        Télécharge plusieurs vidéos en parallèle
        
        Args:
            urls: Liste d'URLs
            format_spec: Spécification de format
            max_workers: Nombre de téléchargements parallèles
            quiet: Mode silencieux
            
        Returns:
            Liste des chemins de fichiers téléchargés
        """
        results = []
        total = len(urls)
        
        if not quiet:
            print(f"{Fore.CYAN}📥 Démarrage du téléchargement par lot: {total} vidéos")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(self.download_video, url, None, format_spec, None, quiet): url 
                for url in urls
            }
            
            for i, future in enumerate(as_completed(future_to_url), 1):
                url = future_to_url[future]
                try:
                    result = future.result()
                    results.append(result)
                    if not quiet:
                        print(f"{Fore.GREEN}[{i}/{total}] Terminé: {url}")
                except Exception as e:
                    if not quiet:
                        print(f"{Fore.RED}[{i}/{total}] Échec: {url} - {e}")
                    results.append(None)
        
        return results
    
    def list_formats(self, url):
        """
        Liste les formats disponibles pour une vidéo
        
        Args:
            url: URL de la vidéo
            
        Returns:
            Liste des formats disponibles
        """
        info = self.get_video_info(url, verbose=False)
        if not info or not info.get('formats'):
            return None
        
        formats = info['formats']
        print(f"\n{Fore.CYAN}📋 Formats disponibles pour: {Fore.WHITE}{info['title']}")
        print(f"{Fore.YELLOW}{'='*60}")
        
        for fmt in formats:
            ext = fmt.get('ext', 'N/A')
            res = fmt.get('resolution', 'N/A')
            filesize = fmt.get('filesize') or fmt.get('filesize_approx', 0)
            fmt_id = fmt.get('format_id', 'N/A')
            
            if filesize:
                size_mb = filesize / (1024 * 1024)
                size_str = f"{size_mb:.1f} MB"
            else:
                size_str = "N/A"
            
            print(f"  {Fore.GREEN}{fmt_id:8} {Fore.WHITE}{ext:5} | {res:12} | {size_str}")
        
        return formats


def print_banner():
    """Affiche la bannière de l'application"""
    banner = f"""
{Fore.CYAN}╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   {Fore.MAGENTA}██╗   ██╗███████╗ ██████╗ ███╗   ██╗                    {Fore.CYAN}║
║   {Fore.MAGENTA}██║   ██║██╔════╝██╔═══██╗████╗  ██║                    {Fore.CYAN}║
║   {Fore.MAGENTA}██║   ██║█████╗  ██║   ██║██╔██╗ ██║                    {Fore.CYAN}║
║   {Fore.MAGENTA}╚██╗ ██╔╝██╔══╝  ██║   ██║██║╚██╗██║                    {Fore.CYAN}║
║    {Fore.MAGENTA}╚████╔╝ ███████╗╚██████╔╝██║ ╚████║                    {Fore.CYAN}║
║     {Fore.MAGENTA}╚═══╝  ╚══════╝ ╚═════╝ ╚═╝  ╚═══╝                    {Fore.CYAN}║
║                                                               ║
║          {Fore.YELLOW}Téléchargeur de vidéos haute vitesse{Fore.CYAN}              ║
║                    Version 1.0                                ║
╚═══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def interactive_mode():
    """Mode interactif pour téléchargements guidés"""
    print_banner()
    
    downloader = VideoDownloader()
    
    while True:
        print(f"\n{Fore.CYAN}╔══════════════════════════════════════╗")
        print(f"║     {Fore.YELLOW}MENU PRINCIPAL{Fore.CYAN}                 ║")
        print(f"╠══════════════════════════════════════╣")
        print(f"║  {Fore.GREEN}1.{Fore.WHITE} Télécharger une vidéo          ║")
        print(f"║  {Fore.GREEN}2.{Fore.WHITE} Télécharger par lot (fichier)  ║")
        print(f"║  {Fore.GREEN}3.{Fore.WHITE} Lister les formats disponibles  ║")
        print(f"║  {Fore.GREEN}4.{Fore.WHITE} Changer le répertoire de sortie  ║")
        print(f"║  {Fore.GREEN}5.{Fore.WHITE} Afficher les informations vidéo  ║")
        print(f"║  {Fore.GREEN}0.{Fore.WHITE} Quitter                           ║")
        print(f"╚══════════════════════════════════════╝")
        
        try:
            choice = input(f"\n{Fore.YELLOW}👉 Entrez votre choix: {Fore.WHITE}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{Fore.RED}👋 Au revoir!")
            break
        
        if choice == '1':
            url = input(f"{Fore.YELLOW}🔗 Entrez l'URL de la vidéo: {Fore.WHITE}").strip()
            if url:
                downloader.download_video(url)
        
        elif choice == '2':
            filepath = input(f"{Fore.YELLOW}📁 Entrez le chemin du fichier ( URLs ): {Fore.WHITE}").strip()
            if filepath and os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                if urls:
                    max_workers = input(f"{Fore.YELLOW}⚡ Nombre de téléchargements parallèles [3]: {Fore.WHITE}").strip()
                    max_workers = int(max_workers) if max_workers.isdigit() else 3
                    downloader.download_batch(urls, max_workers=max_workers)
                else:
                    print(f"{Fore.RED}❌ Aucune URL trouvée dans le fichier")
            else:
                print(f"{Fore.RED}❌ Fichier non trouvé")
        
        elif choice == '3':
            url = input(f"{Fore.YELLOW}🔗 Entrez l'URL de la vidéo: {Fore.WHITE}").strip()
            if url:
                downloader.list_formats(url)
        
        elif choice == '4':
            new_dir = input(f"{Fore.YELLOW}📁 Entrez le nouveau répertoire: {Fore.WHITE}").strip()
            if new_dir:
                downloader.output_dir = new_dir
                if not os.path.exists(new_dir):
                    os.makedirs(new_dir)
                print(f"{Fore.GREEN}✅ Répertoire changé: {new_dir}")
        
        elif choice == '5':
            url = input(f"{Fore.YELLOW}🔗 Entrez l'URL de la vidéo: {Fore.WHITE}").strip()
            if url:
                downloader.get_video_info(url)
        
        elif choice == '0':
            print(f"{Fore.GREEN}👋 Au revoir!")
            break
        
        else:
            print(f"{Fore.RED}❌ Choix invalide")


def main():
    """Point d'entrée principal avec CLI"""
    parser = argparse.ArgumentParser(
        description='DjodeTube - Téléchargeur de vidéos haute vitesse',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples d'utilisation:
  %(prog)s "https://youtube.com/watch?v=..."
  %(prog)s -i
  %(prog)s -b urls.txt
  %(prog)s "https://youtube.com/watch?v=..." -f best
  %(prog)s "https://youtube.com/watch?v=..." -o ~/Videos
        """
    )
    
    parser.add_argument('url', nargs='?', help='URL de la vidéo à télécharger')
    parser.add_argument('-i', '--interactive', action='store_true', help='Mode interactif')
    parser.add_argument('-b', '--batch', metavar='FILE', help='Télécharger plusieurs vidéos depuis un fichier')
    parser.add_argument('-o', '--output', metavar='DIR', help='Répertoire de sortie')
    parser.add_argument('-f', '--format', metavar='SPEC', help='Spécification de format (ex: best, bestvideo, bestaudio)')
    parser.add_argument('-q', '--quiet', action='store_true', help='Mode silencieux')
    parser.add_argument('-l', '--list-formats', action='store_true', help='Lister les formats disponibles')
    parser.add_argument('-n', '--connections', type=int, default=8, help='Nombre de connexions (défaut: 8)')
    
    args = parser.parse_args()
    
    # Mode interactif
    if args.interactive:
        interactive_mode()
        return
    
    # Mode batch
    if args.batch:
        if not os.path.exists(args.batch):
            print(f"{Fore.RED}❌ Fichier non trouvé: {args.batch}")
            sys.exit(1)
        
        with open(args.batch, 'r') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        if not urls:
            print(f"{Fore.RED}❌ Aucune URL trouvée dans le fichier")
            sys.exit(1)
        
        downloader = VideoDownloader(output_dir=args.output, num_connections=args.connections)
        results = downloader.download_batch(urls, format_spec=args.format, quiet=args.quiet)
        
        success = sum(1 for r in results if r is not None)
        print(f"\n{Fore.GREEN}✅ Terminé: {success}/{len(urls)} téléchargements réussis")
        return
    
    # Mode URL unique
    if args.url:
        downloader = VideoDownloader(output_dir=args.output, num_connections=args.connections)
        
        if args.list_formats:
            downloader.list_formats(args.url)
        else:
            downloader.download_video(args.url, format_spec=args.format, quiet=args.quiet)
    else:
        # Pas d'arguments - afficher l'aide
        print_banner()
        parser.print_help()
        print(f"\n{Fore.YELLOW}💡 Astuce: Utilisez {Fore.WHITE}-i{Fore.YELLOW} pour le mode interactif")


if __name__ == '__main__':
    main()

