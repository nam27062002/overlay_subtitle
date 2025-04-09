import os
import json
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout, QSlider, QCheckBox, QMessageBox
from PyQt6.QtCore import Qt, QTimer, QUrl, QSettings, QThread, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtGui import QFont, QFontMetrics

# Try to import translation library
try:
    import translators as ts
    TRANSLATORS_AVAILABLE = True
except ImportError:
    TRANSLATORS_AVAILABLE = False
    print("The 'translators' library is not installed. Automatic translation feature will not work.")
    print("Run 'pip install translators' to install.")

# Identifiers for QSettings
ORGANIZATION_NAME = "ntrantrong"
APPLICATION_NAME = "OverlaySubtitles"

# --- Translation Thread --- (Background thread for translation)
class TranslationThread(QThread):
    translation_complete = pyqtSignal(list)
    translation_error = pyqtSignal(str)

    def __init__(self, subtitles_list):
        super().__init__()
        self.subtitles_to_translate = subtitles_list

    def run(self):
        if not TRANSLATORS_AVAILABLE:
            self.translation_error.emit("The 'translators' library is not installed.")
            return
            
        translated_count = 0
        errors = []
        updated_subtitles = [] # Create new list to avoid modifying the list being used by main thread

        for i, subtitle in enumerate(self.subtitles_to_translate):
            current_subtitle_copy = subtitle.copy() # Work on a copy
            vi_text = current_subtitle_copy.get("vi_text", "")
            en_text = current_subtitle_copy.get("text", "")

            if not vi_text and en_text: # If no Vietnamese translation yet and English text exists
                try:
                    # Choose translator, e.g. 'google'. Can try 'bing', 'deepl' if needed.
                    translated_vi = ts.translate_text(
                        en_text, 
                        translator='google', 
                        from_language='en', 
                        to_language='vi'
                    )
                    current_subtitle_copy["vi_text"] = translated_vi
                    translated_count += 1
                    print(f"Translated subtitle {i+1}: {en_text} -> {translated_vi}") # Debug
                except Exception as e:
                    error_msg = f"Error translating subtitle {i+1}: {str(e)}"
                    print(error_msg)
                    errors.append(error_msg)
                    # Still add to list to preserve original subtitle
            
            updated_subtitles.append(current_subtitle_copy)
            # Add small sleep to avoid API overload (if needed)
            # self.msleep(50)

        if errors:
            self.translation_error.emit("Errors occurred during translation:\n" + "\n".join(errors[:5]) + ("\n..." if len(errors) > 5 else ""))
        
        print(f"Translation complete. Translated {translated_count} sentences.")
        self.translation_complete.emit(updated_subtitles)

# --- OverlaySubtitle Class --- 
class OverlaySubtitle(QWidget):
    DEFAULT_ALPHA = 70
    DEFAULT_FONT_SIZE = 16
    MIN_FONT_SIZE = 10
    MAX_FONT_SIZE = 30
    DEFAULT_PLAYBACK_RATE = 1.0 # Default speed
    MIN_PLAYBACK_RATE = 0.25
    MAX_PLAYBACK_RATE = 2.0
    # Fixed speed levels
    PLAYBACK_RATES = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]
    # Slider mapping: 25 -> 0.25x, 50 -> 0.5x, 100 -> 1.0x, 200 -> 2.0x
    SLIDER_TO_RATE_FACTOR = 100
    DEFAULT_SHOW_VIETSUB = False # Default to not showing Vietnamese subtitles

    def __init__(self, video):
        super().__init__()
        
        self.video = video
        self.subtitles = []
        self.current_subtitle_index = -1
        self.drag_position = None
        self.translations_attempted = False # Flag to mark if translation has been attempted
        self.translation_thread = None # Keep reference to translation thread

        # Load settings
        self.settings = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)
        self.background_alpha = self.settings.value("overlay/backgroundAlpha", self.DEFAULT_ALPHA, type=int)
        self.current_font_size = self.settings.value("overlay/fontSize", self.DEFAULT_FONT_SIZE, type=int)
        self.current_playback_rate = self.settings.value("overlay/playbackRate", self.DEFAULT_PLAYBACK_RATE, type=float)
        self.show_vietnamese = self.settings.value("overlay/showVietnamese", self.DEFAULT_SHOW_VIETSUB, type=bool)
        # Ensure values are within valid limits
        self.current_font_size = max(self.MIN_FONT_SIZE, min(self.MAX_FONT_SIZE, self.current_font_size))
        self.current_playback_rate = max(self.MIN_PLAYBACK_RATE, min(self.MAX_PLAYBACK_RATE, self.current_playback_rate))
        
        # Load subtitles
        if self.video.get("subtitle_path") and os.path.exists(self.video["subtitle_path"]):
            try:
                with open(self.video["subtitle_path"], 'r', encoding='utf-8') as f:
                    self.subtitles = json.load(f)
            except Exception as e:
                print(f"Error reading subtitle file: {str(e)}")
                self.subtitles = []
        
        # Setup overlay window
        self.setWindowTitle("Subtitle Overlay")
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
        self.time_label.setFixedWidth(80) # Reduce width a bit
        control_layout.addWidget(self.time_label)

        # Transparency slider
        control_layout.addWidget(QLabel("Transparency:"))
        self.transparency_slider = QSlider(Qt.Orientation.Horizontal)
        self.transparency_slider.setRange(0, 100)
        self.transparency_slider.setValue(self.background_alpha)
        self.transparency_slider.setFixedWidth(60) # Reduce width
        self.transparency_slider.valueChanged.connect(self.update_background_transparency)
        control_layout.addWidget(self.transparency_slider)

        # Font size slider
        control_layout.addWidget(QLabel("Font Size:"))
        self.font_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_size_slider.setRange(self.MIN_FONT_SIZE, self.MAX_FONT_SIZE)
        self.font_size_slider.setValue(self.current_font_size)
        self.font_size_slider.setFixedWidth(60) # Reduce width
        self.font_size_slider.valueChanged.connect(self.update_font_size)
        control_layout.addWidget(self.font_size_slider)

        # Speed slider and label
        control_layout.addWidget(QLabel("Speed:"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        # Convert rate to slider value (0.25 -> 25, 0.5 -> 50, 1.0 -> 100, 2.0 -> 200)
        min_slider_val = int(self.MIN_PLAYBACK_RATE * self.SLIDER_TO_RATE_FACTOR)
        max_slider_val = int(self.MAX_PLAYBACK_RATE * self.SLIDER_TO_RATE_FACTOR)
        self.speed_slider.setRange(min_slider_val, max_slider_val)
        self.speed_slider.setValue(int(self.current_playback_rate * self.SLIDER_TO_RATE_FACTOR))
        self.speed_slider.setFixedWidth(60) # Reduce width
        self.speed_slider.valueChanged.connect(self.update_playback_speed)
        control_layout.addWidget(self.speed_slider)
        
        self.speed_label = QLabel(f"{self.current_playback_rate:.2f}x") # Label displaying speed
        self.speed_label.setFixedWidth(40)
        control_layout.addWidget(self.speed_label)
        
        # Show Vietnamese Checkbox
        self.vietsub_checkbox = QCheckBox("Show Vietnamese")
        self.vietsub_checkbox.setChecked(self.show_vietnamese)
        self.vietsub_checkbox.setStyleSheet("color: white;") # For better visibility on dark background
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
        # Update initial playback rate for player (AFTER PLAYER IS CREATED)
        self.player.setPlaybackRate(self.current_playback_rate)

        # Load audio
        audio_path = self.video.get("audio_path", "")
        if audio_path:
            abs_audio_path = os.path.abspath(audio_path)
            
            if os.path.exists(abs_audio_path):
                self.player.setSource(QUrl.fromLocalFile(abs_audio_path))
                print(f"Found audio file at: {abs_audio_path}")
            else:
                current_dir = os.getcwd()
                alternative_path = os.path.join(current_dir, audio_path)
                
                if os.path.exists(alternative_path):
                    self.player.setSource(QUrl.fromLocalFile(alternative_path))
                    print(f"Found audio file at: {alternative_path}")
                else:
                    print(f"Could not find audio file: {audio_path}")
        
        # Connect signals
        self.player.durationChanged.connect(self.update_duration)
        self.player.positionChanged.connect(self.update_position)
        
        # Timer for subtitle update
        self.timer = QTimer(self)
        self.timer.setInterval(100)  # 100ms
        self.timer.timeout.connect(self.update_subtitle)
        
        # Calculate initial size based on screen width
        screen_width = self.screen().geometry().width()
        self.setMinimumWidth(int(screen_width * 0.6)) # Increase width a bit to fit new sliders
        self.resize(int(screen_width * 0.6), 120)
        
        # Position at the bottom of the screen
        self.move_to_bottom()
        
        # Start playing
        self.player.play()
        self.play_button.setText("⏸")
        self.timer.start()
        
        # Automatically start translation if setting is enabled
        if self.show_vietnamese and not self.translations_attempted:
            self.start_translation()
    
    def move_to_bottom(self):
        """Move overlay to bottom of screen"""
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
        current_time = self.player.position() / 1000  # Convert from ms to s
        
        found_subtitle_this_cycle = False
        current_display_subtitle_index = self.current_subtitle_index

        if not self.subtitles:
            if self.subtitle_label.text() != "No subtitles":
                 self.subtitle_label.setText("No subtitles")
            return

        for i, subtitle in enumerate(self.subtitles):
            start_time = subtitle["start"]
            end_time = start_time + subtitle["duration"]
            
            if start_time <= current_time < end_time:
                found_subtitle_this_cycle = True
                # Only update label if index changed OR forced (due to toggle vietsub)
                if i != self.current_subtitle_index or force_update:
                    self.current_subtitle_index = i
                    en_text = subtitle["text"]
                    display_text = en_text # Default to English

                    if self.show_vietnamese:
                        print(f"Attempting to get vi_text for: {subtitle}") # DEBUG PRINT
                        vi_text = subtitle.get("vi_text", "") # Get Vietnamese text (assuming key is vi_text)
                        print(f"Got vi_text: '{vi_text}'") # DEBUG PRINT
                        if vi_text: # If Vietnamese text exists
                            # Use HTML for line breaks and styling
                            # Light gray and slightly smaller for Vietnamese text
                            vi_font_size = max(self.MIN_FONT_SIZE, self.current_font_size - 4) 
                            display_text = (f"{en_text}<br>"
                                            f"<i style='color: #cccccc; font-size: {vi_font_size}pt;'>{vi_text}</i>")
                            print("vi_text found, formatting...") # DEBUG PRINT
                    
                    self.subtitle_label.setText(display_text)
                return # Exit immediately when suitable subtitle is found

        # If loop ends without finding a subtitle in the current time range
        if not found_subtitle_this_cycle:
            # Only clear text if previously displaying a subtitle
            if self.current_subtitle_index != -1 or force_update:
                 self.subtitle_label.setText("")
                 self.current_subtitle_index = -1
    
    def toggle_vietnamese_display(self, checked):
        """Toggle Vietnamese subtitle display on/off"""
        self.show_vietnamese = checked
        
        # If turning on Vietnamese subtitles and haven't attempted translation yet
        if checked and not self.translations_attempted:
            self.start_translation()
        
        # Refresh current subtitle display with new setting
        self.update_subtitle(force_update=True)
    
    def start_translation(self):
        """Start background translation if needed"""
        if not self.subtitles or self.translations_attempted:
            return
            
        # Check if subtitles already have translations
        need_translation = False
        for sub in self.subtitles:
            if not sub.get("vi_text"):
                need_translation = True
                break
                
        if need_translation:
            self.translations_attempted = True # Mark as attempted regardless of success
            
            # Create and start translation thread
            self.translation_thread = TranslationThread(self.subtitles)
            self.translation_thread.translation_complete.connect(self.on_translation_complete)
            self.translation_thread.translation_error.connect(self.on_translation_error)
            self.translation_thread.start()
            
            # Show "translating" message
            QMessageBox.information(self, "Translation", "Translating subtitles in the background.\nThis may take a few minutes.")
    
    def on_translation_complete(self, translated_subtitles):
        """Handle completed translations"""
        # Update subtitles with translated versions
        self.subtitles = translated_subtitles
        
        # Save updated subtitles to file if possible
        if self.video.get("subtitle_path"):
            try:
                with open(self.video["subtitle_path"], 'w', encoding='utf-8') as f:
                    json.dump(self.subtitles, f, ensure_ascii=False, indent=4)
                print("Translations saved to subtitle file")
            except Exception as e:
                print(f"Error saving translations: {e}")
        
        # Update current display if needed
        self.update_subtitle(force_update=True)
        
    def on_translation_error(self, error_message):
        """Handle translation errors"""
        QMessageBox.warning(self, "Translation Error", error_message)
    
    def update_background_transparency(self, value):
        """Update background transparency and apply style"""
        self.background_alpha = value
        background_color = f"rgba(0, 0, 0, {value/100})"
        
        # Style for main window
        self.setStyleSheet(f"""
            QWidget {{ background-color: {background_color}; }}
            QLabel {{ color: white; font-weight: bold; background-color: transparent; }}
        """)
        
        # Style for subtitle text
        self.update_font_size(self.current_font_size) # This also updates the font style
    
    def update_font_size(self, size):
        """Update font size for subtitle text"""
        self.current_font_size = size
        
        font = QFont()
        font.setPointSize(size)
        font.setBold(True)
        self.subtitle_label.setFont(font)
        
        # Set drop shadow style for better readability
        self.subtitle_label.setStyleSheet(f"""
            color: white; 
            background-color: transparent;
            font-size: {size}pt;
            text-shadow: 1px 1px 2px black, 0 0 1em black;
        """)
    
    def update_playback_speed(self, value):
        # Convert slider value to playback rate
        raw_rate = value / self.SLIDER_TO_RATE_FACTOR
        
        # Find the closest rate in the allowed list
        closest_rate = min(self.PLAYBACK_RATES, key=lambda x: abs(x - raw_rate))
        
        self.current_playback_rate = closest_rate
        self.player.setPlaybackRate(self.current_playback_rate)
        self.speed_label.setText(f"{self.current_playback_rate:.2f}x")
        self.speed_slider.setValue(int(self.current_playback_rate * self.SLIDER_TO_RATE_FACTOR))
    
    def enterEvent(self, event):
        """Show controls when mouse moves into overlay"""
        self.controls_widget.setVisible(True)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Hide controls when mouse leaves overlay"""
        self.controls_widget.setVisible(False)
        super().leaveEvent(event)
    
    def mousePressEvent(self, event):
        """Allow moving the overlay window"""
        # Only set drag_position if left mouse button is pressed directly on widget (not on slider)
        if event.button() == Qt.MouseButton.LeftButton:
             self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        else:
             self.drag_position = None # Ensure reset if other button is pressed
        super().mousePressEvent(event) # Still call super to let child widgets handle their events
    
    def mouseMoveEvent(self, event):
        """Move overlay window with mouse"""
        # Only move if left mouse button is held AND drag_position is set
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_position)
        super().mouseMoveEvent(event)
    
    def closeEvent(self, event):
        """Save settings, stop translation thread (if running) and stop playback when closing window"""
        # Stop translation thread if running
        if self.translation_thread and self.translation_thread.isRunning():
            print("Requesting translation thread to stop...")
            # No direct way to hard stop thread, but can request exit
            # However, translation might be nearly complete, so let it finish or error on its own
            # Just ensure not to use results if widget is closed
            self.translation_thread.quit() # Request exit from event loop (if any)
            # self.translation_thread.wait(1000) # Wait maximum 1 second
            
        # Save settings
        self.settings.setValue("overlay/backgroundAlpha", self.background_alpha)
        self.settings.setValue("overlay/fontSize", self.current_font_size)
        self.settings.setValue("overlay/playbackRate", self.current_playback_rate)
        self.settings.setValue("overlay/showVietnamese", self.show_vietnamese)
        
        # Stop playback
        self.player.stop()
        self.timer.stop()
        super().closeEvent(event) 