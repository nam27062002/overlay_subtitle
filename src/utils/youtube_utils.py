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

def download_youtube_video(url, download_folder):
    """Tải âm thanh và phụ đề từ video YouTube"""
    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError("URL YouTube không hợp lệ")
    
    print(f"Bắt đầu tải video có ID: {video_id}")
    
    # Biến để lưu thông tin video
    title = None
    abs_audio_path = None
    rel_audio_path = None
    abs_thumbnail_path = None
    rel_thumbnail_path = None
    abs_subtitle_path = None
    rel_subtitle_path = None
    
    # Thử phương pháp 1: Sử dụng pytube
    try:
        # Thử tải thông tin video với số lần thử tối đa
        max_retries = 3
        retry_count = 0
        yt = None
        
        while retry_count < max_retries:
            try:
                print(f"Thử tải thông tin video lần {retry_count + 1}...")
                # Thêm timeout và headers giả lập trình duyệt để tránh bị chặn
                yt = YouTube(url, use_oauth=False, allow_oauth_cache=True)
                print(f"Đã tải thông tin video: {yt.title}")
                title = yt.title
                break
            except Exception as e:
                retry_count += 1
                print(f"Lỗi khi tải thông tin video (lần thử {retry_count}): {str(e)}")
                if retry_count >= max_retries:
                    print(f"Không thể tải thông tin video sau {max_retries} lần thử. Thử phương pháp khác...")
                    raise Exception(f"Không thể tải thông tin video sau {max_retries} lần thử: {str(e)}")
                # Chờ trước khi thử lại
                time.sleep(2)
        
        # Tạo tên file an toàn
        safe_title = re.sub(r'[^\w\s-]', '', yt.title).strip().replace(' ', '_')
        
        # Tải âm thanh bằng pytube
        audio_stream = None
        retry_count = 0
        
        print("Bắt đầu tải âm thanh...")
        while retry_count < max_retries and not abs_audio_path:
            try:
                print(f"Tìm kiếm audio stream (lần thử {retry_count + 1})...")
                # Thử với nhiều cách lọc stream khác nhau
                audio_stream = yt.streams.filter(only_audio=True).first()
                
                if not audio_stream:
                    # Thử lại với cách khác
                    audio_stream = yt.streams.get_audio_only()
                
                if not audio_stream:
                    # Thử lấy bất kỳ stream nào
                    audio_stream = yt.streams.first()
                    
                if audio_stream:
                    print(f"Đã tìm thấy audio stream: {audio_stream}")
                    
                    # Tạo đường dẫn cho file âm thanh
                    audio_file = f"{safe_title}_{video_id}.mp4"
                    abs_audio_path = os.path.join(download_folder, audio_file)
                    rel_audio_path = os.path.join("src", "downloads", audio_file)
                    
                    # Tải xuống âm thanh
                    audio_stream.download(output_path=download_folder, filename=audio_file)
                    print(f"Đã tải xuống âm thanh thành công: {abs_audio_path}")
                    break
                
                retry_count += 1
                time.sleep(1)
            except Exception as e:
                retry_count += 1
                print(f"Lỗi khi tải âm thanh (lần thử {retry_count}): {str(e)}")
                if retry_count >= max_retries:
                    print("Không thể tải âm thanh bằng pytube. Thử phương pháp khác...")
                time.sleep(2)
        
        # Tải ảnh thumbnail
        thumbnail_file = f"{safe_title}_{video_id}.jpg"
        abs_thumbnail_path = os.path.join(download_folder, thumbnail_file)
        rel_thumbnail_path = os.path.join("src", "downloads", thumbnail_file)
        
        # Thử tải thumbnail với nhiều phương pháp khác nhau
        thumbnail_downloaded = False
        
        # Phương pháp 1: Sử dụng URL từ pytube
        try:
            print("Đang tải thumbnail bằng phương pháp 1...")
            # Một số video có thể trả về URL thumbnail dạng string thay vì đối tượng
            if hasattr(yt.thumbnail_url, 'get_data'):
                with open(abs_thumbnail_path, 'wb') as f:
                    f.write(yt.thumbnail_url.get_data())
                thumbnail_downloaded = True
            else:
                urllib.request.urlretrieve(yt.thumbnail_url, abs_thumbnail_path)
                thumbnail_downloaded = True
            print("Đã tải thumbnail bằng phương pháp 1 thành công")
        except (urllib.error.HTTPError, urllib.error.URLError, AttributeError) as e:
            print(f"Không thể tải thumbnail bằng phương pháp 1: {str(e)}")
        
        # Phương pháp 2: Sử dụng URL khác từ YouTube
        if not thumbnail_downloaded:
            try:
                print("Đang tải thumbnail bằng phương pháp 2...")
                # Tạo URL thumbnail thay thế từ video ID
                alternative_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
                response = requests.get(alternative_url)
                if response.status_code == 200:
                    with open(abs_thumbnail_path, 'wb') as f:
                        f.write(response.content)
                    thumbnail_downloaded = True
                    print("Đã tải thumbnail bằng phương pháp 2 (maxresdefault) thành công")
                else:
                    # Thử với độ phân giải thấp hơn
                    alternative_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                    response = requests.get(alternative_url)
                    if response.status_code == 200:
                        with open(abs_thumbnail_path, 'wb') as f:
                            f.write(response.content)
                        thumbnail_downloaded = True
                        print("Đã tải thumbnail bằng phương pháp 2 (hqdefault) thành công")
            except Exception as e:
                print(f"Không thể tải thumbnail bằng phương pháp 2: {str(e)}")
        
        # Nếu không tải được thumbnail
        if not thumbnail_downloaded:
            print("Không thể tải thumbnail, sẽ sử dụng đường dẫn trống")
            abs_thumbnail_path = None
            rel_thumbnail_path = None
    
    except Exception as e:
        print(f"Lỗi khi sử dụng pytube: {str(e)}")
        
        # Nếu pytube thất bại, thử sử dụng yt-dlp
        if not abs_audio_path:
            try:
                print("Đang chuyển sang phương pháp dự phòng: yt-dlp")
                if not title:
                    # Tạo một tiêu đề tạm thời nếu không có
                    title = f"YouTube_Video_{video_id}"
                safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
                abs_audio_path, rel_audio_path, title = download_with_ytdlp(url, video_id, download_folder, safe_title)
                
                # Nếu tải video thành công bằng yt-dlp, thử tải thumbnail
                if not abs_thumbnail_path:
                    try:
                        print("Đang tải thumbnail...")
                        thumbnail_file = f"{safe_title}_{video_id}.jpg"
                        abs_thumbnail_path = os.path.join(download_folder, thumbnail_file)
                        rel_thumbnail_path = os.path.join("src", "downloads", thumbnail_file)
                        
                        alternative_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                        response = requests.get(alternative_url)
                        if response.status_code == 200:
                            with open(abs_thumbnail_path, 'wb') as f:
                                f.write(response.content)
                            print("Đã tải thumbnail thành công")
                        else:
                            abs_thumbnail_path = None
                            rel_thumbnail_path = None
                    except Exception as te:
                        print(f"Không thể tải thumbnail: {str(te)}")
                        abs_thumbnail_path = None
                        rel_thumbnail_path = None
            except Exception as yt_dlp_error:
                print(f"Lỗi khi sử dụng yt-dlp: {str(yt_dlp_error)}")
                raise ValueError(f"Không thể tải video bằng cả hai phương pháp: {str(e)} | {str(yt_dlp_error)}")
    
    # Kiểm tra xem đã tải được audio chưa
    if not abs_audio_path:
        raise ValueError("Không thể tải âm thanh từ video này")
    
    # Tạo tên file an toàn (nếu chưa có)
    if not title:
        title = f"YouTube_Video_{video_id}"
    safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
    
    # Tải phụ đề tiếng Anh
    subtitles = None
    
    try:
        print("Đang tải phụ đề tiếng Anh...")
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = transcript_list.find_transcript(['en'])
        subtitles = transcript.fetch()
        
        # Chuyển đổi đối tượng subtitles thành list dict có thể serialize được
        subtitle_data = []
        for entry in subtitles:
            # Truy cập trực tiếp vào các thuộc tính thay vì sử dụng .get()
            try:
                subtitle_data.append({
                    'text': entry['text'] if 'text' in entry else str(entry),
                    'start': entry['start'] if 'start' in entry else 0,
                    'duration': entry['duration'] if 'duration' in entry else 0
                })
            except (TypeError, KeyError, AttributeError):
                # Nếu không thể truy cập như dictionary, thử truy cập như đối tượng
                try:
                    subtitle_data.append({
                        'text': getattr(entry, 'text', str(entry)),
                        'start': getattr(entry, 'start', 0),
                        'duration': getattr(entry, 'duration', 0)
                    })
                except Exception as attr_error:
                    print(f"Không thể truy cập thuộc tính của phụ đề: {str(attr_error)}")
                    # Thêm một bản ghi trống để tránh bỏ qua phụ đề này hoàn toàn
                    subtitle_data.append({
                        'text': str(entry),
                        'start': 0,
                        'duration': 0
                    })
        
        subtitle_file = f"{safe_title}_{video_id}.json"
        abs_subtitle_path = os.path.join(download_folder, subtitle_file)
        rel_subtitle_path = os.path.join("src", "downloads", subtitle_file)
        
        with open(abs_subtitle_path, 'w', encoding='utf-8') as f:
            json.dump(subtitle_data, f, ensure_ascii=False, indent=4)
        
        print(f"Đã tải phụ đề tiếng Anh thành công: {abs_subtitle_path}")
    except Exception as e:
        print(f"Lỗi khi tải phụ đề: {str(e)}")
        subtitles = None
        abs_subtitle_path = None
        rel_subtitle_path = None
    
    print(f"Đã hoàn thành tải video {title}")
    
    # Đảm bảo tất cả các khóa đều có trong dictionary kết quả
    result = {
        "video_id": video_id,
        "title": title if title else f"YouTube_Video_{video_id}",
        "audio_path": rel_audio_path,
        "subtitle_path": rel_subtitle_path,
        "thumbnail_path": rel_thumbnail_path,
        "download_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Đảm bảo các giá trị không phải None
    for key in result:
        if result[key] is None and key != "subtitle_path" and key != "thumbnail_path":
            result[key] = ""
    
    return result 