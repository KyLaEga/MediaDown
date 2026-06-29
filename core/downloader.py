import os
import threading
import time
import subprocess
import json
import re
import shutil

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

    def _rewrite_url(self, url):
        """Перезаписываем URL известных зеркал на оригинальные для корректной работы yt-dlp"""
        import re
        if 'exporntoons.net/watch/' in url:
            match = re.search(r'watch/(-?\d+_\d+)', url)
            if match:
                return f"https://vk.com/video{match.group(1)}"
        if 'xv-ru.com' in url:
            return url.replace('xv-ru.com', 'xvideos.com')
        return url

    def download_media(self, url, output_dir, media_type='auto', format_str='best', quality='лучшее', progress_callback=None, counter=None):
        url = self._rewrite_url(url)
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
                return self._download_ytdlp(url, output_dir, media_type, format_str, quality, progress_callback)
            except Exception as e:
                if media_type == 'auto':
                    # Fallback to gallery-dl
                    return self._download_gallery(url, output_dir, progress_callback)
                else:
                    raise e

    def _download_ytdlp(self, url, output_dir, media_type, format_str, quality, progress_callback):
        ydl_opts = {
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'color': 'never',
            'no_color': True,
            'writethumbnail': True,
            'nocheckcertificate': True,
            'concurrent_fragment_downloads': 5,
            'socket_timeout': 10,
        }

        # Parse height limit from quality
        height_limit = ""
        if quality != 'лучшее':
            # Extract digits, e.g. '2160p (4K)' -> '2160'
            match = re.search(r'\d+', quality)
            if match:
                height_limit = f"[height<=?{match.group()}]"

        has_atomic_parsley = shutil.which('AtomicParsley') is not None or shutil.which('atomicparsley') is not None

        if media_type == 'audio':
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': format_str if format_str != 'best' else 'mp3',
                    'preferredquality': '192',
                },
                {'key': 'FFmpegMetadata'},
            ]
            if format_str == 'mp3' or format_str == 'best' or (format_str == 'm4a' and has_atomic_parsley):
                ydl_opts['postprocessors'].append({'key': 'EmbedThumbnail'})
        elif media_type == 'video' or media_type == 'auto':
            if format_str == 'best':
                ydl_opts['format'] = f'bestvideo{height_limit}+bestaudio/best{height_limit}/best'
            else:
                # E.g. 'mp4'
                ydl_opts['format'] = f'bestvideo{height_limit}[ext={format_str}]+bestaudio[ext=m4a]/best{height_limit}[ext={format_str}]/best'
                ydl_opts['merge_output_format'] = format_str
                
            if 'postprocessors' not in ydl_opts:
                ydl_opts['postprocessors'] = []
            ydl_opts['postprocessors'].append({'key': 'FFmpegMetadata'})
            
            # Embed thumbnail only if format is mkv (uses ffmpeg) or if we have AtomicParsley for mp4/best
            if format_str == 'mkv' or ((format_str == 'mp4' or format_str == 'best') and has_atomic_parsley):
                ydl_opts['postprocessors'].append({'key': 'EmbedThumbnail'})

        last_update = [0.0]

        def hook(d):
            self.pause_event.wait()
            if self.cancelled:
                raise Exception("Отменено пользователем")
            
            if d['status'] == 'downloading':
                # Throttle progress callbacks to at most once per 200ms to avoid UI thread lag
                now = time.time()
                if now - last_update[0] >= 0.2:
                    last_update[0] = now
                    if progress_callback:
                        total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                        downloaded_bytes = d.get('downloaded_bytes', 0)
                        speed_bytes = d.get('speed')
                        speed = float(speed_bytes) if speed_bytes is not None else 0.0
                        if total_bytes > 0:
                            percent = (downloaded_bytes / total_bytes) * 100
                            progress_callback(int(percent), 100, f"Загрузка: {d.get('_percent_str', '0%')} - {d.get('_speed_str', '')}", speed)
            elif d['status'] == 'finished':
                if progress_callback:
                    progress_callback(100, 100, "Обработка файла...", 0.0)

        ydl_opts['progress_hooks'] = [hook]

        info = None
        file_path = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # 1. Извлекаем информацию без скачивания, чтобы точно определить путь к файлу
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'Unknown')
                file_path = ydl.prepare_filename(info)
                
                # Дорабатываем путь в зависимости от формата
                if media_type == 'audio':
                    base, _ = os.path.splitext(file_path)
                    ext = format_str if format_str != 'best' else 'mp3'
                    file_path = f"{base}.{ext}"
                elif media_type == 'video' or media_type == 'auto':
                    if format_str != 'best':
                        base, _ = os.path.splitext(file_path)
                        file_path = f"{base}.{format_str}"

                # 2. Запускаем скачивание на основе извлеченной информации
                ydl.process_info(info)

                # Вычисляем итоговое разрешение и формат
                height = info.get('height')
                
                # Переименовываем файл, добавляя разрешение в конец (например, _1080p)
                if height and file_path and os.path.exists(file_path):
                    base, ext_file = os.path.splitext(file_path)
                    new_file_path = f"{base}_{height}p{ext_file}"
                    try:
                        os.rename(file_path, new_file_path)
                        file_path = new_file_path
                        
                        # Также переименуем обложку .jpg, .png, .webp, если она есть рядом
                        for thumb_ext in ['.jpg', '.png', '.webp']:
                            thumb_path = f"{base}{thumb_ext}"
                            if os.path.exists(thumb_path):
                                os.rename(thumb_path, f"{base}_{height}p{thumb_ext}")
                    except Exception as re_err:
                        print(f"Ошибка переименования файла: {re_err}")

                ext = None
                if file_path:
                    _, ext_file = os.path.splitext(file_path)
                    if ext_file:
                        ext = ext_file.lstrip('.').lower()
                if not ext:
                    ext = info.get('ext')
                
                quality_desc = ""
                if height:
                    quality_desc = f"{height}p"
                if ext:
                    quality_desc = f"{quality_desc} ({ext})" if quality_desc else ext

                return {
                    'title': title,
                    'pages': 1,
                    'size': 0,
                    'file_path': file_path,
                    'quality_desc': quality_desc
                }
        except Exception as e:
            if "Отменено" in str(e):
                raise
            
            # Если произошла ошибка (например, сбой вшивания обложки AtomicParsley),
            # но сам медиа-файл скачан и лежит на диске, мы считаем загрузку успешной.
            if file_path and os.path.exists(file_path):
                title = info.get('title', 'Unknown') if info else 'Unknown'
                height = info.get('height') if info else None
                
                # Переименовываем файл на случай падения пост-процессора
                if height:
                    base, ext_file = os.path.splitext(file_path)
                    new_file_path = f"{base}_{height}p{ext_file}"
                    try:
                        os.rename(file_path, new_file_path)
                        file_path = new_file_path
                        
                        for thumb_ext in ['.jpg', '.png', '.webp']:
                            thumb_path = f"{base}{thumb_ext}"
                            if os.path.exists(thumb_path):
                                os.rename(thumb_path, f"{base}_{height}p{thumb_ext}")
                    except Exception as re_err:
                        print(f"Ошибка переименования файла: {re_err}")

                ext = None
                if file_path:
                    _, ext_file = os.path.splitext(file_path)
                    if ext_file:
                        ext = ext_file.lstrip('.').lower()
                quality_desc = ""
                if height:
                    quality_desc = f"{height}p"
                if ext:
                    quality_desc = f"{quality_desc} ({ext})" if quality_desc else ext
                    
                return {
                    'title': title,
                    'pages': 1,
                    'size': 0,
                    'file_path': file_path,
                    'quality_desc': quality_desc
                }
                
            raise Exception(f"Ошибка yt-dlp: {e}")

    def _download_gallery(self, url, output_dir, progress_callback):
        if progress_callback:
            progress_callback(0, 100, "Загрузка галереи...", 0.0)
            
        import sys
        cmd = [
            sys.executable, '-m', 'gallery_dl',
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
                            progress_callback(downloaded, 0, f"Скачано файлов: {downloaded}", 0.0)
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
                'file_path': output_dir,
                'quality_desc': f"{downloaded} фото"
            }
        except Exception as e:
            raise Exception(f"Ошибка gallery-dl: {e}")
