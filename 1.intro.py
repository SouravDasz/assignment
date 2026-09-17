import asyncio
import shutil
import subprocess
from pathlib import Path

import edge_tts
import yt_dlp
from faster_whisper import WhisperModel

VIDEO_URL = ""
DOWNLOAD_FOLDER = Path(r"C:\fastapi\downloads")
WHISPER_MODEL = "tiny"
VOICE = "en-US-JennyNeural"


def find_ffmpeg():
    """Return the FFmpeg executable path, including the WinGet install path."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg

    winget_folder = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    matches = sorted(winget_folder.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"))
    return str(matches[0]) if matches else None


def find_existing_media(folder):
    """Reuse the newest downloaded video/audio pair when one exists."""
    videos = sorted(folder.glob("*.video.mp4"), key=lambda item: item.stat().st_mtime, reverse=True)
    for video_path in videos:
        audio_path = video_path.with_name(video_path.name.replace(".video.mp4", ".audio.mp3"))
        if audio_path.exists():
            return video_path, audio_path
    return None


def download_media(url, folder):
    """Download separate video and MP3 audio files from YouTube."""
    if not url:
        raise ValueError("Set VIDEO_URL to a YouTube video URL before running the script")

    folder.mkdir(parents=True, exist_ok=True)
    existing_media = find_existing_media(folder)
    if existing_media:
        print("Using existing local video and audio files.")
        return existing_media

    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError("FFmpeg is required to download and convert the audio to MP3")

    video_options = {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "outtmpl": str(folder / "%(title)s.video.%(ext)s"),
        "noplaylist": True,
    }
    audio_options = {
        "format": "bestaudio[protocol=https]/bestaudio",
        "outtmpl": str(folder / "%(title)s.audio.%(ext)s"),
        "noplaylist": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    try:
        with yt_dlp.YoutubeDL(video_options) as downloader:
            video_info = downloader.extract_info(url, download=True)
            video_path = Path(downloader.prepare_filename(video_info)).with_suffix(".mp4")
        with yt_dlp.YoutubeDL(audio_options) as downloader:
            audio_info = downloader.extract_info(url, download=True)
            audio_path = Path(downloader.prepare_filename(audio_info)).with_suffix(".mp3")
    except yt_dlp.utils.DownloadError as error:
        raise RuntimeError(f"YouTube download failed: {error}") from error

    return video_path, audio_path


def translate_audio(audio_path):
    """Transcribe speech and translate it directly into English."""
    print("Transcribing and translating speech to English...")
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8", cpu_threads=2)
    segments, _ = model.transcribe(str(audio_path), task="translate", vad_filter=True)
    text = " ".join(segment.text.strip() for segment in segments).strip()
    if not text:
        raise RuntimeError("No speech was detected in the source audio")
    return text


async def create_english_audio(text, audio_path):
    """Generate an English MP3 from translated text."""
    english_audio_path = audio_path.with_name(f"{audio_path.stem}.english.mp3")
    await edge_tts.Communicate(text, VOICE).save(str(english_audio_path))
    return english_audio_path


def create_dubbed_video(video_path, english_audio_path):
    """Replace the original audio with the generated English audio."""
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError("FFmpeg is required to create the dubbed video")

    dubbed_path = video_path.with_name(f"{video_path.stem}.dubbed.mp4")
    subprocess.run([
        ffmpeg, "-y", "-i", str(video_path), "-i", str(english_audio_path),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
        "-shortest", str(dubbed_path),
    ], check=True)
    return dubbed_path


def main():
    video_path, audio_path = download_media(VIDEO_URL, DOWNLOAD_FOLDER)
    english_text = translate_audio(audio_path)
    transcript_path = video_path.with_name(f"{video_path.stem}.english.txt")
    transcript_path.write_text(english_text + "\n", encoding="utf-8")
    english_audio_path = asyncio.run(create_english_audio(english_text, audio_path))
    dubbed_path = create_dubbed_video(video_path, english_audio_path)
    print("English transcript:", transcript_path)
    print("English audio:", english_audio_path)
    print("Dubbed video:", dubbed_path)


if __name__ == "__main__":
    main()
