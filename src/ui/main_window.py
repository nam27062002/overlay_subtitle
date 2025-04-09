import os
import json
import shutil
from datetime import datetime
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
                            QMessageBox, QSplitter, QProgressBar, QDialog, QFileDialog, QTextEdit)
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
        self.current_progress = 0
        # Weights for each step (total = 100%)
        self.weights = {
            "prepare": 5,       # Preparation: 5%
            "audio": 60,        # Audio download: 60%
            "subtitle": 25,     # Subtitles: 25%
            "thumbnail": 10     # Thumbnail: 10%
        }
        
    def run(self):
        try:
            self.current_progress = 0
            self.download_progress.emit(self.current_progress)
            self.status_update.emit("Preparing to download video...")
            
            # Preparation step
            self.update_progress("prepare", 0)
            
            # Define callback to update progress
            def status_callback(status):
                # Update status
                self.status_update.emit(status)
                
                # Update progress based on status message
                if "Downloading audio:" in status:
                    try:
                        # If there's percentage in the message (e.g., "Downloading audio: 42.0% (1.21MiB/s)")
                        percent_str = status.split('%')[0].split(':')[1].strip()
                        percent = float(percent_str)
                        self.update_progress("audio", percent)
                    except (IndexError, ValueError):
                        pass
                elif "Preparing to download audio" in status:
                    self.update_progress("audio", 0)
                elif "Audio download and processing complete" in status:
                    self.update_progress("audio", 100)
                    
                elif "Searching for subtitles" in status:
                    self.update_progress("subtitle", 0)
                elif "Translating subtitles" in status:
                    self.update_progress("subtitle", 30)
                elif "Subtitle translation complete" in status:
                    self.update_progress("subtitle", 80)
                elif "Saving subtitles complete" in status:
                    self.update_progress("subtitle", 100)
                    
                elif "Downloading thumbnail" in status:
                    self.update_progress("thumbnail", 0)
                elif "Thumbnail download complete" in status or "Default thumbnail downloaded" in status:
                    self.update_progress("thumbnail", 100)
            
            # Download video with callback
            video_info = download_youtube_video(self.url, self.download_folder, status_callback)
            
            # Ensure 100% when completed
            self.current_progress = 100
            self.download_progress.emit(self.current_progress)
            self.status_update.emit("Download completed!")
            self.download_complete.emit(video_info)
            
        except Exception as e:
            error_message = str(e)
            self.download_error.emit(error_message)
            self.status_update.emit(f"Error: {error_message}")
            
    def update_progress(self, step, percent):
        """
        Update progress based on the step and its completion percentage
        step: "prepare", "audio", "subtitle", "thumbnail"
        percent: 0-100 for current step
        """
        # Calculate overall progress
        weight = self.weights.get(step, 0)
        step_progress = (percent / 100) * weight
        
        # Calculate total progress
        if step == "prepare":
            self.current_progress = step_progress
        elif step == "audio":
            self.current_progress = self.weights["prepare"] + step_progress
        elif step == "subtitle":
            self.current_progress = self.weights["prepare"] + self.weights["audio"] + step_progress
        elif step == "thumbnail":
            self.current_progress = self.weights["prepare"] + self.weights["audio"] + self.weights["subtitle"] + step_progress
        
        # Round and limit progress from 0-100
        self.current_progress = min(100, max(0, round(self.current_progress)))
        
        # Emit update signal
        self.download_progress.emit(self.current_progress)

class VideoItem(QWidget):
    def __init__(self, video, parent=None):
        super().__init__(parent)
        self.video = video
        
        # Ensure all required keys exist in the dictionary
        required_keys = ["thumbnail_path", "title", "download_date", "audio_path", "subtitle_path", "video_id"]
        for key in required_keys:
            if key not in video:
                print(f"Missing key {key} in video: {video}")
                if key == "thumbnail_path" or key == "subtitle_path":
                    video[key] = None
                else:
                    video[key] = ""
        
        layout = QHBoxLayout(self)
        
        # Thumbnail image
        thumbnail_label = QLabel()
        thumbnail_path = video.get("thumbnail_path")
        
        if thumbnail_path:
            # Try loading with absolute path
            abs_thumbnail_path = os.path.abspath(thumbnail_path)
            if os.path.exists(abs_thumbnail_path):
                pixmap = QPixmap(abs_thumbnail_path)
                thumbnail_label.setPixmap(pixmap.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio))
            else:
                # Try with relative path from current directory
                current_dir = os.getcwd()
                alternative_path = os.path.join(current_dir, thumbnail_path)
                
                if os.path.exists(alternative_path):
                    pixmap = QPixmap(alternative_path)
                    thumbnail_label.setPixmap(pixmap.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio))
                else:
                    # Thumbnail not found
                    thumbnail_label.setText("No\nthumbnail")
                    thumbnail_label.setStyleSheet("background-color: #eee; color: #666; font-size: 10px; text-align: center;")
                    thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            thumbnail_label.setText("No\nthumbnail")
            thumbnail_label.setStyleSheet("background-color: #eee; color: #666; font-size: 10px; text-align: center;")
            thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        thumbnail_label.setFixedSize(160, 90)
        layout.addWidget(thumbnail_label)
        
        # Video information
        info_layout = QVBoxLayout()
        title_label = QLabel(video.get("title", "No title"))
        title_label.setStyleSheet("font-weight: bold;")
        date_label = QLabel(video.get("download_date", ""))
        info_layout.addWidget(title_label)
        info_layout.addWidget(date_label)
        layout.addLayout(info_layout, 1)
        
        # Control buttons
        buttons_layout = QVBoxLayout()
        
        # Play button
        play_button = QPushButton("Play")
        play_button.setFixedWidth(80)
        play_button.clicked.connect(self.play_video)
        buttons_layout.addWidget(play_button)
        
        # Overlay subtitle button
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
        
        # Ensure all required keys exist
        required_keys = ["thumbnail_path", "title"]
        for key in required_keys:
            if key not in template:
                if key == "thumbnail_path":
                    template[key] = None
                else:
                    template[key] = ""
        
        # Thumbnail image
        thumbnail_label = QLabel()
        thumbnail_path = template.get("thumbnail_path")
        
        if thumbnail_path:
            # Try loading with absolute path
            abs_thumbnail_path = os.path.abspath(thumbnail_path)
            if os.path.exists(abs_thumbnail_path):
                pixmap = QPixmap(abs_thumbnail_path)
                thumbnail_label.setPixmap(pixmap.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio))
            else:
                # Try with relative path from current directory
                current_dir = os.getcwd()
                alternative_path = os.path.join(current_dir, thumbnail_path)
                
                if os.path.exists(alternative_path):
                    pixmap = QPixmap(alternative_path)
                    thumbnail_label.setPixmap(pixmap.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio))
                else:
                    # Thumbnail not found
                    thumbnail_label.setText("No\nthumbnail")
                    thumbnail_label.setStyleSheet("background-color: #eee; color: #666; font-size: 10px; text-align: center;")
                    thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            thumbnail_label.setText("No\nthumbnail")
            thumbnail_label.setStyleSheet("background-color: #eee; color: #666; font-size: 10px; text-align: center;")
            thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        thumbnail_label.setFixedSize(160, 90)
        layout.addWidget(thumbnail_label)
        
        # Video information
        info_layout = QVBoxLayout()
        title_label = QLabel(template.get("title", "No title"))
        title_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(title_label)
        layout.addLayout(info_layout, 1)
        
        # Control buttons
        buttons_layout = QVBoxLayout()
        
        # Play button
        play_button = QPushButton("Play")
        play_button.setFixedWidth(80)
        play_button.clicked.connect(self.play_video)
        buttons_layout.addWidget(play_button)
        
        # Overlay subtitle button
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
        
        self.setWindowTitle("YouTube Subtitle Application")
        self.setGeometry(100, 100, 800, 600)
        
        # Video download folder
        self.download_folder = os.path.join("src", "downloads")
        os.makedirs(self.download_folder, exist_ok=True)
        
        # Main widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        
        # URL input section
        url_layout = QHBoxLayout()
        url_label = QLabel("YouTube URL:")
        
        # Replace QLineEdit with QTextEdit for multiple URLs
        self.url_input = QTextEdit()
        self.url_input.setPlaceholderText("Enter YouTube video URLs (one per line)")
        self.url_input.setFixedHeight(80)  # Limit height
        
        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self.download_videos)
        
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input, 1)
        url_layout.addWidget(self.download_button)
        
        main_layout.addLayout(url_layout)
        
        # Progress bar and status label
        progress_layout = QVBoxLayout()
        
        self.status_label = QLabel("Ready to download")
        progress_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)
        
        main_layout.addLayout(progress_layout)
        
        # Downloaded videos list and delete all button
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("<h3>Downloaded Videos</h3>"))
        
        # Add Delete All button
        self.delete_all_button = QPushButton("Delete All")
        self.delete_all_button.setStyleSheet("background-color: #f44336; color: white;")
        self.delete_all_button.clicked.connect(self.delete_all_videos)
        header_layout.addWidget(self.delete_all_button, alignment=Qt.AlignmentFlag.AlignRight)
        
        main_layout.addLayout(header_layout)
        
        self.video_list = QListWidget()
        self.video_list.setStyleSheet("QListWidget::item { border-bottom: 1px solid #ddd; }")
        main_layout.addWidget(self.video_list)
        
        # Load video list
        self.load_videos()
    
    def load_videos(self):
        self.video_list.clear()
        try:
            videos = get_all_videos()
            
            if not videos:
                empty_item = QListWidgetItem("No videos downloaded yet")
                empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.video_list.addItem(empty_item)
                return
            
            for video in videos:
                try:
                    # Create dictionary with fixed keys (column order in database)
                    # video is a tuple with order (id, video_id, title, audio_path, subtitle_path, thumbnail_path, download_date)
                    video_dict = {
                        "id": video[0],
                        "video_id": video[1],
                        "title": video[2],
                        "audio_path": video[3],
                        "subtitle_path": video[4],
                        "thumbnail_path": video[5],
                        "download_date": video[6]
                    }
                    
                    # Check required keys
                    required_keys = ["video_id", "title", "audio_path", "subtitle_path", "thumbnail_path", "download_date"]
                    for key in required_keys:
                        if key not in video_dict or video_dict[key] is None:
                            if key in ["subtitle_path", "thumbnail_path"]:
                                video_dict[key] = None
                            else:
                                video_dict[key] = ""
                    
                    # Create ListWidgetItem
                    item = QListWidgetItem()
                    item.setSizeHint(QSize(0, 100))  # Fixed height for each item
                    self.video_list.addItem(item)
                    
                    # Create and assign video widget
                    video_widget = VideoItem(video_dict)
                    self.video_list.setItemWidget(item, video_widget)
                except Exception as e:
                    print(f"Error loading video from database: {str(e)}")
                    continue  # Skip problematic video
        except Exception as e:
            print(f"Error loading video list: {str(e)}")
            self.video_list.addItem("Error loading video list")
    
    def download_videos(self):
        """Download a list of videos from the entered URLs"""
        # Get all URLs from text input, one URL per line
        urls_text = self.url_input.toPlainText().strip()
        if not urls_text:
            QMessageBox.warning(self, "Error", "Please enter at least one YouTube URL")
            return
        
        # Split URLs, remove empty lines and special characters like '@'
        urls = []
        for line in urls_text.split('\n'):
            # Remove leading/trailing spaces and special characters like '@'
            url = line.strip().lstrip('@')
            if url:  # If URL is not empty after stripping
                urls.append(url)
        
        if not urls:
            QMessageBox.warning(self, "Error", "No valid URLs found")
            return
        
        # Check validity of URLs
        invalid_urls = []
        valid_urls = []
        for url in urls:
            video_id = extract_video_id(url)
            if not video_id:
                invalid_urls.append(url)
            else:
                valid_urls.append(url)
        
        if invalid_urls:
            invalid_msg = "\n".join(invalid_urls[:5])
            if len(invalid_urls) > 5:
                invalid_msg += f"\n... and {len(invalid_urls) - 5} more URLs"
            QMessageBox.warning(self, "Invalid URLs", 
                               f"The following URLs are not valid YouTube URLs:\n{invalid_msg}")
        
        if not valid_urls:
            return  # No valid URLs to download
        
        # Ask for confirmation before downloading multiple videos
        if len(valid_urls) > 1:
            confirm = QMessageBox.question(
                self, 
                "Confirm multiple downloads",
                f"Do you want to download {len(valid_urls)} videos?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        
        # Disable download button and show progress bar
        self.download_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        # Create a queue of URLs to download sequentially
        self.urls_queue = valid_urls.copy()
        self.total_videos = len(self.urls_queue)
        self.processed_videos = 0
        
        # Start downloading the first video
        self.download_next_video()
    
    def download_next_video(self):
        """Download the next video in the queue"""
        if not self.urls_queue:
            # All videos completed
            self.on_all_downloads_complete()
            return
        
        # Get the next URL from the queue
        url = self.urls_queue.pop(0)
        self.processed_videos += 1
        
        # Update status
        self.status_label.setText(f"Downloading video {self.processed_videos}/{self.total_videos}: {url}")
        
        # Create and start download thread
        self.download_thread = DownloadThread(url, self.download_folder)
        self.download_thread.download_progress.connect(self.update_progress)
        self.download_thread.download_complete.connect(self.on_single_download_complete)
        self.download_thread.download_error.connect(self.on_download_error)
        self.download_thread.status_update.connect(self.update_status)
        self.download_thread.start()
    
    def on_single_download_complete(self, video_info):
        """Handle when a single video is downloaded successfully"""
        # Save video information to database
        save_video(
            video_info["video_id"],
            video_info["title"],
            video_info["audio_path"],
            video_info["subtitle_path"],
            video_info["thumbnail_path"],
            video_info["download_date"]
        )
        
        # Continue with the next video in the queue
        if self.urls_queue:
            self.download_next_video()
        else:
            self.on_all_downloads_complete()
    
    def on_all_downloads_complete(self):
        """Handle when all videos have been downloaded or processed"""
        # Reload video list
        self.load_videos()
        
        # Reset interface
        self.url_input.clear()
        self.download_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Ready to download")
        
        # Show success message
        QMessageBox.information(self, "Success", f"Successfully downloaded {self.processed_videos} videos!")
    
    def update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def update_status(self, status):
        self.status_label.setText(status)
        print(status)  # Print status to console for debugging
    
    def download_video(self):
        """Legacy method for backward compatibility, calls the new method"""
        self.download_videos()
    
    def on_download_error(self, error_message):
        """Handle errors during video download"""
        # Show detailed error message
        detailed_error = QMessageBox()
        detailed_error.setIcon(QMessageBox.Icon.Critical)
        detailed_error.setWindowTitle("Error")
        detailed_error.setText(f"Could not download video {self.processed_videos}/{self.total_videos}")
        detailed_error.setInformativeText("Please check the URL and try again.")
        detailed_error.setDetailedText(f"Error details:\n{error_message}")
        detailed_error.exec()
        
        # Continue with the next video in the queue if available
        if self.urls_queue:
            self.download_next_video()
        else:
            # If no more videos in the queue, finish the process
            self.on_all_downloads_complete()
    
    def delete_all_videos(self):
        """Delete all downloaded videos and data from database"""
        # Show confirmation dialog
        confirm = QMessageBox.question(
            self, 
            "Confirm deletion",
            "Are you sure you want to delete all videos and downloaded data?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                # Get all file paths from database and delete data
                file_paths = delete_all_videos()
                deleted_count = 0
                
                # Delete files
                for paths in file_paths:
                    audio_path, subtitle_path, thumbnail_path = paths
                    
                    # Delete audio file
                    if audio_path and os.path.exists(audio_path):
                        try:
                            os.remove(audio_path)
                            deleted_count += 1
                        except Exception as e:
                            print(f"Error deleting audio file {audio_path}: {str(e)}")
                    
                    # Delete subtitle file
                    if subtitle_path and os.path.exists(subtitle_path):
                        try:
                            os.remove(subtitle_path)
                            deleted_count += 1
                        except Exception as e:
                            print(f"Error deleting subtitle file {subtitle_path}: {str(e)}")
                    
                    # Delete thumbnail file
                    if thumbnail_path and os.path.exists(thumbnail_path):
                        try:
                            os.remove(thumbnail_path)
                            deleted_count += 1
                        except Exception as e:
                            print(f"Error deleting thumbnail file {thumbnail_path}: {str(e)}")
                
                # Reload video list (will be empty)
                self.load_videos()
                
                # Show success message
                QMessageBox.information(
                    self,
                    "Delete successful",
                    f"Deleted all data and {deleted_count} files."
                )
                
            except Exception as e:
                # Show error message
                QMessageBox.critical(
                    self,
                    "Error deleting",
                    f"An error occurred while deleting data: {str(e)}"
                ) 