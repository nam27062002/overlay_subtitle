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
from youtube_transcript_api import YouTubeTranscriptApi
from datetime import datetime

# Thử import thư viện dịch
try:
    import translators as ts
    TRANSLATORS_AVAILABLE = True
except ImportError:
    TRANSLATORS_AVAILABLE = False
    print("WARNING: Thư viện 'translators' chưa được cài đặt. Phụ đề sẽ không được tự động dịch.")
    print("Chạy 'pip install translators' để cài đặt.")

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
         'progress_hooks': [lambda d: status_callback(f"Đang tải âm thanh: {d['_percent_str']} ({d['_speed_str']})") if status_callback and d['status'] == 'downloading' else None],
         'postprocessor_hooks': [lambda d: status_callback(f"Đang xử lý âm thanh...") if status_callback and d['status'] == 'started' else None],
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
            return final_audio_path
            
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
    if status_callback: status_callback("Đang tải phụ đề...")
    subtitle_path = None
    try:
        # Lấy danh sách transcript có sẵn
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Ưu tiên tiếng Anh gốc, sau đó đến tiếng Anh tự động tạo
        transcript = None
        try:
            transcript = transcript_list.find_generated_transcript(['en'])
            print("Using generated English transcript.")
        except Exception:
             print("Generated English transcript not found.")
             try:
                  # Thử tìm transcript được tạo thủ công
                  transcript = transcript_list.find_manually_created_transcript(['en'])
                  print("Using manual English transcript.")
             except Exception:
                  print("Manual English transcript not found.")
                  # Nếu không có tiếng Anh, thử tìm ngôn ngữ khác và dịch? (Tùy chọn nâng cao)
                  # For now, fail if no English transcript found.
                  raise Exception("Không tìm thấy phụ đề tiếng Anh (gốc hoặc tự động).")

        # Lấy dữ liệu phụ đề (list of dicts)
        subtitles_data = transcript.fetch()

        # === THÊM BƯỚC DỊCH TẠI ĐÂY ===
        if TRANSLATORS_AVAILABLE:
            if status_callback: status_callback("Đang dịch phụ đề (có thể mất vài phút)...")
            print("Bắt đầu dịch phụ đề sang tiếng Việt...")
            translated_count = 0
            errors = []
            # Tạo list mới để tránh vấn đề lặp và sửa đổi cùng lúc
            updated_subtitles_data = [] 

            for i, sub in enumerate(subtitles_data):
                sub_copy = sub.copy() # Làm việc trên bản sao
                en_text = sub_copy.get("text", "")
                # Kiểm tra xem đã có vi_text chưa (có thể API trả về nhiều ngôn ngữ?)
                # Hoặc logic trước đó đã thêm vào (dù không nên)
                if not sub_copy.get("vi_text") and en_text: 
                    try:
                        # Dịch sang tiếng Việt
                        vi_text = ts.translate_text(
                            en_text,
                            translator='google', # hoặc 'bing', ...
                            from_language='en',
                            to_language='vi'
                        )
                        sub_copy["vi_text"] = vi_text
                        translated_count += 1
                        # print(f" Dịch sub {i+1}: OK") # Có thể quá nhiều log
                    except Exception as e:
                        error_msg = f"Lỗi dịch sub {i+1}: {str(e)}"
                        print(error_msg)
                        errors.append(error_msg)
                        # Giữ nguyên sub_copy không có vi_text
                
                updated_subtitles_data.append(sub_copy) # Thêm bản sao (đã dịch hoặc chưa) vào list mới
                # Có thể thêm sleep nhỏ nếu gặp lỗi rate limit
                # time.sleep(0.05) 

            subtitles_data = updated_subtitles_data # Gán lại list đã cập nhật
            print(f"Dịch hoàn tất. {translated_count} câu đã được dịch.")
            if errors:
                print(f"Có {len(errors)} lỗi xảy ra trong quá trình dịch.")
                # Có thể báo lỗi cụ thể hơn nếu muốn
            if status_callback: status_callback("Dịch phụ đề hoàn tất.")
        # ==============================

        # Lưu vào file JSON
        safe_title = sanitize_filename(title)
        subtitle_filename = f"{safe_title}_{video_id}.json"
        subtitle_path = os.path.join(download_folder, subtitle_filename)
        
        with open(subtitle_path, 'w', encoding='utf-8') as f:
            json.dump(subtitles_data, f, ensure_ascii=False, indent=4)
        
        if status_callback: status_callback("Tải phụ đề hoàn tất.")
        print(f"Subtitles saved to: {subtitle_path}")
        return subtitle_path

    except Exception as e:
        print(f"Lỗi khi tải hoặc dịch phụ đề: {e}")
        if status_callback: status_callback(f"Lỗi khi tải/dịch phụ đề: {e}")
        # Không ném lỗi ở đây, trả về None để download chính vẫn tiếp tục (chỉ không có sub)
        return None

def download_thumbnail(url, download_folder, video_id, status_callback=None):
    if status_callback: status_callback("Đang tải ảnh thumbnail...")
    try:
        yt = YouTube(url)
        thumbnail_url = yt.thumbnail_url
        # Lấy thumbnail chất lượng cao nhất (thường là maxresdefault.jpg)
        # Tuy nhiên, maxresdefault không phải lúc nào cũng có, hqdefault thường an toàn hơn
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg" # Thử hqdefault

        # Tạo tên file
        thumbnail_filename = f"YouTube_Thumbnail_{video_id}.jpg"
        thumbnail_path = os.path.join(download_folder, thumbnail_filename)
        
        # Tải ảnh
        response = requests.get(thumbnail_url, stream=True)
        response.raise_for_status() # Kiểm tra lỗi HTTP
        
        with open(thumbnail_path, 'wb') as f:
             for chunk in response.iter_content(chunk_size=8192):
                 f.write(chunk)

        if status_callback: status_callback("Tải thumbnail hoàn tất.")
        print(f"Thumbnail saved to: {thumbnail_path}")
        return thumbnail_path

    except Exception as e:
        print(f"Lỗi khi tải thumbnail: {e}")
        # Thử fallback về thumbnail mặc định nếu lỗi (ít quan trọng hơn)
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/default.jpg"
        try:
            response = requests.get(thumbnail_url, stream=True)
            response.raise_for_status()
            thumbnail_filename = f"YouTube_Thumbnail_{video_id}_default.jpg"
            thumbnail_path = os.path.join(download_folder, thumbnail_filename)
            with open(thumbnail_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            if status_callback: status_callback("Đã tải thumbnail mặc định.")
            print(f"Default thumbnail saved to: {thumbnail_path}")
            return thumbnail_path
        except Exception as e2:
             print(f"Lỗi khi tải thumbnail mặc định: {e2}")
             if status_callback: status_callback(f"Lỗi khi tải thumbnail: {e}")
             return None # Không có thumbnail

def download_youtube_video(url, download_folder, status_callback=None):
    """Tải audio, phụ đề (kèm dịch nếu có thể), thumbnail cho video YouTube."""
    try:
        if status_callback: status_callback("Đang lấy thông tin video...")
        yt = YouTube(url)
        video_id = yt.video_id
        title = yt.title
        
        print(f"Processing video: {title} ({video_id})")

        # 1. Tải Audio
        audio_path = download_audio(url, download_folder, video_id, status_callback)
        if not audio_path:
             raise Exception("Tải audio thất bại.")

        # 2. Tải Phụ đề (và dịch nếu có thể)
        subtitle_path = download_subtitles(video_id, download_folder, title, status_callback)
        # Việc tải phụ đề thất bại không nên làm dừng toàn bộ quá trình

        # 3. Tải Thumbnail
        thumbnail_path = download_thumbnail(url, download_folder, video_id, status_callback)

        download_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        video_info = {
            "video_id": video_id,
            "title": title,
            "audio_path": audio_path,
            "subtitle_path": subtitle_path, # Có thể là None
            "thumbnail_path": thumbnail_path, # Có thể là None
            "download_date": download_date
        }
        
        if status_callback: status_callback("Hoàn tất tải xuống!")
        return video_info

    except Exception as e:
        print(f"Lỗi trong quá trình xử lý video: {e}")
        if status_callback: status_callback(f"Lỗi: {e}")
        # Ném lại lỗi để DownloadThread xử lý và báo cho người dùng
        raise e

def sanitize_filename(filename):
    # ... (giữ nguyên hàm này) ...
    return "".join(c for c in filename if c.isalnum() or c in (' ', '.', '_')).rstrip() 