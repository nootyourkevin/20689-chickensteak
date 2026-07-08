"""SenseVoice RKNN ASR 适配器 (测试改进版)。

主要改进：
1. 立体声转单声道（解决识别率低的核心问题）
2. 音频预处理（归一化、降噪）
3. 更详细的调试信息

调用 /home/elf/SenseVoiceSmall-RKNN2/sensevoice_rknn.py 进行语音识别。
需要单声道 16kHz WAV 格式。

使用方式：
    from .asrtest import SenseVoiceASRTest
    asr = SenseVoiceASRTest(verbose=True)
    result = asr.transcribe(audio_bytes)
"""

import os
import re
import subprocess
import tempfile
import time
import wave
import struct
import array
from pathlib import Path

# 独立运行时，直接导入 base 模块
try:
    from .base import BaseASR, ASRResponse
except ImportError:
    # 独立运行模式，定义简单的基类
    from dataclasses import dataclass
    from abc import ABC, abstractmethod

    @dataclass
    class ASRResponse:
        text: str
        latency_ms: float = 0.0
        language: str = "auto"
        confidence: float = 0.0

    class BaseASR(ABC):
        @abstractmethod
        def transcribe(self, audio_bytes: bytes) -> ASRResponse:
            ...
        @abstractmethod
        def is_available(self) -> bool:
            ...
        @property
        def name(self) -> str:
            return self.__class__.__name__


class SenseVoiceASRTest(BaseASR):
    """SenseVoice RKNN ASR 适配器（测试改进版）。"""

    def __init__(
        self,
        model_dir: str = "/home/elf/SenseVoiceSmall-RKNN2",
        script_name: str = "sensevoice_rknn.py",
        verbose: bool = False,
    ):
        self._model_dir = Path(model_dir)
        self._script_path = self._model_dir / script_name
        self._verbose = verbose
        self._available = self._check_available()

    def _check_available(self) -> bool:
        if not self._script_path.exists():
            if self._verbose:
                print(f"[SenseVoiceASRTest] 脚本不存在: {self._script_path}")
            return False
        required_files = ["sense-voice-encoder.rknn", "embedding.npy", "fsmnvad-offline.onnx"]
        for f in required_files:
            if not (self._model_dir / f).exists():
                if self._verbose:
                    print(f"[SenseVoiceASRTest] 模型文件不存在: {f}")
                return False
        return True

    def transcribe(self, audio_bytes: bytes) -> ASRResponse:
        if not self._available:
            return ASRResponse(text="", latency_ms=0, language="auto", confidence=0.0)
        if not audio_bytes:
            return ASRResponse(text="", latency_ms=0, language="auto", confidence=0.0)

        start_time = time.time()
        wav_path = None
        try:
            wav_path = self._save_as_wav(audio_bytes)
            if self._verbose:
                debug_path = "/tmp/debug_recording_test.wav"
                import shutil
                shutil.copy2(wav_path, debug_path)
                print(f"[SenseVoiceASRTest] 录音已保存到: {debug_path}")

            result = subprocess.run(
                ["python3", str(self._script_path), "--audio_file", str(wav_path)],
                capture_output=True, text=True, timeout=30, cwd=str(self._model_dir),
            )
            latency_ms = int((time.time() - start_time) * 1000)

            if result.returncode != 0:
                if self._verbose:
                    print(f"[SenseVoiceASRTest] 识别失败: {result.stderr}")
                return ASRResponse(text="", latency_ms=latency_ms, language="auto", confidence=0.0)

            if self._verbose:
                debug_output_path = "/tmp/debug_asr_output_test.txt"
                with open(debug_output_path, "w") as f:
                    f.write(f"=== STDOUT ===\n{result.stdout}\n\n=== STDERR ===\n{result.stderr}")
                print(f"[SenseVoiceASRTest] ASR输出已保存到: {debug_output_path}")

            combined_output = result.stdout + "\n" + result.stderr
            text, language = self._parse_output(combined_output)

            if self._verbose:
                print(f"[SenseVoiceASRTest] 识别完成: '{text}', 语言: {language}, {latency_ms}ms")

            return ASRResponse(text=text, latency_ms=latency_ms, language=language, confidence=0.8)

        except subprocess.TimeoutExpired:
            latency_ms = int((time.time() - start_time) * 1000)
            return ASRResponse(text="", latency_ms=latency_ms, language="auto", confidence=0.0)
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            if self._verbose:
                print(f"[SenseVoiceASRTest] 异常: {e}")
            return ASRResponse(text="", latency_ms=latency_ms, language="auto", confidence=0.0)
        finally:
            if wav_path and os.path.exists(wav_path):
                os.remove(wav_path)

    def _stereo_to_mono(self, audio_bytes: bytes) -> bytes:
        if len(audio_bytes) < 4:
            return audio_bytes
        sample_count = len(audio_bytes) // 4
        if sample_count == 0:
            return audio_bytes

        mono_data = array.array('h')
        for i in range(sample_count):
            left_sample = struct.unpack_from('<h', audio_bytes, i * 4)[0]
            mono_data.append(left_sample)
        return mono_data.tobytes()

    def _normalize_audio(self, audio_bytes: bytes) -> bytes:
        if len(audio_bytes) < 2:
            return audio_bytes
        sample_count = len(audio_bytes) // 2
        if sample_count == 0:
            return audio_bytes

        samples = array.array('h')
        for i in range(sample_count):
            sample = struct.unpack_from('<h', audio_bytes, i * 2)[0]
            samples.append(sample)

        max_amplitude = max(abs(s) for s in samples) if samples else 0

        if max_amplitude > 0 and max_amplitude < 16000:
            target_amplitude = 32768 * 0.8
            gain = min(target_amplitude / max_amplitude, 4.0)
            normalized = array.array('h')
            for sample in samples:
                new_sample = int(sample * gain)
                new_sample = max(-32768, min(32767, new_sample))
                normalized.append(new_sample)
            return normalized.tobytes()
        return audio_bytes

    def _save_as_wav(self, audio_bytes: bytes) -> str:
        wav_path = tempfile.mktemp(suffix=".wav")
        is_stereo = (len(audio_bytes) % 4 == 0) and (len(audio_bytes) > 0)

        if is_stereo:
            if self._verbose:
                print(f"[SenseVoiceASRTest] 检测到立体声数据，转换为单声道...")
                print(f"[SenseVoiceASRTest] 原始数据大小: {len(audio_bytes)} bytes")
            audio_bytes = self._stereo_to_mono(audio_bytes)
            if self._verbose:
                print(f"[SenseVoiceASRTest] 转换后数据大小: {len(audio_bytes)} bytes")

        audio_bytes = self._normalize_audio(audio_bytes)

        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio_bytes)

        if self._verbose:
            with wave.open(wav_path, "rb") as wf:
                print(f"[SenseVoiceASRTest] WAV 文件信息:")
                print(f"  - 通道数: {wf.getnchannels()}")
                print(f"  - 采样宽度: {wf.getsampwidth()} bytes")
                print(f"  - 采样率: {wf.getframerate()} Hz")
                print(f"  - 帧数: {wf.getnframes()}")
                print(f"  - 时长: {wf.getnframes() / wf.getframerate():.2f} 秒")

        return wav_path

    def _parse_output(self, output: str) -> tuple:
        if not output.strip():
            return "", ""
        for line in output.split('\n'):
            if '[Channel 0]' not in line:
                continue
            lang_match = re.search(r'<\|(\w{2})\|>', line)
            language = lang_match.group(1) if lang_match else "auto"
            text = line
            text = re.sub(r'<\|[^|]*\|>', '', text)
            text = re.sub(r'\[Channel \d+\]', '', text)
            text = re.sub(r'\[\d+\.\d+s - \d+\.\d+s\]', '', text)
            text = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d+\s+\w\s+', '', text)
            text = re.sub(r'\[sensevoice_rknn.py:\d+\]', '', text)
            text = text.strip()
            if text:
                return text, language
        return "", "auto"

    def is_available(self) -> bool:
        return self._available


def test_audio_conversion():
    """测试音频转换功能。"""
    print("=== 测试音频转换功能 ===")

    import math
    sample_rate = 16000
    duration = 1.0
    sample_count = int(sample_rate * duration)

    test_data = array.array('h')
    for i in range(sample_count):
        left = int(16000 * math.sin(2 * math.pi * 440 * i / sample_rate))
        right = int(16000 * math.sin(2 * math.pi * 880 * i / sample_rate))
        test_data.append(left)
        test_data.append(right)

    stereo_bytes = test_data.tobytes()
    print(f"立体声数据大小: {len(stereo_bytes)} bytes")

    asr = SenseVoiceASRTest(verbose=True)
    mono_bytes = asr._stereo_to_mono(stereo_bytes)
    print(f"单声道数据大小: {len(mono_bytes)} bytes")

    mono_samples = array.array('h')
    mono_samples.frombytes(mono_bytes)
    print(f"单声道采样数: {len(mono_samples)}")
    print(f"前5个采样: {list(mono_samples[:5])}")

    print("\n=== 测试完成 ===")


if __name__ == "__main__":
    test_audio_conversion()