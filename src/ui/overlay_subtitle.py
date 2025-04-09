import os
import json
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout, QSlider, QCheckBox, QMessageBox
from PyQt6.QtCore import Qt, QTimer, QUrl, QSettings, QThread, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtGui import QFont, QFontMetrics

# Thử import thư viện dịch
try:
    import translators as ts
    TRANSLATORS_AVAILABLE = True
except ImportError:
    TRANSLATORS_AVAILABLE = False
    print("Thư viện 'translators' chưa được cài đặt. Tính năng tự động dịch sẽ không hoạt động.")
    print("Chạy 'pip install translators' để cài đặt.")

# Định danh cho QSettings
ORGANIZATION_NAME = "ntrantrong"
APPLICATION_NAME = "OverlaySubtitles"

# --- Translation Thread --- (Thêm QThread để dịch ngầm)
class TranslationThread(QThread):
    translation_complete = pyqtSignal(list)
    translation_error = pyqtSignal(str)

    def __init__(self, subtitles_list):
        super().__init__()
        self.subtitles_to_translate = subtitles_list

    def run(self):
        if not TRANSLATORS_AVAILABLE:
            self.translation_error.emit("Thư viện 'translators' chưa được cài đặt.")
            return
            
        translated_count = 0
        errors = []
        updated_subtitles = [] # Tạo list mới để tránh sửa list đang được dùng bởi thread chính

        for i, subtitle in enumerate(self.subtitles_to_translate):
            current_subtitle_copy = subtitle.copy() # Làm việc trên bản sao
            vi_text = current_subtitle_copy.get("vi_text", "")
            en_text = current_subtitle_copy.get("text", "")

            if not vi_text and en_text: # Nếu chưa có vietsub và có english
                try:
                    # Chọn translator, ví dụ 'google'. Có thể thử 'bing', 'deepl' nếu cần.
                    translated_vi = ts.translate_text(
                        en_text, 
                        translator='google', 
                        from_language='en', 
                        to_language='vi'
                    )
                    current_subtitle_copy["vi_text"] = translated_vi
                    translated_count += 1
                    print(f"Đã dịch sub {i+1}: {en_text} -> {translated_vi}") # Debug
                except Exception as e:
                    error_msg = f"Lỗi dịch sub {i+1}: {str(e)}"
                    print(error_msg)
                    errors.append(error_msg)
                    # Vẫn thêm vào list để không mất phụ đề gốc
            
            updated_subtitles.append(current_subtitle_copy)
            # Thêm sleep nhỏ để tránh quá tải API (nếu cần)
            # self.msleep(50)

        if errors:
            self.translation_error.emit("Đã xảy ra lỗi trong quá trình dịch:\n" + "\n".join(errors[:5]) + ("\n..." if len(errors) > 5 else ""))
        
        print(f"Hoàn tất dịch. Đã dịch {translated_count} câu.")
        self.translation_complete.emit(updated_subtitles)

# --- OverlaySubtitle Class --- 
class OverlaySubtitle(QWidget):
    DEFAULT_ALPHA = 70
    DEFAULT_FONT_SIZE = 16
    MIN_FONT_SIZE = 10
    MAX_FONT_SIZE = 30
    DEFAULT_PLAYBACK_RATE = 1.0 # Tốc độ mặc định
    MIN_PLAYBACK_RATE = 0.25
    MAX_PLAYBACK_RATE = 2.0
    # Các mức tốc độ cố định
    PLAYBACK_RATES = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]
    # Ánh xạ slider: 25 -> 0.25x, 50 -> 0.5x, 100 -> 1.0x, 200 -> 2.0x
    SLIDER_TO_RATE_FACTOR = 100
    DEFAULT_SHOW_VIETSUB = False # Mặc định không hiện Vietsub

    def __init__(self, video):
        super().__init__()
        
        self.video = video
        self.subtitles = []
        self.current_subtitle_index = -1
        self.drag_position = None
        self.translations_attempted = False # Cờ đánh dấu đã thử dịch chưa
        self.translation_thread = None # Giữ tham chiếu đến thread dịch

        # Tải cài đặt
        self.settings = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)
        self.background_alpha = self.settings.value("overlay/backgroundAlpha", self.DEFAULT_ALPHA, type=int)
        self.current_font_size = self.settings.value("overlay/fontSize", self.DEFAULT_FONT_SIZE, type=int)
        self.current_playback_rate = self.settings.value("overlay/playbackRate", self.DEFAULT_PLAYBACK_RATE, type=float)
        self.show_vietnamese = self.settings.value("overlay/showVietnamese", self.DEFAULT_SHOW_VIETSUB, type=bool)
        # Đảm bảo các giá trị đọc được nằm trong giới hạn hợp lệ
        self.current_font_size = max(self.MIN_FONT_SIZE, min(self.MAX_FONT_SIZE, self.current_font_size))
        self.current_playback_rate = max(self.MIN_PLAYBACK_RATE, min(self.MAX_PLAYBACK_RATE, self.current_playback_rate))
        
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
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setTextFormat(Qt.TextFormat.RichText)
        main_layout.addWidget(self.subtitle_label)
        
        # Control layout
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(5, 5, 5, 5)
        
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
        self.time_label.setFixedWidth(80) # Giảm độ rộng một chút
        control_layout.addWidget(self.time_label)

        # Transparency slider
        control_layout.addWidget(QLabel("Trong suốt:"))
        self.transparency_slider = QSlider(Qt.Orientation.Horizontal)
        self.transparency_slider.setRange(0, 100)
        self.transparency_slider.setValue(self.background_alpha)
        self.transparency_slider.setFixedWidth(60) # Giảm độ rộng
        self.transparency_slider.valueChanged.connect(self.update_background_transparency)
        control_layout.addWidget(self.transparency_slider)

        # Font size slider
        control_layout.addWidget(QLabel("Cỡ chữ:"))
        self.font_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_size_slider.setRange(self.MIN_FONT_SIZE, self.MAX_FONT_SIZE)
        self.font_size_slider.setValue(self.current_font_size)
        self.font_size_slider.setFixedWidth(60) # Giảm độ rộng
        self.font_size_slider.valueChanged.connect(self.update_font_size)
        control_layout.addWidget(self.font_size_slider)

        # Speed slider and label
        control_layout.addWidget(QLabel("Tốc độ:"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        # Chuyển đổi rate sang giá trị slider (0.25 -> 25, 0.5 -> 50, 1.0 -> 100, 2.0 -> 200)
        min_slider_val = int(self.MIN_PLAYBACK_RATE * self.SLIDER_TO_RATE_FACTOR)
        max_slider_val = int(self.MAX_PLAYBACK_RATE * self.SLIDER_TO_RATE_FACTOR)
        self.speed_slider.setRange(min_slider_val, max_slider_val)
        self.speed_slider.setValue(int(self.current_playback_rate * self.SLIDER_TO_RATE_FACTOR))
        self.speed_slider.setFixedWidth(60) # Giảm độ rộng
        self.speed_slider.valueChanged.connect(self.update_playback_speed)
        control_layout.addWidget(self.speed_slider)
        
        self.speed_label = QLabel(f"{self.current_playback_rate:.2f}x") # Nhãn hiển thị tốc độ
        self.speed_label.setFixedWidth(40)
        control_layout.addWidget(self.speed_label)
        
        # Show Vietsub Checkbox
        self.vietsub_checkbox = QCheckBox("Hiện Vietsub")
        self.vietsub_checkbox.setChecked(self.show_vietnamese)
        self.vietsub_checkbox.setStyleSheet("color: white;") # Cho dễ nhìn trên nền tối
        self.vietsub_checkbox.toggled.connect(self.toggle_vietnamese_display)
        control_layout.addWidget(self.vietsub_checkbox)
        
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
        
        # Media player
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        # Initial style, font, and speed update
        self.update_font_size(self.current_font_size)
        self.update_background_transparency(self.background_alpha)
        # Cập nhật tốc độ phát ban đầu cho player (SAU KHI PLAYER ĐƯỢC TẠO)
        self.player.setPlaybackRate(self.current_playback_rate)

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
        self.setMinimumWidth(int(screen_width * 0.6)) # Tăng chiều rộng một chút để chứa slider mới
        self.resize(int(screen_width * 0.6), 120)
        
        # Position at the bottom of the screen
        self.move_to_bottom()
        
        # Start playing
        self.player.play()
        self.play_button.setText("⏸")
        self.timer.start()
        
        # Tự động bắt đầu dịch nếu cài đặt được bật sẵn
        if self.show_vietnamese and not self.translations_attempted:
            self.start_translation()
    
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
    
    def update_subtitle(self, force_update=False):
        current_time = self.player.position() / 1000  # Chuyển đổi từ ms sang s
        
        found_subtitle_this_cycle = False
        current_display_subtitle_index = self.current_subtitle_index

        if not self.subtitles:
            if self.subtitle_label.text() != "Không có phụ đề":
                 self.subtitle_label.setText("Không có phụ đề")
            return

        for i, subtitle in enumerate(self.subtitles):
            start_time = subtitle["start"]
            end_time = start_time + subtitle["duration"]
            
            if start_time <= current_time < end_time:
                found_subtitle_this_cycle = True
                # Chỉ cập nhật label nếu index thay đổi HOẶC bị ép buộc (do toggle vietsub)
                if i != self.current_subtitle_index or force_update:
                    self.current_subtitle_index = i
                    en_text = subtitle["text"]
                    display_text = en_text # Mặc định là tiếng Anh

                    if self.show_vietnamese:
                        print(f"Attempting to get vi_text for: {subtitle}") # DEBUG PRINT
                        vi_text = subtitle.get("vi_text", "") # Lấy Vietsub (giả định key là vi_text)
                        print(f"Got vi_text: '{vi_text}'") # DEBUG PRINT
                        if vi_text: # Nếu có Vietsub
                            # Sử dụng HTML để xuống dòng và tạo kiểu
                            # Màu xám nhạt và nhỏ hơn một chút cho Vietsub
                            vi_font_size = max(self.MIN_FONT_SIZE, self.current_font_size - 4) 
                            display_text = (f"{en_text}<br>"
                                            f"<i style='color: #cccccc; font-size: {vi_font_size}pt;'>{vi_text}</i>")
                            print("vi_text found, formatting...") # DEBUG PRINT
                    
                    self.subtitle_label.setText(display_text)
                return # Thoát ngay khi tìm thấy phụ đề phù hợp

        # Nếu vòng lặp kết thúc mà không tìm thấy phụ đề nào trong khoảng thời gian hiện tại
        if not found_subtitle_this_cycle:
            # Chỉ xóa text nếu trước đó đang hiển thị một phụ đề nào đó
            if self.current_subtitle_index != -1 or force_update:
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
        """Lưu cài đặt và dừng phát khi đóng cửa sổ"""
        # Lưu cài đặt
        self.settings.setValue("overlay/backgroundAlpha", self.background_alpha)
        self.settings.setValue("overlay/fontSize", self.current_font_size)
        self.settings.setValue("overlay/playbackRate", self.current_playback_rate) # Lưu tốc độ
        self.settings.setValue("overlay/showVietnamese", self.show_vietnamese) # Lưu trạng thái Vietsub
        
        # Dừng phát
        self.player.stop()
        self.timer.stop()
        
        # Dừng thread dịch nếu đang chạy
        if self.translation_thread and self.translation_thread.isRunning():
            print("Đang yêu cầu dừng luồng dịch...")
            # Không có cách trực tiếp dừng thread cứng rắn, nhưng có thể yêu cầu thoát
            # Tuy nhiên, việc dịch có thể đã gần xong, nên cứ để nó hoàn thành hoặc tự lỗi
            # Chỉ cần đảm bảo không sử dụng kết quả nếu widget đã đóng
            self.translation_thread.quit() # Yêu cầu thoát vòng lặp sự kiện (nếu có)
            # self.translation_thread.wait(1000) # Chờ tối đa 1 giây
        
        super().closeEvent(event)

    def update_font_size(self, value):
        """Cập nhật kích thước font chữ của phụ đề"""
        self.current_font_size = value
        font = self.subtitle_label.font() # Lấy font hiện tại
        font.setPointSize(self.current_font_size)
        self.subtitle_label.setFont(font)
        # Ép cập nhật lại text để áp dụng style HTML mới (nếu đang hiện vietsub)
        self.update_subtitle(force_update=True)

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

    def update_playback_speed(self, value):
        # Chuyển đổi giá trị slider sang playback rate
        raw_rate = value / self.SLIDER_TO_RATE_FACTOR
        
        # Tìm giá trị tốc độ gần nhất trong danh sách cho phép
        closest_rate = min(self.PLAYBACK_RATES, key=lambda x: abs(x - raw_rate))
        
        self.current_playback_rate = closest_rate
        self.player.setPlaybackRate(self.current_playback_rate)
        self.speed_label.setText(f"{self.current_playback_rate:.2f}x")
        self.speed_slider.setValue(int(self.current_playback_rate * self.SLIDER_TO_RATE_FACTOR))
    
    def toggle_vietnamese_display(self, checked):
        """Cập nhật trạng thái hiển thị Vietsub và làm mới phụ đề hiện tại (nếu có)"""
        self.show_vietnamese = checked
        # Nếu bật và chưa thử dịch lần nào, bắt đầu dịch
        if checked and not self.translations_attempted:
            self.start_translation()
        # Luôn cập nhật hiển thị phụ đề hiện tại theo trạng thái mới
        self.update_subtitle(force_update=True)
    
    def start_translation(self):
        """Bắt đầu quá trình dịch ngầm nếu cần thiết."""
        if not TRANSLATORS_AVAILABLE:
            # Không hiển thị messagebox ở đây vì đã báo lỗi lúc import
            # Chỉ đặt cờ để không thử lại
            self.translations_attempted = True 
            return

        if not self.subtitles:
            print("Không có phụ đề để dịch.")
            self.translations_attempted = True # Đánh dấu đã xử lý (dù không có gì để dịch)
            return
            
        # Kiểm tra xem có cần dịch không (còn câu nào thiếu vi_text không)
        needs_translation = any(not sub.get('vi_text') and sub.get('text') for sub in self.subtitles)
        
        if not needs_translation:
             print("Tất cả phụ đề đã có Vietsub hoặc không cần dịch.")
             self.translations_attempted = True # Đánh dấu đã xử lý
             return

        print("Bắt đầu dịch phụ đề...")
        # Vô hiệu hóa checkbox trong khi dịch?
        # self.vietsub_checkbox.setEnabled(False) 
        self.translation_thread = TranslationThread(self.subtitles)
        self.translation_thread.translation_complete.connect(self.on_translation_complete)
        self.translation_thread.translation_error.connect(self.on_translation_error)
        self.translation_thread.finished.connect(self.on_translation_finished) # Để bật lại checkbox
        self.translation_thread.start()

    def on_translation_complete(self, translated_subtitles):
        """Xử lý khi luồng dịch hoàn tất thành công."""
        print("Nhận kết quả dịch.")
        self.subtitles = translated_subtitles # Cập nhật list phụ đề với bản dịch
        self.translations_attempted = True
        self.update_subtitle(force_update=True) # Cập nhật hiển thị ngay

    def on_translation_error(self, error_message):
        """Xử lý khi có lỗi trong luồng dịch."""
        print(f"Lỗi luồng dịch: {error_message}")
        # Hiển thị lỗi cho người dùng một lần
        if not self.translations_attempted: # Chỉ hiện nếu đây là lỗi đầu tiên
             QMessageBox.warning(self, "Lỗi Dịch Thuật", f"Không thể tự động dịch phụ đề:\n{error_message}")
        self.translations_attempted = True # Đánh dấu đã thử để không lặp lại

    def on_translation_finished(self):
         """Được gọi khi luồng dịch kết thúc (thành công hoặc lỗi)."""
         print("Luồng dịch đã kết thúc.")
         self.translation_thread = None # Dọn dẹp tham chiếu
         # Bật lại checkbox nếu đã vô hiệu hóa
         # self.vietsub_checkbox.setEnabled(True)

    def update_subtitle(self, force_update=False):
        """Cập nhật phụ đề hiển thị, có thể ép buộc cập nhật định dạng"""
        current_time = self.player.position() / 1000
        found_subtitle_this_cycle = False

        if not self.subtitles:
            if self.subtitle_label.text() != "Không có phụ đề":
                 self.subtitle_label.setText("Không có phụ đề")
            return

        subtitle_to_display = None
        subtitle_index = -1

        # Tìm phụ đề phù hợp với thời gian hiện tại
        for i, subtitle in enumerate(self.subtitles):
            start_time = subtitle.get("start", 0)
            duration = subtitle.get("duration", 0)
            end_time = start_time + duration
            if start_time <= current_time < end_time:
                subtitle_to_display = subtitle
                subtitle_index = i
                found_subtitle_this_cycle = True
                break 

        # Cập nhật QLabel chỉ khi cần thiết
        if found_subtitle_this_cycle:
            if subtitle_index != self.current_subtitle_index or force_update:
                self.current_subtitle_index = subtitle_index
                en_text = subtitle_to_display.get("text", "")
                display_text = en_text

                if self.show_vietnamese:
                    # Luôn lấy vi_text từ self.subtitles đã được cập nhật (hoặc không)
                    vi_text = subtitle_to_display.get("vi_text", "") 
                    if vi_text:
                        vi_font_size = max(self.MIN_FONT_SIZE, self.current_font_size - 4)
                        display_text = (f"{en_text}<br>"
                                        f"<i style='color: #cccccc; font-size: {vi_font_size}pt;'>{vi_text}</i>")
                    # Không cần else ở đây, nếu vi_text rỗng thì display_text giữ nguyên là en_text
                
                self.subtitle_label.setText(display_text)
        else: # Không tìm thấy phụ đề nào cho thời gian hiện tại
            if self.current_subtitle_index != -1: # Nếu trước đó đang hiển thị gì đó
                 self.subtitle_label.setText("")
                 self.current_subtitle_index = -1
    
    def closeEvent(self, event):
        """Lưu cài đặt, dừng thread dịch (nếu đang chạy) và dừng phát khi đóng cửa sổ"""
        # Dừng thread dịch nếu đang chạy
        if self.translation_thread and self.translation_thread.isRunning():
            print("Đang yêu cầu dừng luồng dịch...")
            # Không có cách trực tiếp dừng thread cứng rắn, nhưng có thể yêu cầu thoát
            # Tuy nhiên, việc dịch có thể đã gần xong, nên cứ để nó hoàn thành hoặc tự lỗi
            # Chỉ cần đảm bảo không sử dụng kết quả nếu widget đã đóng
            self.translation_thread.quit() # Yêu cầu thoát vòng lặp sự kiện (nếu có)
            # self.translation_thread.wait(1000) # Chờ tối đa 1 giây
            
        # Lưu cài đặt
        self.settings.setValue("overlay/backgroundAlpha", self.background_alpha)
        self.settings.setValue("overlay/fontSize", self.current_font_size)
        self.settings.setValue("overlay/playbackRate", self.current_playback_rate)
        self.settings.setValue("overlay/showVietnamese", self.show_vietnamese)
        
        # Dừng phát
        self.player.stop()
        self.timer.stop()
        super().closeEvent(event)

    # --- Các hàm xử lý sự kiện còn lại --- (move_to_bottom, enter/leaveEvent, mouse events)
    def move_to_bottom(self):
        """Di chuyển overlay đến vị trí phía dưới màn hình"""
        screen_geometry = self.screen().geometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = screen_geometry.height() - self.height() - 100  # 100 pixels from bottom
        self.move(x, y)
    
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
        if event.button() == Qt.MouseButton.LeftButton:
             self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        else:
             self.drag_position = None
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Di chuyển cửa sổ overlay theo chuột"""
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_position)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Reset drag_position khi nhả chuột"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = None
        super().mouseReleaseEvent(event) 