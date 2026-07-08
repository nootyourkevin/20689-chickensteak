"""SenseVoice RKNN ASR 适配器。

调用 /home/elf/SenseVoiceSmall-RKNN2/sensevoice_rknn.py 进行语音识别。
需要单声道 16kHz WAV 格式。

使用方式：
    from .sensevoice_asr import SenseVoiceASR
    asr = SenseVoiceASR()
    result = asr.transcribe(audio_bytes)
"""

import os
import re
import subprocess
import tempfile
import time
import wave
from pathlib import Path

from .base import BaseASR, ASRResponse


class SenseVoiceASR(BaseASR):
    """SenseVoice RKNN ASR 适配器。"""

    def __init__(
        self,
        model_dir: str = "/home/elf/SenseVoiceSmall-RKNN2",
        script_name: str = "sensevoice_rknn.py",
        verbose: bool = False,
    ):
        """初始化 SenseVoice ASR。

        Args:
            model_dir: SenseVoice 模型目录路径。
            script_name: 脚本文件名。
            verbose: 是否打印调试信息。
        """
        self._model_dir = Path(model_dir)
        self._script_path = self._model_dir / script_name
        self._verbose = verbose
        self._available = self._check_available()

    def _check_available(self) -> bool:
        """检查 SenseVoice 是否可用。"""
        if not self._script_path.exists():
            if self._verbose:
                print(f"[SenseVoiceASR] 脚本不存在: {self._script_path}")
            return False

        # 检查模型文件
        required_files = ["sense-voice-encoder.rknn", "embedding.npy", "fsmnvad-offline.onnx"]
        for f in required_files:
            if not (self._model_dir / f).exists():
                if self._verbose:
                    print(f"[SenseVoiceASR] 模型文件不存在: {f}")
                return False

        return True

    def transcribe(self, audio_bytes: bytes) -> ASRResponse:
        """将音频数据转换为文本。

        Args:
            audio_bytes: 原始 PCM 音频数据（16-bit signed int, mono, 16kHz）。

        Returns:
            ASRResponse 包含识别文本。
        """
        if not self._available:
            return ASRResponse(
                text="",
                latency_ms=0,
                language="auto",
                confidence=0.0,
            )

        if not audio_bytes:
            return ASRResponse(
                text="",
                latency_ms=0,
                language="auto",
                confidence=0.0,
            )

        start_time = time.time()

        # 保存为临时 WAV 文件
        wav_path = None
        try:
            wav_path = self._save_as_wav(audio_bytes)

            # 调试：保存一份录音用于检查
            if self._verbose:
                debug_path = "/tmp/debug_recording.wav"
                import shutil
                shutil.copy2(wav_path, debug_path)
                print(f"[SenseVoiceASR] 录音已保存到: {debug_path}")

            # 调用 SenseVoice 脚本
            result = subprocess.run(
                ["python3", str(self._script_path), "--audio_file", str(wav_path)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self._model_dir),
            )

            latency_ms = int((time.time() - start_time) * 1000)

            if result.returncode != 0:
                if self._verbose:
                    print(f"[SenseVoiceASR] 识别失败: {result.stderr}")
                return ASRResponse(
                    text="",
                    latency_ms=latency_ms,
                    language="auto",
                    confidence=0.0,
                )

            # 调试：保存完整原始输出到文件
            if self._verbose:
                debug_output_path = "/tmp/debug_asr_output.txt"
                with open(debug_output_path, "w") as f:
                    f.write(f"=== STDOUT ===\n{result.stdout}\n\n=== STDERR ===\n{result.stderr}")
                print(f"[SenseVoiceASR] ASR输出已保存到: {debug_output_path}")

            # SenseVoice 把识别结果输出到 STDERR
            combined_output = result.stdout + "\n" + result.stderr
            text, language = self._parse_output(combined_output)

            if self._verbose:
                print(f"[SenseVoiceASR] 识别完成: '{text}', 语言: {language}, {latency_ms}ms")

            return ASRResponse(
                text=text,
                latency_ms=latency_ms,
                language=language,
                confidence=0.8,  # SenseVoice 不返回置信度，给默认值
            )

        except subprocess.TimeoutExpired:
            latency_ms = int((time.time() - start_time) * 1000)
            return ASRResponse(
                text="",
                latency_ms=latency_ms,
                language="auto",
                confidence=0.0,
            )
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            if self._verbose:
                print(f"[SenseVoiceASR] 异常: {e}")
            return ASRResponse(
                text="",
                latency_ms=latency_ms,
                language="auto",
                confidence=0.0,
            )
        finally:
            # 清理临时文件
            if wav_path and os.path.exists(wav_path):
                os.remove(wav_path)

    def _save_as_wav(self, audio_bytes: bytes) -> str:
        """将 PCM 数据保存为 WAV 文件。保留立体声格式（SenseVoice 支持）。"""
        wav_path = tempfile.mktemp(suffix=".wav")

        # 直接保存立体声（AudioRecorder 输出的就是立体声）
        # SenseVoice 会自动处理立体声输入
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(2)  # 立体声
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(16000)  # 16kHz
            wf.writeframes(audio_bytes)

        return wav_path

    def _parse_output(self, output: str) -> tuple:
        """解析 SenseVoice 输出。

        输出格式示例：
        [Channel 0] [0.71s - 3.14s] <|en|><|EMO_UNKNOWN|><|Speech|><|woitn|>喂

        返回:
            (text, language)
        """
        if not output.strip():
            return "", ""

        # 只处理包含 [Channel X] 的行（识别结果）
        for line in output.split('\n'):
            if '[Channel 0]' not in line:
                continue

            # 提取语言（第一个 <|XX|> 标签）
            lang_match = re.search(r'<\|(\w{2})\|>', line)
            language = lang_match.group(1) if lang_match else "auto"

            # 提取文本：去掉所有 <|...|> 标签和时间戳
            text = line
            text = re.sub(r'<\|[^|]*\|>', '', text)
            text = re.sub(r'\[Channel \d+\]', '', text)
            text = re.sub(r'\[\d+\.\d+s - \d+\.\d+s\]', '', text)
            # 去掉日志时间戳
            text = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d+\s+\w\s+', '', text)
            # 去掉文件名和行号
            text = re.sub(r'\[sensevoice_rknn.py:\d+\]', '', text)
            text = text.strip()

            if text:
                return text, language

        # 没找到识别结果
        return "", "auto"

    def is_available(self) -> bool:
        """检查 ASR 是否可用。"""
        return self._available
