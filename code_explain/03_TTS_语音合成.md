# TTS 语音合成

## 文件位置

```
src/line_c/tts/
├── base.py              # TTS 接口定义
├── mock_tts.py          # Mock TTS（测试用）
├── piper_tts.py         # Piper TTS（备用）
└── paroli_tts.py        # Paroli TTS（RKNN 加速）
```

---

## 1. TTS 接口定义 (`base.py`)

```python
@dataclass
class TTSResponse:
    """TTS 的一次合成结果"""
    audio_bytes: bytes                # PCM 音频数据
    sample_rate: int = 22050          # 采样率
    latency_ms: float = 0.0           # 合成耗时（毫秒）


class BaseTTS(ABC):
    """TTS 抽象基类——所有语音合成后端的统一接口"""

    @abstractmethod
    def speak(self, text: str) -> TTSResponse:
        """将文本转换为语音

        参数：
        - text: 要合成的文本

        返回：
        - TTSResponse: 包含音频数据和元信息
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """检测 TTS 后端是否可用"""
        ...
```

**作用**：定义 TTS 的统一接口。

---

## 2. Paroli TTS (`paroli_tts.py`)

### 2.1 初始化

```python
class ParoliTTS(BaseTTS):
    """Paroli/Piper TTS 适配器（RKNN 加速）"""

    def __init__(
        self,
        encoder_path: str = "/root/paroli-daemon/build/streaming-piper/ljspeech/encoder.onnx",
        decoder_path: str = "/root/paroli-daemon/build/streaming-piper/ljspeech/decoder.rknn",
        config_path: str = "/root/paroli-daemon/build/streaming-piper/ljspeech/config.json",
        espeak_data: str = "/root/piper_phonemize/share/espeak-ng-data",
        length_scale: float = 1.0,
        verbose: bool = False,
    ):
        """
        参数说明：
        - encoder_path:  编码器模型路径
        - decoder_path:  解码器模型路径（RKNN 加速）
        - config_path:   配置文件路径
        - espeak_data:   espeak-ng 数据路径
        - length_scale:  语速控制（1.0=正常，<1.0=更快，>1.0=更慢）
        - verbose:       是否打印调试信息
        """
        self._encoder_path = encoder_path
        self._decoder_path = decoder_path
        self._config_path = config_path
        self._espeak_data = espeak_data
        self._length_scale = length_scale
        self._verbose = verbose
```

---

### 2.2 合成语音

```python
    def speak(self, text: str) -> TTSResponse:
        """调用 paroli-cli 合成语音"""
        if not text.strip():
            return TTSResponse(audio_bytes=b"", sample_rate=22050, latency_ms=0)

        start_time = time.time()

        # 创建临时文件
        wav_path = tempfile.mktemp(suffix=".wav")

        try:
            # 构建命令
            cmd = [
                "sudo", "-n",
                "/root/paroli-daemon/build/paroli-cli",
                "--encoder", self._encoder_path,
                "--decoder", self._decoder_path,
                "-c", self._config_path,
                "--espeak_data", self._espeak_data,
                "-f", wav_path,
                "--length_scale", str(self._length_scale),
            ]

            # 执行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            if result.returncode != 0:
                print(f"[ParoliTTS] 合成失败: {result.stderr}")
                return TTSResponse(audio_bytes=b"", sample_rate=22050, latency_ms=latency_ms)

            # 读取生成的 WAV 文件
            with wave.open(wav_path, "rb") as wf:
                audio_bytes = wf.readframes(wf.getnframes())
                sample_rate = wf.getframerate()

            if self._verbose:
                print(f"[ParoliTTS] 合成完成: {len(audio_bytes)} bytes, {latency_ms}ms")

            return TTSResponse(
                audio_bytes=audio_bytes,
                sample_rate=sample_rate,
                latency_ms=latency_ms,
            )

        except subprocess.TimeoutExpired:
            latency_ms = int((time.time() - start_time) * 1000)
            return TTSResponse(audio_bytes=b"", sample_rate=22050, latency_ms=latency_ms)
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            print(f"[ParoliTTS] 异常: {e}")
            return TTSResponse(audio_bytes=b"", sample_rate=22050, latency_ms=latency_ms)
        finally:
            # 清理临时文件
            if os.path.exists(wav_path):
                os.remove(wav_path)
```

**作用**：调用 Paroli/Piper TTS 合成语音（RKNN 加速）。

---

## 📊 TTS 对比

| TTS | 模型 | 采样率 | 特点 |
|-----|------|--------|------|
| Paroli | Piper RKNN | 22050Hz | RKNN 加速，4.3x 实时 |
| Mock | 无 | 16000Hz | 测试用，播放提示音 |

---

## 🔄 合成流程

```
文本输入
    ↓
paroli-cli 命令
    ↓
编码器 (encoder.onnx)
    ↓
解码器 (decoder.rknn) ← RKNN 加速
    ↓
生成 WAV 文件
    ↓
读取音频数据
    ↓
返回 TTSResponse
```
