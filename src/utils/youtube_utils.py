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
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from datetime import datetime
import yt_dlp # Make sure to import yt_dlp at the beginning of the file

# Try importing translation library
try:
    import translators as ts
    TRANSLATORS_AVAILABLE = True
except ImportError:
    TRANSLATORS_AVAILABLE = False
    print("WARNING: The 'translators' library is not installed. Automatic subtitles translation will not work.")
    print("Run 'pip install translators' to install it.")

# --- Custom Exception ---
class NoEnglishTranscriptError(Exception):
    """Error thrown when English subtitles are not found."""
    pass

# Backup download method using yt-dlp
def download_with_ytdlp(url, video_id, download_folder, safe_title):
    """Download audio from YouTube using yt-dlp (backup method)"""
    print("Using yt-dlp to download video...")
    
    try:
        import yt_dlp
    except ImportError:
        print("The yt-dlp library not found. Please install it using: pip install yt-dlp")
        raise ValueError("The yt-dlp library is not installed")
    
    # Temporary file path
    temp_dir = tempfile.mkdtemp()
    
    # Options for yt-dlp
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': False,
        'ffmpeg_location': r'D:\OverlaySubtitles\FFMPEG',
    }
    
    abs_audio_path = None
    rel_audio_path = None
    title = None
    
    try:
        # Download video using yt-dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Unknown Title')
            downloaded_file = ydl.prepare_filename(info)
            
            # Create target filename
            audio_file = f"{safe_title}_{video_id}.mp4"
            abs_audio_path = os.path.join(download_folder, audio_file)
            rel_audio_path = os.path.join("src", "downloads", audio_file)
            
            # Move file from temporary directory to target directory
            shutil.move(downloaded_file, abs_audio_path)
            print(f"Successfully downloaded audio using yt-dlp: {abs_audio_path}")
    
    except Exception as e:
        print(f"Error when using yt-dlp: {str(e)}")
        raise ValueError(f"Cannot download video using yt-dlp: {str(e)}")
    
    finally:
        # Remove temporary directory
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
    
    return abs_audio_path, rel_audio_path, title

def extract_video_id(url):
    """Extract video ID from YouTube URL"""
    # Support various YouTube URL formats
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',  # Standard format v=ID or /ID
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',  # Short format youtu.be/ID
        r'(?:embed\/)([0-9A-Za-z_-]{11})',  # Embed format
        r'(?:shorts\/)([0-9A-Za-z_-]{11})'  # YouTube Shorts format
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def download_audio(url, download_folder, video_id, status_callback=None):
    if status_callback: status_callback("Preparing to download audio...")
    
    # Progress callback for detailed monitoring
    def progress_hook(d):
        if status_callback and d['status'] == 'downloading':
            if '_percent_str' in d and '_speed_str' in d:
                status_callback(f"Downloading audio: {d['_percent_str']} ({d['_speed_str']})")
        elif status_callback and d['status'] == 'finished':
            status_callback(f"Download complete, processing audio...")
    
    # Post-processor callback to monitor conversion process
    def postprocessor_hook(d):
        if status_callback:
            if d['status'] == 'started':
                status_callback(f"Processing audio... {d.get('postprocessor', '')}")
            elif d['status'] == 'finished':
                status_callback(f"Audio processing complete")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(download_folder, f'YouTube_Audio_{video_id}.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3', # or 'wav', 'm4a' as needed
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [progress_hook],
        'postprocessor_hooks': [postprocessor_hook],
        'nocheckcertificate': True, # Skip SSL certificate check if needed
        'http_chunk_size': 10485760 # Increase chunk size for downloads
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if status_callback: status_callback("Starting audio download...")
            info = ydl.extract_info(url, download=True)
            downloaded_path = ydl.prepare_filename(info)
            # yt-dlp automatically adds codec extension, we need to get the exact path after processing
            base, _ = os.path.splitext(downloaded_path)
            final_audio_path = base + '.mp3' # Must match preferredcodec
            
            if not os.path.exists(final_audio_path):
                 # Sometimes the actual file name may be slightly different, look for an mp3 file matching video_id
                 found = False
                 for f in os.listdir(download_folder):
                      if f.startswith(f'YouTube_Audio_{video_id}') and f.endswith('.mp3'):
                           final_audio_path = os.path.join(download_folder, f)
                           found = True
                           break
                 if not found:
                    raise FileNotFoundError(f"MP3 audio file not found after download: {final_audio_path}")

            if status_callback: status_callback("Audio download and processing complete.")
            print(f"Audio downloaded to: {final_audio_path}")
            return final_audio_path, info.get('title', f'Video_{video_id}') # Return title too
            
    except yt_dlp.utils.DownloadError as e:
        # Print more detailed error
        print(f"yt-dlp download error: {e}")
        if "certificate verify failed" in str(e):
             if status_callback: status_callback("SSL error when downloading audio. Try again or check network/Python settings.")
        elif "HTTP Error 403" in str(e):
             if status_callback: status_callback("HTTP Error 403 (Forbidden). Video might be restricted.")
        else:
             if status_callback: status_callback(f"Unidentified error when downloading audio: {e}")
        raise # Throw error again for main thread to handle
    except Exception as e:
        print(f"Unexpected error during audio download: {e}")
        if status_callback: status_callback(f"Unexpected error when downloading audio: {e}")
        raise

def download_subtitles(video_id, download_folder, title, status_callback=None):
    if status_callback: status_callback("Searching for automatic English subtitles...")
    subtitles_data_fetched = None
    transcript = None
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        try:
            transcript = transcript_list.find_generated_transcript(['en'])
            print("Found automatic English subtitles.")
            if status_callback: status_callback("Found automatic English subtitles.")
        except NoTranscriptFound:
            print("No AUTOMATIC English subtitles found. This video will be skipped.")
            if status_callback: status_callback("No automatic English subtitles found.")
            raise NoEnglishTranscriptError(f"Video {video_id} doesn't have automatic English subtitles.")
        
        subtitles_data_fetched = transcript.fetch()
        if status_callback: status_callback("Successfully loaded subtitle data.")

    except TranscriptsDisabled:
         print(f"Subtitles are disabled for video {video_id}.")
         raise NoEnglishTranscriptError(f"Subtitles are disabled for video {video_id}.")
    except NoEnglishTranscriptError:
         raise
    except Exception as e:
         print(f"API error when getting subtitles for {video_id}: {e}")
         raise NoEnglishTranscriptError(f"Error when getting subtitles for video {video_id}: {e}")

    if subtitles_data_fetched:
        subtitles_data_processed = []

        if TRANSLATORS_AVAILABLE:
            if status_callback: status_callback("Translating subtitles (may take a few minutes)...")
            print("Starting to translate subtitles to Vietnamese...")
            translated_count = 0
            errors = []
            total_subs = len(subtitles_data_fetched)
            
            for i, sub_obj in enumerate(subtitles_data_fetched):
                # Update translation progress by count
                if status_callback and i % 10 == 0:  # Update every 10 sentences to avoid too many updates
                    percent_done = min(100, int((i / total_subs) * 100))
                    status_callback(f"Translating subtitles: {percent_done}% ({i}/{total_subs})")
                
                # Create dictionary from object's direct properties
                sub_dict = {
                    'text': sub_obj.text,
                    'start': sub_obj.start,
                    'duration': sub_obj.duration
                }
                
                en_text = sub_dict['text']
                if en_text: 
                    try:
                        vi_text = ts.translate_text(en_text, translator='google', from_language='en', to_language='vi')
                        sub_dict["vi_text"] = vi_text
                        translated_count += 1
                    except Exception as e:
                        error_msg = f"Error translating subtitle {i+1}: {str(e)}"
                        print(error_msg)
                        errors.append(error_msg)
                        sub_dict["vi_text"] = ""
                else:
                     sub_dict["vi_text"] = ""
                     
                subtitles_data_processed.append(sub_dict)
            
            print(f"Translation complete. {translated_count} sentences were translated.")
            if errors: print(f"There were {len(errors)} errors during translation.")
            if status_callback: status_callback(f"Subtitle translation complete. Translated {translated_count}/{total_subs} sentences.")
        else:
            if status_callback: status_callback("Skipping translation because the library is not installed.")
            for sub_obj in subtitles_data_fetched:
                 sub_dict = {
                    'text': sub_obj.text,
                    'start': sub_obj.start,
                    'duration': sub_obj.duration,
                    'vi_text': ''
                 }
                 subtitles_data_processed.append(sub_dict)

        safe_title = sanitize_filename(title)
        subtitle_filename = f"{safe_title}_{video_id}.json"
        subtitle_path = os.path.join(download_folder, subtitle_filename)
        try:
            with open(subtitle_path, 'w', encoding='utf-8') as f:
                json.dump(subtitles_data_processed, f, ensure_ascii=False, indent=4)
            if status_callback: status_callback("Saving subtitles complete.")
            print(f"Subtitles saved to: {subtitle_path}")
            return subtitle_path
        except Exception as e:
            print(f"Error when saving JSON subtitle file: {e}")
            if status_callback: status_callback(f"Error saving subtitle file: {e}")
            raise IOError(f"Error when saving subtitle file: {e}")
    else:
        print(f"No subtitle data to process for {video_id} despite no prior errors.")
        raise NoEnglishTranscriptError(f"Logic error: no subtitle data for {video_id}.")

def download_thumbnail(video_id, download_folder, status_callback=None):
    if status_callback: status_callback("Downloading thumbnail image...")
    thumbnail_path = None
    try:
        # Get highest quality thumbnail
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

        # Create filename
        thumbnail_filename = f"YouTube_Thumbnail_{video_id}.jpg"
        thumbnail_path = os.path.join(download_folder, thumbnail_filename)
        
        # Download image with progress tracking
        response = requests.get(thumbnail_url, stream=True, timeout=10)
        response.raise_for_status()
        
        # Get file size if available
        content_length = response.headers.get('content-length')
        if content_length:
            content_length = int(content_length)
            downloaded = 0
            
            with open(thumbnail_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if status_callback and content_length > 0:
                        percent = int((downloaded / content_length) * 100)
                        if percent % 20 == 0:  # Update every 20%
                            status_callback(f"Downloading thumbnail: {percent}%")
        else:
            # If content-length is not available
            with open(thumbnail_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

        if status_callback: status_callback("Thumbnail download complete.")
        print(f"Thumbnail saved to: {thumbnail_path}")
        return thumbnail_path

    except requests.exceptions.RequestException as e:
        print(f"Network error when downloading thumbnail: {e}")
        # Try fallback to default thumbnail if error
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/default.jpg"
        try:
            response = requests.get(thumbnail_url, stream=True, timeout=5)
            response.raise_for_status()
            thumbnail_filename = f"YouTube_Thumbnail_{video_id}_default.jpg"
            thumbnail_path = os.path.join(download_folder, thumbnail_filename)
            with open(thumbnail_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            if status_callback: status_callback("Default thumbnail downloaded.")
            print(f"Default thumbnail saved to: {thumbnail_path}")
            return thumbnail_path
        except requests.exceptions.RequestException as e2:
             print(f"Network error when downloading default thumbnail: {e2}")
             if status_callback: status_callback(f"Error downloading thumbnail: {e}")
             return None
    except Exception as e:
        print(f"Unexpected error when downloading thumbnail: {e}")
        if status_callback: status_callback(f"Error downloading thumbnail: {e}")
        return None

def download_youtube_video(url, download_folder, status_callback=None):
    """Download audio, subtitles (with translation if possible), and thumbnail for YouTube video."""
    video_id = extract_video_id(url) # Get video_id first for use in filenames
    if not video_id:
        raise ValueError("Could not extract Video ID from URL.")
        
    print(f"Processing video ID: {video_id}")

    title = None # Will get title from yt-dlp later
    audio_path = None
    subtitle_path = None
    thumbnail_path = None

    try:
        # 1. Download Audio and get Title from yt-dlp
        if status_callback: status_callback("Preparing to download audio and get information...")
        
        # Options to get info without downloading again if the file already exists? (Difficult with yt-dlp)
        # For now, just download audio again
        
        audio_path, title = download_audio(url, download_folder, video_id, status_callback)
        
        if not audio_path or not title:
             raise Exception("Audio download or title retrieval failed.")

        # 2. Download Subtitles (and translate if possible) - Use retrieved video_id and title
        subtitle_path = download_subtitles(video_id, download_folder, title, status_callback)
        
        # 3. Download Thumbnail - Use video_id
        thumbnail_path = download_thumbnail(video_id, download_folder, status_callback)

        download_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        video_info = {
            "video_id": video_id,
            "title": title,
            "audio_path": audio_path,
            "subtitle_path": subtitle_path, 
            "thumbnail_path": thumbnail_path,
            "download_date": download_date
        }
        
        if status_callback: status_callback("Download completed!")
        return video_info

    except NoEnglishTranscriptError as e:
        print(f"Cancelling download for video {video_id}: {e}")
        # Delete downloaded audio file (if exists)
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                print(f"Deleted temporary audio file: {audio_path}")
            except OSError as rm_err:
                print(f"Error when deleting temporary audio file {audio_path}: {rm_err}")
        # Throw error again with message for user
        raise Exception(f"Video does not have English subtitles so it was skipped.") from e

    except Exception as e:
        print(f"Unexpected error during video processing ({video_id}): {e}")
        # Try to delete audio if other errors occur after audio download
        if audio_path and os.path.exists(audio_path):
             try:
                  os.remove(audio_path)
                  print(f"Deleted temporary audio file due to other error: {audio_path}")
             except OSError as rm_err:
                  print(f"Error when deleting temporary audio file {audio_path}: {rm_err}")
        if status_callback: status_callback(f"Error: {e}")
        # Throw original error for DownloadThread to display details
        raise e

def sanitize_filename(filename):
    # ... (keep this function unchanged) ...
    return "".join(c for c in filename if c.isalnum() or c in (' ', '.', '_')).rstrip() 