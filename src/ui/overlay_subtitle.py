import os
import json
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout, QSlider
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtGui import QFont, QFontMetrics

class OverlaySubtitle(QWidget):
    def __init__(self, video):
        super().__init__()
        
        self.video = video
        self.subtitles = []
        self.current_subtitle_index = -1
        self.background_alpha = 70 # Giá trị alpha ban đầu (0-100)
        self.drag_position = None # Khởi tạo drag_position
        
        # Load subtitles
        if self.video.get("subtitle_path") and os.path.exists(self.video["subtitle_path"]):
            try:
                with open(self.video["subtitle_path"], 'r', encoding='utf-8') as f:
                    self.subtitles = json.load(f)
            except Exception as e:
                print(f"Lỗi khi đọc file phụ đề: {str(e)}")
                self.subtitles = []
        
        # Setup overlay window
        self.setWindowTitle("Phụ đề overlay")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Subtitle display
        self.subtitle_label = QLabel("...")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self.subtitle_label.setWordWrap(True)
        main_layout.addWidget(self.subtitle_label)
        
        # Control layout
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(5, 5, 5, 5) # Giảm margins để vừa slider
        
        # Play button
        self.play_button = QPushButton("⏵")
        self.play_button.setFixedSize(40, 30)
        self.play_button.clicked.connect(self.toggle_play)
        control_layout.addWidget(self.play_button)
        
        # Time slider
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 100)
        self.time_slider.sliderMoved.connect(self.set_position)
        control_layout.addWidget(self.time_slider)
        
        # Time display
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setFixedWidth(100)
        control_layout.addWidget(self.time_label)

        # Transparency slider
        self.transparency_slider = QSlider(Qt.Orientation.Horizontal)
        self.transparency_slider.setRange(0, 100) # 0% to 100% alpha
        self.transparency_slider.setValue(self.background_alpha)
        self.transparency_slider.setFixedWidth(80)
        self.transparency_slider.valueChanged.connect(self.update_background_transparency)
        control_layout.addWidget(QLabel("Trong suốt:")) # Nhãn cho slider
        control_layout.addWidget(self.transparency_slider)
        
        # Close button
        self.close_button = QPushButton("✕")
        self.close_button.setFixedSize(30, 30)
        self.close_button.clicked.connect(self.close)
        control_layout.addWidget(self.close_button)
        
        controls_widget = QWidget()
        controls_widget.setLayout(control_layout)
        controls_widget.setVisible(False)  # Initially hidden
        
        main_layout.addWidget(controls_widget)
        self.controls_widget = controls_widget
        
        # Initial style update
        self.update_background_transparency(self.background_alpha)

        # Media player
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        # Load audio
        audio_path = self.video.get("audio_path", "")
        if audio_path:
            abs_audio_path = os.path.abspath(audio_path)
            
            if os.path.exists(abs_audio_path):
                self.player.setSource(QUrl.fromLocalFile(abs_audio_path))
                print(f"Đã tìm thấy file âm thanh tại: {abs_audio_path}")
            else:
                current_dir = os.getcwd()
                alternative_path = os.path.join(current_dir, audio_path)
                
                if os.path.exists(alternative_path):
                    self.player.setSource(QUrl.fromLocalFile(alternative_path))
                    print(f"Đã tìm thấy file âm thanh tại: {alternative_path}")
                else:
                    print(f"Không tìm thấy file âm thanh: {audio_path}")
        
        # Connect signals
        self.player.durationChanged.connect(self.update_duration)
        self.player.positionChanged.connect(self.update_position)
        
        # Timer for subtitle update
        self.timer = QTimer(self)
        self.timer.setInterval(100)  # 100ms
        self.timer.timeout.connect(self.update_subtitle)
        
        # Calculate initial size based on screen width
        screen_width = self.screen().geometry().width()
        self.setMinimumWidth(int(screen_width * 0.5))  # 50% of screen width
        self.resize(int(screen_width * 0.5), 120)
        
        # Position at the bottom of the screen
        self.move_to_bottom()
        
        # Start playing
        self.player.play()
        self.play_button.setText("⏸")
        self.timer.start()
    
    def move_to_bottom(self):
        """Di chuyển overlay đến vị trí phía dưới màn hình"""
        screen_geometry = self.screen().geometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = screen_geometry.height() - self.height() - 100  # 100 pixels from bottom
        self.move(x, y)
    
    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_button.setText("⏵")
            self.timer.stop()
        else:
            self.player.play()
            self.play_button.setText("⏸")
            self.timer.start()
    
    def set_position(self, position):
        self.player.setPosition(position)
    
    def update_duration(self, duration):
        self.time_slider.setRange(0, duration)
        self.update_time_label()
    
    def update_position(self, position):
        self.time_slider.setValue(position)
        self.update_time_label()
    
    def update_time_label(self):
        position = self.player.position()
        duration = self.player.duration()
        
        position_minutes = position // 60000
        position_seconds = (position % 60000) // 1000
        
        duration_minutes = duration // 60000
        duration_seconds = (duration % 60000) // 1000
        
        self.time_label.setText(f"{position_minutes:02d}:{position_seconds:02d} / {duration_minutes:02d}:{duration_seconds:02d}")
    
    def update_subtitle(self):
        current_time = self.player.position() / 1000  # Chuyển đổi từ ms sang s
        
        # Tìm phụ đề hiện tại
        if not self.subtitles:
            self.subtitle_label.setText("Không có phụ đề")
            return
        
        found_subtitle = False
        for i, subtitle in enumerate(self.subtitles):
            start_time = subtitle["start"]
            end_time = start_time + subtitle["duration"]
            
            if start_time <= current_time <= end_time:
                found_subtitle = True
                if i != self.current_subtitle_index:
                    self.current_subtitle_index = i
                    self.subtitle_label.setText(subtitle["text"])
                return
        
        # Nếu không tìm thấy phụ đề nào hiện tại
        if not found_subtitle:
            self.subtitle_label.setText("")
            self.current_subtitle_index = -1
    
    def enterEvent(self, event):
        """Hiển thị controls khi chuột di chuyển vào overlay"""
        self.controls_widget.setVisible(True)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Ẩn controls khi chuột di chuyển ra khỏi overlay"""
        self.controls_widget.setVisible(False)
        super().leaveEvent(event)
    
    def mousePressEvent(self, event):
        """Cho phép di chuyển cửa sổ overlay"""
        # Chỉ thiết lập drag_position nếu nhấn chuột trái trực tiếp lên widget (không phải lên slider)
        if event.button() == Qt.MouseButton.LeftButton:
             self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        else:
             self.drag_position = None # Đảm bảo reset nếu nhấn nút khác
        super().mousePressEvent(event) # Vẫn gọi super để các widget con xử lý event của chúng
    
    def mouseMoveEvent(self, event):
        """Di chuyển cửa sổ overlay theo chuột"""
        # Chỉ di chuyển nếu đang nhấn giữ chuột trái VÀ drag_position đã được thiết lập
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_position)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Reset drag_position khi nhả chuột"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = None
        super().mouseReleaseEvent(event)
    
    def closeEvent(self, event):
        """Dừng phát khi đóng cửa sổ"""
        self.player.stop()
        self.timer.stop()
        super().closeEvent(event)

    def update_background_transparency(self, value):
        """Cập nhật độ trong suốt của nền PHỤ ĐỀ dựa trên giá trị slider (0-100)"""
        self.background_alpha = value
        # Đảm bảo alpha không bao giờ hoàn toàn bằng 0 để bắt sự kiện hover
        min_alpha = 0.01 # 1%
        alpha_percent = max(min_alpha, self.background_alpha / 100.0)
        
        # Chỉ cập nhật stylesheet cho nhãn phụ đề
        self.subtitle_label.setStyleSheet(f"""
            background-color: rgba(0, 0, 0, {alpha_percent});
            color: white;
            border-radius: 5px;
            padding: 10px;
        """)
        
        # Giữ nền của widget điều khiển cố định (ví dụ: 70% alpha)
        controls_alpha = 0.7 # 70%
        self.controls_widget.setStyleSheet(f"""
            background-color: rgba(0, 0, 0, {controls_alpha});
            border-radius: 5px;
        """)
        
        # Cập nhật màu chữ cho nhãn thời gian (vẫn giữ logic này để đảm bảo dễ đọc trên nền cố định)
        text_color = "white" # Luôn là trắng vì nền control cố định là màu tối
        self.time_label.setStyleSheet(f"color: {text_color}; padding: 5px;") 