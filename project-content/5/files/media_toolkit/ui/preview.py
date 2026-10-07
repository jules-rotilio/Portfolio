"""Preview widgets for still, animated, audio, and video media."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from PIL import Image
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QImage, QMovie, QPixmap, QResizeEvent
from PySide6.QtCore import QTimer
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from media_toolkit.ui.background import BackgroundCalls
from media_toolkit.media.ffmpeg_tools import FFMPEG_QUIET_ARGS, find_tool
from media_toolkit.core.filesystem import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
from media_toolkit.media.media_info import probe_media


def extract_video_poster(path: Path) -> bytes:
    """Return the first video frame as PNG bytes scaled for the preview pane.

    Runs FFmpeg, so call it off the UI thread. Error messages are written to
    be shown directly in place of the thumbnail.
    """
    try:
        ffmpeg = find_tool("ffmpeg")
    except FileNotFoundError as error:
        raise FileNotFoundError("Install FFmpeg to show a video thumbnail") from error
    try:
        result = subprocess.run(
            [
                ffmpeg,
                *FFMPEG_QUIET_ARGS,
                "-ss",
                "0",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-vf",
                "scale=640:360:force_original_aspect_ratio=decrease",
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "pipe:1",
            ],
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"Could not load video thumbnail: {error}") from error
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError("Video thumbnail is not available")
    return result.stdout


class MediaPreviewWidget(QWidget):
    """Preview images, animated GIFs, video, and audio with media details."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the stacked media viewer and playback controls."""
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.media_stack = QStackedWidget()
        self.image_label = QLabel("Choose a media file to preview")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(240, 200)
        self.image_label.setWordWrap(True)
        self._empty_movie = QMovie(self.image_label)
        self.video_widget = QVideoWidget()
        self.video_poster = QLabel("Video preview unavailable")
        self.video_poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_poster.setMinimumSize(240, 200)
        self.video_stack = QStackedWidget()
        self.video_stack.addWidget(self.video_poster)
        self.video_stack.addWidget(self.video_widget)
        self.audio_label = QLabel("Audio preview")
        self.audio_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.media_stack.addWidget(self.image_label)
        self.media_stack.addWidget(self.video_stack)
        self.media_stack.addWidget(self.audio_label)
        layout.addWidget(self.media_stack, stretch=1)

        controls = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self._toggle_playback)
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.setEnabled(False)
        self.position_slider.sliderMoved.connect(self._seek)
        self.time_label = QLabel("00:00 / 00:00")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setMaximumWidth(100)
        controls.addWidget(self.play_button)
        controls.addWidget(self.position_slider, stretch=1)
        controls.addWidget(self.time_label)
        controls.addWidget(QLabel("Volume"))
        controls.addWidget(self.volume_slider)
        layout.addLayout(controls)

        self.details = QLabel()
        self.details.setWordWrap(True)
        layout.addWidget(self.details)

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.7)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.playbackStateChanged.connect(self._playback_state_changed)
        self.player.errorOccurred.connect(self._playback_error)
        self.volume_slider.valueChanged.connect(self._volume_changed)

        self._pixmap: QPixmap | None = None
        self._video_poster_pixmap: QPixmap | None = None
        self._movie: QMovie | None = None
        self._animated_webp: Image.Image | None = None
        self._animated_webp_frame = 0
        self._animated_webp_frame_count = 0
        self._animated_webp_timer = QTimer(self)
        self._animated_webp_timer.timeout.connect(self._show_next_webp_frame)
        self._duration = 0
        self._video_loaded = False
        self._details_text = ""
        self._playback_error_text = ""
        self._background = BackgroundCalls(self)

    def clear_preview(self) -> None:
        """Stop playback and reset the widget to its empty "pick a file" state."""
        self._background.cancel_all()
        self.player.stop()
        self.player.setSource(QUrl())
        self._video_loaded = False
        if self._movie is not None:
            self._movie.stop()
            self._movie = None
        self._animated_webp_timer.stop()
        if self._animated_webp is not None:
            self._animated_webp.close()
            self._animated_webp = None
        self._animated_webp_frame = 0
        self._animated_webp_frame_count = 0
        self._pixmap = None
        self._video_poster_pixmap = None
        self.video_poster.clear()
        self.video_poster.setText("Video preview unavailable")
        self.video_stack.setCurrentWidget(self.video_poster)
        self.image_label.setMovie(self._empty_movie)
        self.image_label.clear()
        self.image_label.setText("Choose a media file to preview")
        self.media_stack.setCurrentWidget(self.image_label)
        self._details_text = ""
        self._playback_error_text = ""
        self.details.clear()
        self.play_button.setText("Play")
        self.play_button.setEnabled(False)
        self.position_slider.setRange(0, 0)
        self.position_slider.setEnabled(False)
        self.time_label.setText("00:00 / 00:00")
        self._duration = 0

    def show_file(self, path: Path, metadata: dict[str, Any] | None = None) -> None:
        """Display a file and populate detailed metadata for the selected media."""
        self.clear_preview()
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            self._video_loaded = True
            self.media_stack.setCurrentWidget(self.video_stack)
            self._load_player(path)
            self._load_video_poster(path)
        elif path.suffix.lower() in AUDIO_EXTENSIONS:
            self.audio_label.setText(path.name)
            self.media_stack.setCurrentWidget(self.audio_label)
            self._load_player(path)
        else:
            self._show_image(path)

        if metadata is not None and "details" in metadata:
            self._set_details("\n".join(metadata["details"]))
        elif metadata is not None and "error" in metadata:
            self._show_details_error(path, metadata["error"])
        else:
            # Unindexed files are probed with ffprobe, which can take seconds.
            self._set_details("Reading media details…")
            self._background.submit(
                "details",
                lambda: probe_media(path),
                lambda details: self._set_details("\n".join(details)),
                lambda error: self._show_details_error(path, error),
            )

    def _set_details(self, text: str) -> None:
        """Show media details followed by any playback error."""
        self._details_text = text
        lines = [line for line in (text, self._playback_error_text) if line]
        self.details.setText("\n".join(lines))

    def _show_details_error(self, path: Path, error: object) -> None:
        """Explain why details are unavailable, keeping the file size visible."""
        self._set_details(
            f"Media details unavailable: {error}\n"
            f"File size: {self._file_size(path)}"
        )

    def _show_image(self, path: Path) -> None:
        """Render a still image or animated image sample in the preview stack."""
        if path.suffix.lower() == ".webp":
            try:
                animation = Image.open(path)
                if getattr(animation, "n_frames", 1) > 1:
                    self._animated_webp = animation
                    self._animated_webp_frame_count = animation.n_frames
                    self._show_next_webp_frame()
                    self.media_stack.setCurrentWidget(self.image_label)
                    return
                animation.close()
            except (OSError, ValueError, Image.DecompressionBombError):
                pass

        if path.suffix.lower() == ".gif":
            movie = QMovie(str(path))
            if movie.isValid():
                self._movie = movie
                self.image_label.setMovie(movie)
                movie.frameChanged.connect(self._update_movie_size)
                self.media_stack.setCurrentWidget(self.image_label)
                movie.start()
                self._update_movie_size()
                return

        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            self._pixmap = pixmap
            self.media_stack.setCurrentWidget(self.image_label)
            self._update_pixmap_size()
            return

        self.image_label.setText("Image preview is not available for this file")
        self.media_stack.setCurrentWidget(self.image_label)

    def _show_next_webp_frame(self) -> None:
        """Advance the animated WebP frame timer using the image's own timing metadata."""
        if self._animated_webp is None or self._animated_webp_frame_count < 2:
            return
        try:
            self._animated_webp.seek(self._animated_webp_frame)
            frame = self._animated_webp.convert("RGBA")
            image = QImage(
                frame.tobytes(),
                frame.width,
                frame.height,
                frame.width * 4,
                QImage.Format.Format_RGBA8888,
            ).copy()
            duration = max(
                20,
                int(
                    self._animated_webp.info.get(
                        "duration", self._animated_webp.info.get("default_image_duration", 100)
                    )
                ),
            )
        except (OSError, ValueError, EOFError):
            self._animated_webp_timer.stop()
            self.image_label.setText("Animated WebP preview is not available")
            return
        self._pixmap = QPixmap.fromImage(image)
        self._update_pixmap_size()
        self._animated_webp_frame = (
            self._animated_webp_frame + 1
        ) % self._animated_webp_frame_count
        # WebP frame delays are stored in the image metadata, so the timer must
        # be restarted after each frame to keep playback smooth and in sync.
        self._animated_webp_timer.start(duration)

    def _load_player(self, path: Path) -> None:
        """Attach a QMediaPlayer to this file and enable playback controls."""
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.play_button.setEnabled(True)
        self.position_slider.setEnabled(True)

    def _load_video_poster(self, path: Path) -> None:
        """Extract the first-frame thumbnail in the background."""
        self.video_poster.setText("Loading video thumbnail…")
        self._background.submit(
            "poster",
            lambda: extract_video_poster(path),
            self._show_video_poster,
            lambda error: self.video_poster.setText(str(error)),
        )

    def _show_video_poster(self, png_data: bytes) -> None:
        """Set the thumbnail without switching away from video already playing."""
        image = QImage.fromData(png_data, "PNG")
        if image.isNull():
            self.video_poster.setText("Video thumbnail is not available")
            return
        self._video_poster_pixmap = QPixmap.fromImage(image)
        self._update_video_poster_size()

    def _update_video_poster_size(self) -> None:
        if self._video_poster_pixmap is None:
            return
        self.video_poster.setPixmap(
            self._video_poster_pixmap.scaled(
                self.video_poster.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _toggle_playback(self) -> None:
        """Play or pause the active source while respecting the current media stack."""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if self._video_loaded:
                self.video_stack.setCurrentWidget(self.video_widget)
            self.player.play()

    def _volume_changed(self, value: int) -> None:
        self.audio_output.setVolume(value / 100)

    def _playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        """Keep the button label in sync with the underlying media state."""
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setText("Pause" if playing else "Play")

    def _playback_error(
        self, error: QMediaPlayer.Error, error_string: str
    ) -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        if error_string:
            # Kept separately so details arriving later do not overwrite it.
            self._playback_error_text = f"Playback error: {error_string}"
            self._set_details(self._details_text)

    def _seek(self, position: int) -> None:
        self.player.setPosition(position)

    def _position_changed(self, position: int) -> None:
        self.position_slider.setValue(position)
        self._update_time_label(position, self._duration)

    def _duration_changed(self, duration: int) -> None:
        self._duration = duration
        self.position_slider.setRange(0, duration)
        self._update_time_label(self.player.position(), duration)

    def _update_time_label(self, position: int, duration: int) -> None:
        self.time_label.setText(
            f"{self._format_time(position)} / {self._format_time(duration)}"
        )

    @staticmethod
    def _format_time(milliseconds: int) -> str:
        seconds = max(0, milliseconds // 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02}:{minutes:02}:{seconds:02}"
        return f"{minutes:02}:{seconds:02}"

    @staticmethod
    def _file_size(path: Path) -> str:
        try:
            return f"{path.stat().st_size:,} bytes"
        except OSError as error:
            return f"Unavailable ({error})"

    def _update_pixmap_size(self) -> None:
        if self._pixmap is None:
            return
        self.image_label.setPixmap(
            self._pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _update_movie_size(self) -> None:
        if self._movie is None:
            return
        frame_size = self._movie.frameRect().size()
        if frame_size.width() <= 0 or frame_size.height() <= 0:
            return
        self._movie.setScaledSize(
            frame_size.scaled(
                self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio
            )
        )

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Resize the visible image or poster while preserving the original aspect ratio."""
        super().resizeEvent(event)
        if self._movie is not None:
            self._update_movie_size()
        else:
            self._update_pixmap_size()
        self._update_video_poster_size()
