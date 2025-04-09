import sqlite3
import os

DATABASE_PATH = "youtube_subtitles.db"

def init_db():
    """Khởi tạo cơ sở dữ liệu"""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT UNIQUE,
        title TEXT,
        audio_path TEXT,
        subtitle_path TEXT,
        thumbnail_path TEXT,
        download_date TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()

def get_all_videos():
    """Lấy danh sách tất cả video"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM videos ORDER BY download_date DESC")
    videos = c.fetchall()
    conn.close()
    return videos

def get_video_by_id(video_id):
    """Lấy thông tin video theo ID"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
    video = c.fetchone()
    conn.close()
    return video

def save_video(video_id, title, audio_path, subtitle_path, thumbnail_path, download_date):
    """Lưu thông tin video vào cơ sở dữ liệu"""
    # Đảm bảo không có giá trị None cho các trường không nullable
    video_id = video_id or ""
    title = title or ""
    audio_path = audio_path or ""
    download_date = download_date or ""
    
    # Subtitle và thumbnail có thể là None
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO videos (video_id, title, audio_path, subtitle_path, thumbnail_path, download_date) VALUES (?, ?, ?, ?, ?, ?)",
        (video_id, title, audio_path, subtitle_path, thumbnail_path, download_date)
    )
    conn.commit()
    last_id = c.lastrowid
    conn.close()
    return last_id

def delete_video(video_id):
    """Xóa video theo ID"""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    conn.commit()
    conn.close()

def delete_all_videos():
    """Xóa tất cả video khỏi cơ sở dữ liệu và trả về danh sách đường dẫn file để xóa"""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    
    # Lấy tất cả đường dẫn file trước khi xóa
    c.execute("SELECT audio_path, subtitle_path, thumbnail_path FROM videos")
    file_paths = c.fetchall()
    
    # Xóa tất cả dữ liệu
    c.execute("DELETE FROM videos")
    conn.commit()
    conn.close()
    
    return file_paths 