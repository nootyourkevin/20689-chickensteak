"""AudioPlayer — PCM 音频播放器。

用法：
    player = AudioPlayer()
    player.play(pcm_bytes)   # 立即返回，后台线程播放
    player.stop()            # 打断当前播放

播放格式：16kHz, 16bit, mono PCM

注：PyAudio 在 play() 时才导入，模块本身不需要预装 pyaudio。
"""

import threading
from PyQt5.QtCore import QObject, pyqtSignal


class AudioPlayer(QObject):
    """播放 PCM 音频。

    play() 启动后台播放线程并立即返回，不阻塞调用线程。
    stop() 打断播放，播放线程立即退出。
    """

    playback_started = pyqtSignal()
    playback_finished = pyqtSignal()
    playback_error = pyqtSignal(str)

    CHUNK = 1024
    CHANNELS = 1
    RATE = 16000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._playing = False
        self._thread: threading.Thread | None = None

    def play(self, audio_bytes: bytes, sample_rate: int = 16000):
        """开始 PCM 播放。启动后台线程，立即返回。"""
        if not audio_bytes:
            self.playback_finished.emit()
            return

        # 打断正在播放的音频
        self.stop()

        self._playing = True
        print(f"[AudioPlayer] 开始播放: {len(audio_bytes)} bytes, 采样率: {sample_rate}Hz")
        self._thread = threading.Thread(
            target=self._play_thread, args=(audio_bytes, sample_rate), daemon=True
        )
        self._thread.start()

    def _play_thread(self, audio_bytes: bytes, sample_rate: int = 16000):
        """后台线程：使用 aplay 命令播放 PCM 数据。"""
        import subprocess
        import tempfile
        import os

        wav_path = None

        try:
            # 创建临时 WAV 文件
            wav_path = tempfile.mktemp(suffix=".wav")

            # 写入 WAV 文件（指定采样率，16bit，mono）
            import wave
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(self.CHANNELS)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(audio_bytes)

            self.playback_started.emit()
            print(f"[AudioPlayer] 使用 paplay 播放: {wav_path} (采样率: {sample_rate}Hz)")

            # 使用 paplay 命令播放（通过 PulseAudio，兼容性好）
            result = subprocess.run(
                ["paplay", wav_path],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                print(f"[AudioPlayer] 播放完成")
            else:
                print(f"[AudioPlayer] 播放失败: {result.stderr}")
                self.playback_error.emit(f"播放失败: {result.stderr}")

        except Exception as e:
            print(f"[AudioPlayer] 播放异常: {e}")
            self.playback_error.emit(f"播放错误: {e}")
        finally:
            # 清理临时文件
            if wav_path and os.path.exists(wav_path):
                os.remove(wav_path)

        self._playing = False
        self.playback_finished.emit()

    def stop(self):
        """立即打断播放。"""
        self._playing = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def is_playing(self) -> bool:
        """是否正在播放。"""
        return self._playing

    def close(self):
        """释放资源。"""
        self.stop()
