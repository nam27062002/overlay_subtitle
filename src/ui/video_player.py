import os
import json
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QSlider, QComboBox, QListWidget, QListWidgetItem, QMessageBox)
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

class SubtitleItem(QListWidgetItem):
    def __init__(self, text, start_time, duration):
        super().__init__(text)
        self.start_time = start_time
        self.duration = duration
        self.end_time = start_time + duration
        self.setTextAlignment(Qt.AlignmentFlag.AlignLeft)

class VideoPlayerWindow(QMainWindow):
    def __init__(self, video):
        super().__init__()
        
        self.video = video
        self.subtitles = []
        self.current_subtitle_index = -1
        
        # Đảm bảo tất cả các khóa cần thiết đều có trong dictionary
        required_keys = ["thumbnail_path", "title", "download_date", "audio_path", "subtitle_path", "video_id"]
        for key in required_keys:
            if key not in video:
                print(f"Thiếu khóa {key} trong video: {video}")
                if key == "thumbnail_path" or key == "subtitle_path":
                    video[key] = None
                else:
                    video[key] = ""
        
        # Tải phụ đề
        if self.video.get("subtitle_path") and os.path.exists(self.video["subtitle_path"]):
            try:
                with open(self.video["subtitle_path"], 'r', encoding='utf-8') as f:
                    self.subtitles = json.load(f)
            except Exception as e:
                print(f"Lỗi khi đọc file phụ đề: {str(e)}")
                self.subtitles = []
        
        self.setWindowTitle(f"Phát - {self.video.get('title', 'Video không tiêu đề')}")
        self.setGeometry(100, 100, 900, 600)
        
        # Widget chính
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout chính
        main_layout = QVBoxLayout(central_widget)
        
        # Hiển thị thumbnail
        thumbnail_layout = QHBoxLayout()
        thumbnail_label = QLabel()
        
        # Kiểm tra thumbnail_path có tồn tại và không phải None
        if self.video.get("thumbnail_path") and os.path.exists(self.video["thumbnail_path"]):
            pixmap = QPixmap(self.video["thumbnail_path"])
            thumbnail_label.setPixmap(pixmap.scaled(320, 180, Qt.AspectRatioMode.KeepAspectRatio))
        else:
            # Tạo hình ảnh mặc định nếu không có thumbnail
            thumbnail_label.setText("Không có thumbnail")
            thumbnail_label.setStyleSheet("background-color: #eee; color: #666; font-size: 14px;")
            
        thumbnail_label.setFixedSize(320, 180)
        thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Thông tin video
        info_layout = QVBoxLayout()
        title_label = QLabel(self.video.get("title", "Video không tiêu đề"))
        title_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        info_layout.addWidget(title_label)
        info_layout.addStretch()
        
        thumbnail_layout.addWidget(thumbnail_label)
        thumbnail_layout.addLayout(info_layout)
        thumbnail_layout.addStretch()
        
        main_layout.addLayout(thumbnail_layout)
        
        # Trình phát âm thanh
        player_layout = QVBoxLayout()
        
        # Thanh thời gian
        slider_layout = QHBoxLayout()
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 100)
        self.time_slider.sliderMoved.connect(self.set_position)
        
        self.current_time_label = QLabel("00:00")
        self.duration_label = QLabel("00:00")
        
        slider_layout.addWidget(self.current_time_label)
        slider_layout.addWidget(self.time_slider)
        slider_layout.addWidget(self.duration_label)
        
        player_layout.addLayout(slider_layout)
        
        # Nút điều khiển
        controls_layout = QHBoxLayout()
        
        self.play_button = QPushButton()
        self.play_button.setIcon(QIcon.fromTheme("media-playback-start"))
        self.play_button.setText("Phát")
        self.play_button.clicked.connect(self.toggle_play)
        
        self.stop_button = QPushButton()
        self.stop_button.setIcon(QIcon.fromTheme("media-playback-stop"))
        self.stop_button.setText("Dừng")
        self.stop_button.clicked.connect(self.stop_playback)
        
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"])
        self.speed_combo.setCurrentIndex(2)  # 1.0x
        self.speed_combo.currentIndexChanged.connect(self.change_playback_speed)
        
        controls_layout.addWidget(self.play_button)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addStretch()
        controls_layout.addWidget(QLabel("Tốc độ:"))
        controls_layout.addWidget(self.speed_combo)
        
        player_layout.addLayout(controls_layout)
        
        main_layout.addLayout(player_layout)
        
        # Danh sách phụ đề
        subtitle_layout = QVBoxLayout()
        subtitle_label = QLabel("Phụ đề:")
        subtitle_layout.addWidget(subtitle_label)
        
        self.subtitle_list = QListWidget()
        self.subtitle_list.setStyleSheet("""
            QListWidget::item { padding: 5px; }
            QListWidget::item:selected { background-color: #e0f7fa; color: black; }
        """)
        self.subtitle_list.itemClicked.connect(self.on_subtitle_clicked)
        
        # Thêm phụ đề vào danh sách
        if self.subtitles:
            for subtitle in self.subtitles:
                time_text = f"{int(subtitle['start'] // 60):02d}:{int(subtitle['start'] % 60):02d}"
                item = SubtitleItem(f"{time_text} - {subtitle['text']}", subtitle['start'], subtitle['duration'])
                self.subtitle_list.addItem(item)
        else:
            self.subtitle_list.addItem("Không có phụ đề")
        
        subtitle_layout.addWidget(self.subtitle_list)
        main_layout.addLayout(subtitle_layout)
        
        # Thiết lập trình phát media
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        # Kiểm tra đường dẫn audio_path tồn tại trước khi sử dụng
        audio_path = self.video.get("audio_path", "")
        if audio_path:
            # Chuyển đổi đường dẫn tương đối thành đường dẫn tuyệt đối
            # Tìm đường dẫn file âm thanh theo cả đường dẫn tương đối và tuyệt đối
            abs_audio_path = os.path.abspath(audio_path)
            
            # Kiểm tra xem file có tồn tại không
            if os.path.exists(abs_audio_path):
                self.player.setSource(QUrl.fromLocalFile(abs_audio_path))
                print(f"Đã tìm thấy file âm thanh tại: {abs_audio_path}")
            else:
                # Thử với đường dẫn tương đối từ thư mục hiện tại
                current_dir = os.getcwd()
                alternative_path = os.path.join(current_dir, audio_path)
                
                if os.path.exists(alternative_path):
                    self.player.setSource(QUrl.fromLocalFile(alternative_path))
                    print(f"Đã tìm thấy file âm thanh tại: {alternative_path}")
                else:
                    print(f"Không tìm thấy file âm thanh: {audio_path}")
                    print(f"Đã thử tìm tại: {abs_audio_path}")
                    print(f"Đã thử tìm tại: {alternative_path}")
                    
                    # Hiển thị thông báo lỗi
                    QMessageBox.warning(self, "Lỗi", "Không tìm thấy file âm thanh!")
        else:
            print("Không có đường dẫn đến file âm thanh")
            QMessageBox.warning(self, "Lỗi", "Không có đường dẫn đến file âm thanh!")
        
        # Kết nối các signal
        self.player.durationChanged.connect(self.update_duration)
        self.player.positionChanged.connect(self.update_position)
        self.player.mediaStatusChanged.connect(self.handle_status_changed)
        
        # Timer để cập nhật phụ đề
        self.timer = QTimer(self)
        self.timer.setInterval(100)  # 100ms
        self.timer.timeout.connect(self.update_subtitle)
        
    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_button.setText("Phát")
            self.timer.stop()
        else:
            self.player.play()
            self.play_button.setText("Tạm dừng")
            self.timer.start()
    
    def stop_playback(self):
        self.player.stop()
        self.play_button.setText("Phát")
        self.timer.stop()
    
    def set_position(self, position):
        self.player.setPosition(position)
    
    def update_duration(self, duration):
        self.time_slider.setRange(0, duration)
        minutes = duration // 60000
        seconds = (duration % 60000) // 1000
        self.duration_label.setText(f"{minutes:02d}:{seconds:02d}")
    
    def update_position(self, position):
        self.time_slider.setValue(position)
        minutes = position // 60000
        seconds = (position % 60000) // 1000
        self.current_time_label.setText(f"{minutes:02d}:{seconds:02d}")
        
    def handle_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.setPosition(0)
            self.player.stop()
            self.play_button.setText("Phát")
            self.timer.stop()
    
    def change_playback_speed(self, index):
        speeds = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
        self.player.setPlaybackRate(speeds[index])
    
    def update_subtitle(self):
        current_time = self.player.position() / 1000  # Chuyển đổi từ ms sang s
        
        # Tìm phụ đề hiện tại
        if not self.subtitles:
            return
        
        for i, subtitle in enumerate(self.subtitles):
            start_time = subtitle["start"]
            end_time = start_time + subtitle["duration"]
            
            if start_time <= current_time <= end_time:
                if i != self.current_subtitle_index:
                    self.current_subtitle_index = i
                    self.subtitle_list.setCurrentRow(i)
                    # Cuộn đến phụ đề hiện tại
                    self.subtitle_list.scrollToItem(
                        self.subtitle_list.item(i),
                        QListWidget.ScrollHint.PositionAtCenter
                    )
                return
    
    def on_subtitle_clicked(self, item):
        if isinstance(item, SubtitleItem):
            self.player.setPosition(int(item.start_time * 1000))
            if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.toggle_play()
    
    def closeEvent(self, event):
        self.player.stop()
        self.timer.stop()
        super().closeEvent(event) 