# Ứng dụng Phụ đề YouTube

Ứng dụng desktop giúp tải âm thanh và phụ đề từ video YouTube, lưu trữ và phát lại khi cần.

## Tính năng

- Tải âm thanh từ video YouTube
- Tải phụ đề tiếng Anh từ video
- Lưu trữ thông tin vào cơ sở dữ liệu
- Hiển thị danh sách các video đã tải
- Phát âm thanh với phụ đề đồng bộ
- Điều chỉnh tốc độ phát
- Giao diện desktop thân thiện với người dùng

## Yêu cầu hệ thống

- Python 3.6+
- Các thư viện Python: PyQt6, pytube, youtube-transcript-api

## Cài đặt

1. Clone repository này
2. Cài đặt các thư viện cần thiết:
   ```
   pip install PyQt6 pytube youtube-transcript-api
   ```

## Cách sử dụng

1. Chạy ứng dụng:
   ```
   python main.py
   ```
2. Nhập URL video YouTube vào ô nhập liệu và nhấn "Tải xuống"
3. Đợi quá trình tải hoàn tất
4. Xem danh sách video đã tải và nhấp vào nút "Phát" để phát âm thanh với phụ đề

## Cấu trúc thư mục

```
OverlaySubtitles/
├── main.py                 # Mã nguồn chính để chạy ứng dụng
├── src/                    # Thư mục chứa mã nguồn
│   ├── downloads/          # Nơi lưu trữ âm thanh và phụ đề đã tải
│   ├── models/             # Mô hình dữ liệu
│   │   ├── __init__.py
│   │   └── database.py     # Xử lý cơ sở dữ liệu
│   ├── ui/                 # Giao diện người dùng
│   │   ├── __init__.py
│   │   ├── main_window.py  # Cửa sổ chính
│   │   └── video_player.py # Trình phát video với phụ đề
│   └── utils/              # Các tiện ích
│       ├── __init__.py
│       └── youtube_utils.py # Xử lý việc tải từ YouTube
└── youtube_subtitles.db    # Cơ sở dữ liệu SQLite
```

## Giải quyết sự cố

Nếu bạn gặp lỗi "Không tải được phụ đề", có thể do:
- Video không có phụ đề tiếng Anh
- YouTube đã thay đổi cấu trúc API

Nếu gặp vấn đề khi tải âm thanh, hãy kiểm tra:
- Kết nối internet
- URL video có hợp lệ không
- Quyền truy cập vào video (có thể một số video bị giới hạn độ tuổi hoặc quốc gia)

## Giấy phép

Phát triển bởi Trần Trọng Nam. Mã nguồn mở theo giấy phép MIT. 