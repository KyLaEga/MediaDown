import os
import threading
import time
import subprocess
import json
import re

import yt_dlp

class UniversalMediaDownloader:
    def __init__(self, max_workers=3):
        self.max_workers = max_workers
        self.cancelled = False
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()

    def close(self):
        pass

    def pause(self):
        self.pause_event.clear()

    def resume(self):
        self.pause_event.set()

    def cancel(self):
        self.cancelled = True
        self.cancel_event.set()

    def sanitize_filename(self, filename):
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = re.sub(r'[_\s]+', '_', filename)
        filename = filename.strip('_')
        if len(filename) > 200:
            filename = filename[:200]
        return filename

    def download_media(self, url, output_dir, media_type='auto', format_str='best', progress_callback=None, counter=None):
        self.pause_event.wait()
        if self.cancelled:
            raise Exception("Отменено")

        if progress_callback:
            progress_callback(0, 100, "Анализ ссылки...")

        # If it's explicitly gallery, or auto but we might fallback
        if media_type == 'gallery':
            return self._download_gallery(url, output_dir, progress_callback)
        else:
            try:
                return self._download_ytdlp(url, output_dir, media_type, format_str, progress_callback)
            except Exception as e:
                if media_type == 'auto':
                    # Fallback to gallery-dl
                    return self._download_gallery(url, output_dir, progress_callback)
                else:
                    raise e

    def _download_ytdlp(self, url, output_dir, media_type, format_str, progress_callback):
        ydl_opts = {
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'noplaylist': False,
            'quiet': True,
            'no_warnings': True,
            'color': 'never',
            'no_color': True,
            'writethumbnail': True,
        }

        if media_type == 'audio':
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': format_str if format_str != 'best' else 'mp3',
                    'preferredquality': '192',
                },
                {'key': 'FFmpegMetadata'},
                {'key': 'EmbedThumbnail'},
            ]
        elif media_type == 'video' or media_type == 'auto':
            if format_str == 'best':
                ydl_opts['format'] = 'bestvideo+bestaudio/best'
            else:
                # E.g. 'mp4'
                ydl_opts['format'] = f'bestvideo[ext={format_str}]+bestaudio[ext=m4a]/best[ext={format_str}]/best'
                ydl_opts['merge_output_format'] = format_str
                
            if 'postprocessors' not in ydl_opts:
                ydl_opts['postprocessors'] = []
            ydl_opts['postprocessors'].extend([
                {'key': 'FFmpegMetadata'},
                {'key': 'EmbedThumbnail'},
            ])

        def hook(d):
            self.pause_event.wait()
            if self.cancelled:
                raise Exception("Отменено пользователем")
            
            if d['status'] == 'downloading':
                if progress_callback:
                    total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                    downloaded_bytes = d.get('downloaded_bytes', 0)
                    if total_bytes > 0:
                        percent = (downloaded_bytes / total_bytes) * 100
                        progress_callback(int(percent), 100, f"Загрузка: {d.get('_percent_str', '0%')} - {d.get('_speed_str', '')}")
            elif d['status'] == 'finished':
                if progress_callback:
                    progress_callback(100, 100, "Обработка файла...")

        ydl_opts['progress_hooks'] = [hook]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title', 'Unknown')
                
                # Попытка получить точный путь к файлу
                file_path = None
                requested_downloads = info.get('requested_downloads')
                if requested_downloads and len(requested_downloads) > 0:
                    file_path = requested_downloads[0].get('filepath')
                
                if not file_path:
                    file_path = ydl.prepare_filename(info)
                    # Если было извлечение аудио, расширение может отличаться от изначального
                    if media_type == 'audio':
                        base, _ = os.path.splitext(file_path)
                        ext = format_str if format_str != 'best' else 'mp3'
                        file_path = f"{base}.{ext}"

                return {
                    'title': title,
                    'pages': 1,
                    'size': 0,
                    'file_path': file_path
                }
        except Exception as e:
            if "Отменено" in str(e):
                raise
            raise Exception(f"Ошибка yt-dlp: {e}")

    def _download_gallery(self, url, output_dir, progress_callback):
        if progress_callback:
            progress_callback(0, 100, "Загрузка галереи...")
            
        cmd = [
            'gallery-dl',
            '-d', output_dir,
            url
        ]
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            import queue
            output_queue = queue.Queue()
            
            def read_output(pipe):
                for line in iter(pipe.readline, ''):
                    output_queue.put(line)
                pipe.close()
                
            reader_thread = threading.Thread(target=read_output, args=(process.stdout,), daemon=True)
            reader_thread.start()
            
            downloaded = 0
            while True:
                self.pause_event.wait()
                if self.cancelled:
                    process.terminate()
                    raise Exception("Отменено")
                    
                try:
                    line = output_queue.get(timeout=0.5)
                    if line and line.startswith('#'):
                        downloaded += 1
                        if progress_callback:
                            progress_callback(downloaded, 0, f"Скачано файлов: {downloaded}")
                except queue.Empty:
                    if process.poll() is not None:
                        break
            
            # Дождаться завершения треда
            reader_thread.join(timeout=1.0)
            
            if process.returncode != 0:
                raise Exception(f"gallery-dl завершился с кодом {process.returncode}")
                
            return {
                'title': f"Gallery_{int(time.time())}",
                'pages': downloaded,
                'size': 0,
                'file_path': output_dir
            }
        except Exception as e:
            raise Exception(f"Ошибка gallery-dl: {e}")
