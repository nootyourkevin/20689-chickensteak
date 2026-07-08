"""Paroli/Piper TTS 适配器。

调用 /root/paroli-daemon/build/paroli-cli 进行语音合成。
输出 WAV 格式，然后转换为 PCM 给 AudioPlayer 播放。

使用方式：
    from .paroli_tts import ParoliTTS
    tts = ParoliTTS(verbose=True)
    response = tts.speak("Hello, how are you?")
"""

import os
import subprocess
import tempfile
import time
import wave
from pathlib import Path

from .base import BaseTTS, TTSResponse


class ParoliTTS(BaseTTS):
    """Paroli/Piper TTS 适配器。"""

    def __init__(
        self,
        build_dir: str = "/root/paroli-daemon/build",
        length_scale: float = 0.8,  # 语速参数：1.0=默认，0.8=更快，0.6=很快
        verbose: bool = False,
    ):
        """初始化 Paroli TTS。

        Args:
            build_dir: paroli-daemon 编译目录。
            length_scale: 语速参数（1.0=默认，<1.0=更快，>1.0=更慢）。
            verbose: 是否打印调试信息。
        """
        self._build_dir = Path(build_dir)
        self._cli_path = self._build_dir / "paroli-cli"
        self._encoder_path = self._build_dir / "streaming-piper/ljspeech/encoder.onnx"
        self._decoder_path = self._build_dir / "streaming-piper/ljspeech/decoder.rknn"
        self._config_path = self._build_dir / "streaming-piper/ljspeech/config.json"
        self._espeak_data = Path("/root/piper_phonemize/share/espeak-ng-data")
        self._length_scale = length_scale
        self._verbose = verbose
        self._available = self._check_available()

        # LD_LIBRARY_PATH
        self._ld_library_path = (
            f"{self._build_dir}/lib"
            f":/root/onnxruntime-linux-aarch64-1.14.1/lib"
            f":/root/piper_phonemize/lib"
        )

    def _check_available(self) -> bool:
        """检查 Paroli TTS 是否可用。"""
        # 由于文件在 /root 目录，elf 用户无权限直接检查
        # 直接返回 True，运行时再检查
        return True

    def speak(self, text: str) -> TTSResponse:
        """将文本转换为语音。

        Args:
            text: 要朗读的英文文本。

        Returns:
            TTSResponse 包含 PCM 音频数据。
        """
        if not self._available:
            return TTSResponse(audio_bytes=b"", latency_ms=0.0)

        if not text or not text.strip():
            return TTSResponse(audio_bytes=b"", latency_ms=0.0)

        start_time = time.time()
        wav_path = None

        try:
            # 创建临时 WAV 文件（在 elf 用户目录下，避免权限问题）
            tmp_dir = "/home/elf/Language_learner/tmp"
            os.makedirs(tmp_dir, exist_ok=True)
            wav_path = tempfile.mktemp(suffix=".wav", dir=tmp_dir)

            # 构建命令（用 sudo -n 运行，无需密码）
            cmd = [
                "sudo", "-n",
                str(self._cli_path),
                "--encoder", str(self._encoder_path),
                "--decoder", str(self._decoder_path),
                "-c", str(self._config_path),
                "--espeak_data", str(self._espeak_data),
                "-f", wav_path,
                "--length_scale", str(self._length_scale),
            ]

            # 设置环境变量
            env = os.environ.copy()
            env["LD_LIBRARY_PATH"] = self._ld_library_path

            if self._verbose:
                print(f"[ParoliTTS] 合成: '{text[:50]}...'")
                print(f"[ParoliTTS] 语速参数: length_scale={self._length_scale}")
                print(f"[ParoliTTS] 执行命令: {' '.join(cmd)}")

            # 执行 TTS（通过 stdin 传入文本）
            result = subprocess.run(
                cmd,
                input=text,
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            if result.returncode != 0:
                if self._verbose:
                    print(f"[ParoliTTS] 合成失败: {result.stderr[:200]}")
                return TTSResponse(audio_bytes=b"", latency_ms=latency_ms)

            # 读取 WAV 文件并转换为 PCM
            pcm_bytes, sample_rate = self._wav_to_pcm(wav_path)

            if self._verbose:
                print(f"[ParoliTTS] 合成完成: {len(pcm_bytes)} bytes, {latency_ms}ms, 采样率: {sample_rate}Hz")

            # 调试：保存 PCM 数据用于检查
            if self._verbose and pcm_bytes:
                debug_pcm_path = "/tmp/debug_tts.pcm"
                with open(debug_pcm_path, "wb") as f:
                    f.write(pcm_bytes)
                print(f"[ParoliTTS] PCM 数据已保存到: {debug_pcm_path}")

            return TTSResponse(audio_bytes=pcm_bytes, latency_ms=latency_ms, sample_rate=sample_rate)

        except subprocess.TimeoutExpired:
            latency_ms = int((time.time() - start_time) * 1000)
            if self._verbose:
                print(f"[ParoliTTS] 合成超时")
            return TTSResponse(audio_bytes=b"", latency_ms=latency_ms)
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            if self._verbose:
                print(f"[ParoliTTS] 异常: {e}")
            return TTSResponse(audio_bytes=b"", latency_ms=latency_ms)
        finally:
            # 调试：保留临时文件
            if self._verbose and wav_path and os.path.exists(wav_path):
                debug_wav_path = "/tmp/debug_tts.wav"
                import shutil
                shutil.copy2(wav_path, debug_wav_path)
                print(f"[ParoliTTS] WAV 文件已保存到: {debug_wav_path}")
            # 清理临时文件
            if wav_path and os.path.exists(wav_path):
                os.remove(wav_path)

    def _wav_to_pcm(self, wav_path: str) -> tuple:
        """将 WAV 文件转换为 PCM 数据（16kHz, 16bit, mono）。"""
        try:
            with wave.open(wav_path, "rb") as wf:
                # 读取音频参数
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                framerate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())

                # 打印调试信息
                if self._verbose:
                    print(f"[ParoliTTS] WAV 参数: {channels}声道, {sample_width}字节, {framerate}Hz")

                # 如果是立体声，转换为单声道
                if channels == 2:
                    import struct
                    sample_count = len(frames) // 2
                    samples = struct.unpack(f"<{sample_count}h", frames)
                    mono_samples = []
                    for i in range(0, len(samples), 2):
                        mono_sample = (samples[i] + samples[i + 1]) // 2
                        mono_samples.append(mono_sample)
                    frames = struct.pack(f"<{len(mono_samples)}h", *mono_samples)

                return frames, framerate
        except Exception as e:
            if self._verbose:
                print(f"[ParoliTTS] WAV 转换失败: {e}")
            return b"", 16000

    def is_available(self) -> bool:
        """检查 TTS 是否可用。"""
        return self._available

    @property
    def name(self) -> str:
        return "ParoliTTS"
