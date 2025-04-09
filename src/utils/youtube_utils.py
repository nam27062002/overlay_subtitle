import os
import re
import json
import urllib.request
import urllib.error
import requests
import time
import tempfile
import shutil
from pytube import YouTube
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from datetime import datetime
import yt_dlp # Đảm bảo import yt_dlp ở đầu file nếu chưa có

# Thử import thư viện dịch
try:
    import translators as ts
    TRANSLATORS_AVAILABLE = True
except ImportError:
    TRANSLATORS_AVAILABLE = False
    print("WARNING: Thư viện 'translators' chưa được cài đặt. Phụ đề sẽ không được tự động dịch.")
    print("Chạy 'pip install translators' để cài đặt.")

# --- Custom Exception --- (Thêm exception riêng)
class NoEnglishTranscriptError(Exception):
    """Lỗi được ném khi không tìm thấy phụ đề tiếng Anh."""
    pass

# Phương pháp tải dự phòng sử dụng yt-dlp
def download_with_ytdlp(url, video_id, download_folder, safe_title):
    """Tải âm thanh từ YouTube sử dụng yt-dlp (phương pháp dự phòng)"""
    print("Đang sử dụng yt-dlp để tải video...")
    
    try:
        import yt_dlp
    except ImportError:
        print("Không tìm thấy thư viện yt-dlp. Vui lòng cài đặt bằng lệnh: pip install yt-dlp")
        raise ValueError("Thư viện yt-dlp không được cài đặt")
    
    # Đường dẫn file tạm thời
    temp_dir = tempfile.mkdtemp()
    
    # Tùy chọn cho yt-dlp
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': False,
        'ffmpeg_location': r'D:\OverlaySubtitles\FFMPEG',
    }
    
    abs_audio_path = None
    rel_audio_path = None
    title = None
    
    try:
        # Tải video bằng yt-dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Unknown Title')
            downloaded_file = ydl.prepare_filename(info)
            
            # Tạo tên file đích
            audio_file = f"{safe_title}_{video_id}.mp4"
            abs_audio_path = os.path.join(download_folder, audio_file)
            rel_audio_path = os.path.join("src", "downloads", audio_file)
            
            # Di chuyển file từ thư mục tạm thời đến thư mục đích
            shutil.move(downloaded_file, abs_audio_path)
            print(f"Đã tải xuống âm thanh thành công bằng yt-dlp: {abs_audio_path}")
    
    except Exception as e:
        print(f"Lỗi khi sử dụng yt-dlp: {str(e)}")
        raise ValueError(f"Không thể tải video bằng yt-dlp: {str(e)}")
    
    finally:
        # Xóa thư mục tạm
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
    
    return abs_audio_path, rel_audio_path, title

def extract_video_id(url):
    """Lấy ID video từ URL YouTube"""
    # Hỗ trợ nhiều định dạng URL YouTube khác nhau
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',  # Dạng chuẩn v=ID hoặc /ID
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',  # Dạng rút gọn youtu.be/ID
        r'(?:embed\/)([0-9A-Za-z_-]{11})',  # Dạng nhúng
        r'(?:shorts\/)([0-9A-Za-z_-]{11})'  # Dạng YouTube Shorts
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def download_audio(url, download_folder, video_id, status_callback=None):
    if status_callback: status_callback("Đang chuẩn bị tải âm thanh...")
    
    # Callback tiến trình để theo dõi chi tiết
    def progress_hook(d):
        if status_callback and d['status'] == 'downloading':
            if '_percent_str' in d and '_speed_str' in d:
                status_callback(f"Đang tải âm thanh: {d['_percent_str']} ({d['_speed_str']})")
        elif status_callback and d['status'] == 'finished':
            status_callback(f"Đã tải xong, đang xử lý âm thanh...")
    
    # Callback xử lý sau để theo dõi quá trình chuyển đổi
    def postprocessor_hook(d):
        if status_callback:
            if d['status'] == 'started':
                status_callback(f"Đang xử lý âm thanh... {d.get('postprocessor', '')}")
            elif d['status'] == 'finished':
                status_callback(f"Xử lý âm thanh hoàn tất")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(download_folder, f'YouTube_Audio_{video_id}.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3', # hoặc 'wav', 'm4a' tùy nhu cầu
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [progress_hook],
        'postprocessor_hooks': [postprocessor_hook],
        'nocheckcertificate': True, # Bỏ qua kiểm tra chứng chỉ SSL nếu cần
        'http_chunk_size': 10485760 # Tăng kích thước chunk tải
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if status_callback: status_callback("Bắt đầu tải âm thanh...")
            info = ydl.extract_info(url, download=True)
            downloaded_path = ydl.prepare_filename(info)
            # yt-dlp tự thêm phần mở rộng codec, ta cần lấy đường dẫn chính xác sau khi xử lý
            base, _ = os.path.splitext(downloaded_path)
            final_audio_path = base + '.mp3' # Phải khớp với preferredcodec
            
            if not os.path.exists(final_audio_path):
                 # Đôi khi tên file thực tế có thể khác một chút, tìm file mp3 khớp video_id
                 found = False
                 for f in os.listdir(download_folder):
                      if f.startswith(f'YouTube_Audio_{video_id}') and f.endswith('.mp3'):
                           final_audio_path = os.path.join(download_folder, f)
                           found = True
                           break
                 if not found:
                    raise FileNotFoundError(f"Không tìm thấy file âm thanh MP3 sau khi tải: {final_audio_path}")

            if status_callback: status_callback("Tải và xử lý âm thanh hoàn tất.")
            print(f"Audio downloaded to: {final_audio_path}")
            return final_audio_path, info.get('title', f'Video_{video_id}') # Trả về cả title
            
    except yt_dlp.utils.DownloadError as e:
        # In lỗi chi tiết hơn
        print(f"yt-dlp download error: {e}")
        if "certificate verify failed" in str(e):
             if status_callback: status_callback("Lỗi SSL khi tải âm thanh. Thử lại hoặc kiểm tra cài đặt mạng/Python.")
        elif "HTTP Error 403" in str(e):
             if status_callback: status_callback("Lỗi HTTP 403 (Forbidden). Có thể video bị giới hạn.")
        else:
             if status_callback: status_callback(f"Lỗi không xác định khi tải âm thanh: {e}")
        raise # Ném lại lỗi để luồng chính xử lý
    except Exception as e:
        print(f"Unexpected error during audio download: {e}")
        if status_callback: status_callback(f"Lỗi không mong muốn khi tải âm thanh: {e}")
        raise

def download_subtitles(video_id, download_folder, title, status_callback=None):
    if status_callback: status_callback("Đang tìm phụ đề tiếng Anh tự động...")
    subtitles_data_fetched = None
    transcript = None
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        try:
            transcript = transcript_list.find_generated_transcript(['en'])
            print("Tìm thấy phụ đề tiếng Anh tự động.")
            if status_callback: status_callback("Đã tìm thấy phụ đề tiếng Anh tự động.")
        except NoTranscriptFound:
            print("Không tìm thấy phụ đề tiếng Anh TỰ ĐỘNG. Video này sẽ bị bỏ qua.")
            if status_callback: status_callback("Không tìm thấy phụ đề tiếng Anh tự động.")
            raise NoEnglishTranscriptError(f"Video {video_id} không có phụ đề tiếng Anh tự động.")
        
        subtitles_data_fetched = transcript.fetch()
        if status_callback: status_callback("Đã tải thành công dữ liệu phụ đề.")

    except TranscriptsDisabled:
         print(f"Phụ đề đã bị tắt cho video {video_id}.")
         raise NoEnglishTranscriptError(f"Phụ đề đã bị tắt cho video {video_id}.")
    except NoEnglishTranscriptError:
         raise
    except Exception as e:
         print(f"Lỗi API khi lấy phụ đề cho {video_id}: {e}")
         raise NoEnglishTranscriptError(f"Lỗi khi lấy phụ đề cho video {video_id}: {e}")

    if subtitles_data_fetched:
        subtitles_data_processed = []

        if TRANSLATORS_AVAILABLE:
            if status_callback: status_callback("Đang dịch phụ đề (có thể mất vài phút)...")
            print("Bắt đầu dịch phụ đề sang tiếng Việt...")
            translated_count = 0
            errors = []
            total_subs = len(subtitles_data_fetched)
            
            for i, sub_obj in enumerate(subtitles_data_fetched):
                # Cập nhật tiến trình dịch theo số lượng
                if status_callback and i % 10 == 0:  # Cập nhật mỗi 10 câu để tránh quá nhiều cập nhật
                    percent_done = min(100, int((i / total_subs) * 100))
                    status_callback(f"Đang dịch phụ đề: {percent_done}% ({i}/{total_subs})")
                
                # Tạo dictionary từ các thuộc tính trực tiếp của đối tượng
                sub_dict = {
                    'text': sub_obj.text,
                    'start': sub_obj.start,
                    'duration': sub_obj.duration
                }
                
                en_text = sub_dict['text']
                if en_text: 
                    try:
                        vi_text = ts.translate_text(en_text, translator='google', from_language='en', to_language='vi')
                        sub_dict["vi_text"] = vi_text
                        translated_count += 1
                    except Exception as e:
                        error_msg = f"Lỗi dịch sub {i+1}: {str(e)}"
                        print(error_msg)
                        errors.append(error_msg)
                        sub_dict["vi_text"] = ""
                else:
                     sub_dict["vi_text"] = ""
                     
                subtitles_data_processed.append(sub_dict)
            
            print(f"Dịch hoàn tất. {translated_count} câu đã được dịch.")
            if errors: print(f"Có {len(errors)} lỗi xảy ra trong quá trình dịch.")
            if status_callback: status_callback(f"Dịch phụ đề hoàn tất. Đã dịch {translated_count}/{total_subs} câu.")
        else:
            if status_callback: status_callback("Bỏ qua dịch do thư viện chưa cài đặt.")
            for sub_obj in subtitles_data_fetched:
                 sub_dict = {
                    'text': sub_obj.text,
                    'start': sub_obj.start,
                    'duration': sub_obj.duration,
                    'vi_text': ''
                 }
                 subtitles_data_processed.append(sub_dict)

        safe_title = sanitize_filename(title)
        subtitle_filename = f"{safe_title}_{video_id}.json"
        subtitle_path = os.path.join(download_folder, subtitle_filename)
        try:
            with open(subtitle_path, 'w', encoding='utf-8') as f:
                json.dump(subtitles_data_processed, f, ensure_ascii=False, indent=4)
            if status_callback: status_callback("Lưu phụ đề hoàn tất.")
            print(f"Subtitles saved to: {subtitle_path}")
            return subtitle_path
        except Exception as e:
            print(f"Lỗi khi lưu file phụ đề JSON: {e}")
            if status_callback: status_callback(f"Lỗi lưu file phụ đề: {e}")
            raise IOError(f"Lỗi khi lưu file phụ đề: {e}")
    else:
        print(f"Không có dữ liệu phụ đề để xử lý cho {video_id} dù không có lỗi trước đó.")
        raise NoEnglishTranscriptError(f"Lỗi logic: không có dữ liệu phụ đề cho {video_id}.")

def download_thumbnail(video_id, download_folder, status_callback=None): # Sửa tham số, không cần url
    if status_callback: status_callback("Đang tải ảnh thumbnail...")
    thumbnail_path = None
    try:
        # Lấy thumbnail chất lượng cao nhất
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

        # Tạo tên file
        thumbnail_filename = f"YouTube_Thumbnail_{video_id}.jpg"
        thumbnail_path = os.path.join(download_folder, thumbnail_filename)
        
        # Tải ảnh với tiến trình
        response = requests.get(thumbnail_url, stream=True, timeout=10)
        response.raise_for_status()
        
        # Lấy kích thước file nếu có
        content_length = response.headers.get('content-length')
        if content_length:
            content_length = int(content_length)
            downloaded = 0
            
            with open(thumbnail_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if status_callback and content_length > 0:
                        percent = int((downloaded / content_length) * 100)
                        if percent % 20 == 0:  # Cập nhật mỗi 20%
                            status_callback(f"Tải thumbnail: {percent}%")
        else:
            # Nếu không có content-length
            with open(thumbnail_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

        if status_callback: status_callback("Tải thumbnail hoàn tất.")
        print(f"Thumbnail saved to: {thumbnail_path}")
        return thumbnail_path

    except requests.exceptions.RequestException as e:
        print(f"Lỗi mạng khi tải thumbnail: {e}")
        # Thử fallback về thumbnail mặc định nếu lỗi
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/default.jpg"
        try:
            response = requests.get(thumbnail_url, stream=True, timeout=5)
            response.raise_for_status()
            thumbnail_filename = f"YouTube_Thumbnail_{video_id}_default.jpg"
            thumbnail_path = os.path.join(download_folder, thumbnail_filename)
            with open(thumbnail_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            if status_callback: status_callback("Đã tải thumbnail mặc định.")
            print(f"Default thumbnail saved to: {thumbnail_path}")
            return thumbnail_path
        except requests.exceptions.RequestException as e2:
             print(f"Lỗi mạng khi tải thumbnail mặc định: {e2}")
             if status_callback: status_callback(f"Lỗi khi tải thumbnail: {e}")
             return None
    except Exception as e:
        print(f"Lỗi không xác định khi tải thumbnail: {e}")
        if status_callback: status_callback(f"Lỗi khi tải thumbnail: {e}")
        return None

def download_youtube_video(url, download_folder, status_callback=None):
    """Tải audio, phụ đề (kèm dịch nếu có thể), thumbnail cho video YouTube."""
    video_id = extract_video_id(url) # Vẫn lấy video_id trước để dùng cho tên file
    if not video_id:
        raise ValueError("Không thể trích xuất Video ID từ URL.")
        
    print(f"Processing video ID: {video_id}")

    title = None # Sẽ lấy title từ yt-dlp sau
    audio_path = None
    subtitle_path = None
    thumbnail_path = None

    try:
        # 1. Tải Audio và lấy Title từ yt-dlp
        if status_callback: status_callback("Đang chuẩn bị tải âm thanh và lấy thông tin...")
        
        # Tùy chọn để lấy info mà không cần tải lại nếu file đã có? (Khó với yt-dlp)
        # Tạm thời cứ tải lại audio
        
        audio_path, title = download_audio(url, download_folder, video_id, status_callback)
        
        if not audio_path or not title:
             raise Exception("Tải audio hoặc lấy title thất bại.")

        # 2. Tải Phụ đề (và dịch nếu có thể) - Dùng video_id và title đã lấy
        subtitle_path = download_subtitles(video_id, download_folder, title, status_callback)
        
        # 3. Tải Thumbnail - Dùng video_id
        thumbnail_path = download_thumbnail(video_id, download_folder, status_callback) # Sửa lại chỉ cần video_id

        download_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        video_info = {
            "video_id": video_id,
            "title": title,
            "audio_path": audio_path,
            "subtitle_path": subtitle_path, 
            "thumbnail_path": thumbnail_path,
            "download_date": download_date
        }
        
        if status_callback: status_callback("Hoàn tất tải xuống!")
        return video_info

    except NoEnglishTranscriptError as e:
        print(f"Hủy tải video {video_id}: {e}")
        # Xóa file audio đã tải (nếu có)
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                print(f"Đã xóa file audio tạm: {audio_path}")
            except OSError as rm_err:
                print(f"Lỗi khi xóa file audio tạm {audio_path}: {rm_err}")
        # Ném lại lỗi với thông điệp cho người dùng
        raise Exception(f"Video không có phụ đề tiếng Anh nên đã bị bỏ qua.") from e

    except Exception as e:
        print(f"Lỗi không mong muốn trong quá trình xử lý video ({video_id}): {e}")
        # Cố gắng xóa audio nếu có lỗi khác xảy ra sau khi tải audio thành công
        if audio_path and os.path.exists(audio_path):
             try:
                  os.remove(audio_path)
                  print(f"Đã xóa file audio tạm do lỗi khác: {audio_path}")
             except OSError as rm_err:
                  print(f"Lỗi khi xóa file audio tạm {audio_path}: {rm_err}")
        if status_callback: status_callback(f"Lỗi: {e}")
        # Ném lại lỗi gốc để DownloadThread hiển thị chi tiết
        raise e

def sanitize_filename(filename):
    # ... (giữ nguyên hàm này) ...
    return "".join(c for c in filename if c.isalnum() or c in (' ', '.', '_')).rstrip() 