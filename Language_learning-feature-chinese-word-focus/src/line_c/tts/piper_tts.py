"""Piper TTS 适配器 — 本地离线语音合成。

使用 piper-tts 库，基于 ONNX 模型推理。
适合嵌入式设备（RK3588），无需联网。

安装：
    pip install piper-tts

模型下载（放到 models/piper/ 目录）：
    wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx
    wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json
"""

import io
import wave
from pathlib import Path
from typing import Optional

from .base import BaseTTS, TTSResponse


class PiperTTS(BaseTTS):
    """Piper 本地 TTS 适配器。"""

    def __init__(
        self,
        model_path: Optional[str] = None,
        speaker_id: Optional[int] = None,
        sample_rate: int = 22050,
        verbose: bool = False,
    ):
        """初始化 Piper TTS。

        Args:
            model_path: ONNX 模型文件路径。如果为 None，使用默认路径。
            speaker_id: 说话人 ID（多说话人模型用）。
            sample_rate: 采样率（模型默认即可）。
            verbose: 是否打印调试信息。
        """
        self._verbose = verbose
        self._speaker_id = speaker_id
        self._sample_rate = sample_rate
        self._model = None
        self._model_path = model_path or self._find_default_model()

        # 尝试加载模型
        self._load_model()

    def _find_default_model(self) -> Optional[str]:
        """查找默认模型路径。"""
        # 按优先级搜索
        search_paths = [
            Path(__file__).parent.parent.parent.parent / "models" / "piper",
            Path.home() / "models" / "piper",
            Path("/home/elf/models/piper"),
            Path("/opt/piper/models"),
        ]

        for base_dir in search_paths:
            if not base_dir.exists():
                continue
            # 查找 .onnx 文件
            for onnx_file in base_dir.glob("*.onnx"):
                if self._verbose:
                    print(f"[PiperTTS] 找到模型: {onnx_file}")
                return str(onnx_file)

        return None

    def _load_model(self):
        """加载 Piper 模型。"""
        if not self._model_path:
            if self._verbose:
                print("[PiperTTS] 未找到模型文件，TTS 不可用")
            return

        try:
            from piper import PiperVoice

            self._model = PiperVoice.load(self._model_path)
            if self._verbose:
                print(f"[PiperTTS] 模型已加载: {self._model_path}")
        except ImportError:
            if self._verbose:
                print("[PiperTTS] piper-tts 未安装，请运行: pip install piper-tts")
        except Exception as e:
            if self._verbose:
                print(f"[PiperTTS] 模型加载失败: {e}")

    def speak(self, text: str) -> TTSResponse:
        """将文本转换为语音。

        Args:
            text: 要朗读的文本。

        Returns:
            TTSResponse 包含 PCM 音频数据。
        """
        if not self._model:
            return TTSResponse(
                audio_bytes=b"",
                format="pcm",
                latency_ms=0,
                error="Piper TTS 未初始化",
            )

        if not text.strip():
            return TTSResponse(
                audio_bytes=b"",
                format="pcm",
                latency_ms=0,
            )

        import time
        start_time = time.time()

        try:
            # 使用 Piper 合成语音
            wav_buffer = io.BytesIO()
            self._model.synthesize(text, wav_buffer)

            # 转换为 PCM 格式
            wav_buffer.seek(0)
            pcm_data = self._wav_to_pcm(wav_buffer)

            latency_ms = int((time.time() - start_time) * 1000)

            if self._verbose:
                print(f"[PiperTTS] 合成完成: {len(text)} 字符, {len(pcm_data)} 字节, {latency_ms}ms")

            return TTSResponse(
                audio_bytes=pcm_data,
                format="pcm",
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            if self._verbose:
                print(f"[PiperTTS] 合成失败: {e}")
            return TTSResponse(
                audio_bytes=b"",
                format="pcm",
                latency_ms=latency_ms,
                error=str(e),
            )

    def _wav_to_pcm(self, wav_buffer: io.BytesIO) -> bytes:
        """将 WAV 转换为原始 PCM 数据。"""
        try:
            with wave.open(wav_buffer, "rb") as wf:
                # 读取所有帧
                pcm_data = wf.readframes(wf.getnframes())
                return pcm_data
        except Exception:
            # 如果不是标准 WAV，直接返回
            wav_buffer.seek(0)
            return wav_buffer.read()

    def is_available(self) -> bool:
        """检查 TTS 是否可用。"""
        return self._model is not None
