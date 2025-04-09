import os
import json
import shutil
from datetime import datetime
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
                            QMessageBox, QSplitter, QProgressBar, QDialog, QFileDialog)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QSize
from PyQt6.QtGui import QPixmap, QImage, QIcon
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from src.utils.youtube_utils import download_youtube_video, extract_video_id
from src.models.database import get_all_videos, save_video, get_video_by_id, delete_all_videos
from src.ui.video_player import VideoPlayerWindow
from src.ui.overlay_subtitle import OverlaySubtitle

class DownloadThread(QThread):
    download_progress = pyqtSignal(int)
    download_complete = pyqtSignal(dict)
    download_error = pyqtSignal(str)
    status_update = pyqtSignal(str)
    
    def __init__(self, url, download_folder):
        super().__init__()
        self.url = url
        self.download_folder = download_folder
        
    def run(self):
        try:
            # Tạo stream xử lý để bắt thông báo từ pytube
            import io
            import sys
            from contextlib import redirect_stdout
            
            self.status_update.emit("Đang chuẩn bị tải video...")
            self.download_progress.emit(5)
            
            # Bắt đầu theo dõi output
            output_buffer = io.StringIO()
            with redirect_stdout(output_buffer):
                # Tải video
                video_info = download_youtube_video(self.url, self.download_folder)
            
            # Lấy log từ quá trình tải
            log_output = output_buffer.getvalue()
            print(log_output)  # Ghi log ra console để debug
            
            self.download_progress.emit(100)
            self.status_update.emit("Đã tải hoàn tất!")
            self.download_complete.emit(video_info)
            
        except Exception as e:
            error_message = str(e)
            self.download_error.emit(error_message)
            self.status_update.emit(f"Lỗi: {error_message}")

class VideoItem(QWidget):
    def __init__(self, video, parent=None):
        super().__init__(parent)
        self.video = video
        
        # Đảm bảo tất cả các khóa cần thiết đều có trong dictionary
        required_keys = ["thumbnail_path", "title", "download_date", "audio_path", "subtitle_path", "video_id"]
        for key in required_keys:
            if key not in video:
                print(f"Thiếu khóa {key} trong video: {video}")
                if key == "thumbnail_path" or key == "subtitle_path":
                    video[key] = None
                else:
                    video[key] = ""
        
        layout = QHBoxLayout(self)
        
        # Hình ảnh thumbnail
        thumbnail_label = QLabel()
        thumbnail_path = video.get("thumbnail_path")
        
        if thumbnail_path:
            # Thử tải với đường dẫn tuyệt đối
            abs_thumbnail_path = os.path.abspath(thumbnail_path)
            if os.path.exists(abs_thumbnail_path):
                pixmap = QPixmap(abs_thumbnail_path)
                thumbnail_label.setPixmap(pixmap.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio))
            else:
                # Thử với đường dẫn tương đối từ thư mục hiện tại
                current_dir = os.getcwd()
                alternative_path = os.path.join(current_dir, thumbnail_path)
                
                if os.path.exists(alternative_path):
                    pixmap = QPixmap(alternative_path)
                    thumbnail_label.setPixmap(pixmap.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio))
                else:
                    # Không tìm thấy thumbnail
                    thumbnail_label.setText("Không có\nthumbnail")
                    thumbnail_label.setStyleSheet("background-color: #eee; color: #666; font-size: 10px; text-align: center;")
                    thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            thumbnail_label.setText("Không có\nthumbnail")
            thumbnail_label.setStyleSheet("background-color: #eee; color: #666; font-size: 10px; text-align: center;")
            thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        thumbnail_label.setFixedSize(160, 90)
        layout.addWidget(thumbnail_label)
        
        # Thông tin video
        info_layout = QVBoxLayout()
        title_label = QLabel(video.get("title", "Không có tiêu đề"))
        title_label.setStyleSheet("font-weight: bold;")
        date_label = QLabel(video.get("download_date", ""))
        info_layout.addWidget(title_label)
        info_layout.addWidget(date_label)
        layout.addLayout(info_layout, 1)
        
        # Nút điều khiển
        buttons_layout = QVBoxLayout()
        
        # Nút phát
        play_button = QPushButton("Phát")
        play_button.setFixedWidth(80)
        play_button.clicked.connect(self.play_video)
        buttons_layout.addWidget(play_button)
        
        # Nút overlay phụ đề
        overlay_button = QPushButton("Overlay")
        overlay_button.setFixedWidth(80)
        overlay_button.setStyleSheet("background-color: #4CAF50; color: white;")
        overlay_button.clicked.connect(self.show_overlay_subtitle)
        buttons_layout.addWidget(overlay_button)
        
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
        
    def play_video(self):
        self.player_window = VideoPlayerWindow(self.video)
        self.player_window.show()
    
    def show_overlay_subtitle(self):
        self.overlay_window = OverlaySubtitle(self.video)
        self.overlay_window.show()

class TemplateItem(QWidget):
    def __init__(self, template, parent=None):
        super().__init__(parent)
        self.template = template
        
        layout = QHBoxLayout(self)
        
        # Đảm bảo tất cả khóa cần thiết tồn tại
        required_keys = ["thumbnail_path", "title"]
        for key in required_keys:
            if key not in template:
                if key == "thumbnail_path":
                    template[key] = None
                else:
                    template[key] = ""
        
        # Hình ảnh thumbnail
        thumbnail_label = QLabel()
        thumbnail_path = template.get("thumbnail_path")
        
        if thumbnail_path:
            # Thử tải với đường dẫn tuyệt đối
            abs_thumbnail_path = os.path.abspath(thumbnail_path)
            if os.path.exists(abs_thumbnail_path):
                pixmap = QPixmap(abs_thumbnail_path)
                thumbnail_label.setPixmap(pixmap.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio))
            else:
                # Thử với đường dẫn tương đối từ thư mục hiện tại
                current_dir = os.getcwd()
                alternative_path = os.path.join(current_dir, thumbnail_path)
                
                if os.path.exists(alternative_path):
                    pixmap = QPixmap(alternative_path)
                    thumbnail_label.setPixmap(pixmap.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio))
                else:
                    # Không tìm thấy thumbnail
                    thumbnail_label.setText("Không có\nthumbnail")
                    thumbnail_label.setStyleSheet("background-color: #eee; color: #666; font-size: 10px; text-align: center;")
                    thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            thumbnail_label.setText("Không có\nthumbnail")
            thumbnail_label.setStyleSheet("background-color: #eee; color: #666; font-size: 10px; text-align: center;")
            thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        thumbnail_label.setFixedSize(160, 90)
        layout.addWidget(thumbnail_label)
        
        # Thông tin video
        info_layout = QVBoxLayout()
        title_label = QLabel(template.get("title", "Không có tiêu đề"))
        title_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(title_label)
        layout.addLayout(info_layout, 1)
        
        # Nút điều khiển
        buttons_layout = QVBoxLayout()
        
        # Nút phát
        play_button = QPushButton("Phát")
        play_button.setFixedWidth(80)
        play_button.clicked.connect(self.play_video)
        buttons_layout.addWidget(play_button)
        
        # Nút overlay phụ đề
        overlay_button = QPushButton("Overlay")
        overlay_button.setFixedWidth(80)
        overlay_button.setStyleSheet("background-color: #4CAF50; color: white;")
        overlay_button.clicked.connect(self.show_overlay_subtitle)
        buttons_layout.addWidget(overlay_button)
        
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
        
    def play_video(self):
        self.player_window = VideoPlayerWindow(self.template)
        self.player_window.show()
        
    def show_overlay_subtitle(self):
        self.overlay_window = OverlaySubtitle(self.template)
        self.overlay_window.show()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Ứng dụng Phụ đề YouTube")
        self.setGeometry(100, 100, 800, 600)
        
        # Thư mục lưu video
        self.download_folder = os.path.join("src", "downloads")
        os.makedirs(self.download_folder, exist_ok=True)
        
        # Widget chính
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout chính
        main_layout = QVBoxLayout(central_widget)
        
        # Phần nhập URL
        url_layout = QHBoxLayout()
        url_label = QLabel("URL YouTube:")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Nhập URL video YouTube")
        self.download_button = QPushButton("Tải xuống")
        self.download_button.clicked.connect(self.download_video)
        
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input, 1)
        url_layout.addWidget(self.download_button)
        
        main_layout.addLayout(url_layout)
        
        # Thanh tiến trình và nhãn trạng thái
        progress_layout = QVBoxLayout()
        
        self.status_label = QLabel("Sẵn sàng tải xuống")
        progress_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)
        
        main_layout.addLayout(progress_layout)
        
        # Danh sách video đã tải và button xóa tất cả
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("<h3>Danh sách video đã tải</h3>"))
        
        # Thêm button Xóa tất cả
        self.delete_all_button = QPushButton("Xóa tất cả")
        self.delete_all_button.setStyleSheet("background-color: #f44336; color: white;")
        self.delete_all_button.clicked.connect(self.delete_all_videos)
        header_layout.addWidget(self.delete_all_button, alignment=Qt.AlignmentFlag.AlignRight)
        
        main_layout.addLayout(header_layout)
        
        self.video_list = QListWidget()
        self.video_list.setStyleSheet("QListWidget::item { border-bottom: 1px solid #ddd; }")
        main_layout.addWidget(self.video_list)
        
        # Tải danh sách video
        self.load_videos()
    
    def load_videos(self):
        self.video_list.clear()
        try:
            videos = get_all_videos()
            
            if not videos:
                empty_item = QListWidgetItem("Chưa có video nào được tải")
                empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.video_list.addItem(empty_item)
                return
            
            for video in videos:
                try:
                    # Tạo dictionary với các khóa cố định (thứ tự cột trong database)
                    # video là một tuple với thứ tự (id, video_id, title, audio_path, subtitle_path, thumbnail_path, download_date)
                    video_dict = {
                        "id": video[0],
                        "video_id": video[1],
                        "title": video[2],
                        "audio_path": video[3],
                        "subtitle_path": video[4],
                        "thumbnail_path": video[5],
                        "download_date": video[6]
                    }
                    
                    # Kiểm tra các khóa cần thiết
                    required_keys = ["video_id", "title", "audio_path", "subtitle_path", "thumbnail_path", "download_date"]
                    for key in required_keys:
                        if key not in video_dict or video_dict[key] is None:
                            if key in ["subtitle_path", "thumbnail_path"]:
                                video_dict[key] = None
                            else:
                                video_dict[key] = ""
                    
                    # Tạo ListWidgetItem
                    item = QListWidgetItem()
                    item.setSizeHint(QSize(0, 100))  # Chiều cao cố định cho mỗi item
                    self.video_list.addItem(item)
                    
                    # Tạo và gán video widget
                    video_widget = VideoItem(video_dict)
                    self.video_list.setItemWidget(item, video_widget)
                except Exception as e:
                    print(f"Lỗi khi tải video từ database: {str(e)}")
                    continue  # Bỏ qua video có vấn đề
        except Exception as e:
            print(f"Lỗi khi tải danh sách video: {str(e)}")
            self.video_list.addItem("Lỗi khi tải danh sách video")
    
    def download_video(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Lỗi", "Vui lòng nhập URL YouTube")
            return
        
        video_id = extract_video_id(url)
        if not video_id:
            QMessageBox.warning(self, "Lỗi", "URL YouTube không hợp lệ")
            return
        
        # Vô hiệu hóa nút tải và hiển thị thanh tiến trình
        self.download_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        # Tạo và khởi chạy luồng tải xuống
        self.download_thread = DownloadThread(url, self.download_folder)
        self.download_thread.download_progress.connect(self.update_progress)
        self.download_thread.download_complete.connect(self.on_download_complete)
        self.download_thread.download_error.connect(self.on_download_error)
        self.download_thread.status_update.connect(self.update_status)
        self.download_thread.start()
    
    def update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def update_status(self, status):
        self.status_label.setText(status)
        print(status)  # In trạng thái ra console để debug
    
    def on_download_complete(self, video_info):
        # Lưu thông tin video vào cơ sở dữ liệu
        save_video(
            video_info["video_id"],
            video_info["title"],
            video_info["audio_path"],
            video_info["subtitle_path"],
            video_info["thumbnail_path"],
            video_info["download_date"]
        )
        
        # Tải lại danh sách video
        self.load_videos()
        
        # Đặt lại giao diện
        self.url_input.clear()
        self.download_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Sẵn sàng tải xuống")
        
        # Hiển thị thông báo thành công
        QMessageBox.information(self, "Thành công", "Đã tải video thành công!")
    
    def on_download_error(self, error_message):
        # Đặt lại giao diện
        self.download_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Lỗi khi tải xuống")
        
        # Hiển thị thông báo lỗi chi tiết
        detailed_error = QMessageBox()
        detailed_error.setIcon(QMessageBox.Icon.Critical)
        detailed_error.setWindowTitle("Lỗi")
        detailed_error.setText("Không thể tải video")
        detailed_error.setInformativeText("Vui lòng kiểm tra URL và thử lại.")
        detailed_error.setDetailedText(f"Chi tiết lỗi:\n{error_message}")
        detailed_error.exec()
    
    def delete_all_videos(self):
        """Xóa tất cả video đã tải và dữ liệu trong database"""
        # Hiển thị hộp thoại xác nhận
        confirm = QMessageBox.question(
            self, 
            "Xác nhận xóa",
            "Bạn có chắc chắn muốn xóa tất cả video và dữ liệu đã tải xuống không?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                # Lấy tất cả đường dẫn file từ database và xóa dữ liệu
                file_paths = delete_all_videos()
                deleted_count = 0
                
                # Xóa các file
                for paths in file_paths:
                    audio_path, subtitle_path, thumbnail_path = paths
                    
                    # Xóa file âm thanh
                    if audio_path and os.path.exists(audio_path):
                        try:
                            os.remove(audio_path)
                            deleted_count += 1
                        except Exception as e:
                            print(f"Lỗi khi xóa file âm thanh {audio_path}: {str(e)}")
                    
                    # Xóa file phụ đề
                    if subtitle_path and os.path.exists(subtitle_path):
                        try:
                            os.remove(subtitle_path)
                            deleted_count += 1
                        except Exception as e:
                            print(f"Lỗi khi xóa file phụ đề {subtitle_path}: {str(e)}")
                    
                    # Xóa file thumbnail
                    if thumbnail_path and os.path.exists(thumbnail_path):
                        try:
                            os.remove(thumbnail_path)
                            deleted_count += 1
                        except Exception as e:
                            print(f"Lỗi khi xóa file thumbnail {thumbnail_path}: {str(e)}")
                
                # Tải lại danh sách video (sẽ trống)
                self.load_videos()
                
                # Hiển thị thông báo thành công
                QMessageBox.information(
                    self,
                    "Xóa thành công",
                    f"Đã xóa tất cả dữ liệu và {deleted_count} file."
                )
                
            except Exception as e:
                # Hiển thị thông báo lỗi
                QMessageBox.critical(
                    self,
                    "Lỗi khi xóa",
                    f"Đã xảy ra lỗi khi xóa dữ liệu: {str(e)}"
                ) 