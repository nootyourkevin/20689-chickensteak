# ASR 语音识别

## 文件位置

```
src/line_c/asr/
├── base.py              # ASR 接口定义
├── mock_asr.py          # Mock ASR（测试用）
├── sensevoice_asr.py    # SenseVoice ASR 原版
└── asrtest.py           # SenseVoice ASR 改进版
```

---

## 1. ASR 接口定义 (`base.py`)

```python
@dataclass
class ASRResponse:
    """ASR 的一次转写结果"""
    text: str                         # 转写文本
    latency_ms: float = 0.0           # 识别耗时（毫秒）
    language: str = "auto"            # 检测到的语言 (zh/en/auto)
    confidence: float = 0.0           # 置信度 0.0-1.0


class BaseASR(ABC):
    """ASR 抽象基类——所有语音识别后端的统一接口"""

    @abstractmethod
    def transcribe(self, audio_bytes: bytes) -> ASRResponse:
        """将音频字节流转写为文本

        参数：
        - audio_bytes: 原始 PCM 音频数据（16kHz, 16bit, mono）

        返回：
        - ASRResponse: 包含转写文本和元信息
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """检测 ASR 后端是否可用"""
        ...
```

**作用**：定义 ASR 的统一接口，所有 ASR 实现都要遵循这个接口。

---

## 2. SenseVoice ASR 原版 (`sensevoice_asr.py`)

### 2.1 保存音频（问题所在）

```python
def _save_as_wav(self, audio_bytes: bytes) -> str:
    """将 PCM 数据保存为 WAV 文件。保留立体声格式（SenseVoice 支持）。"""
    wav_path = tempfile.mktemp(suffix=".wav")

    # 直接保存立体声（AudioRecorder 输出的就是立体声）
    # SenseVoice 会自动处理立体声输入
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(2)  # 立体声 ← 问题所在！
        wf.setsampwidth(2)  # 16-bit = 2 bytes
        wf.setframerate(16000)  # 16kHz
        wf.writeframes(audio_bytes)

    return wav_path
```

**问题**：直接保存立体声，SenseVoice 期望单声道，导致识别率低。

---

## 3. SenseVoice ASR 改进版 (`asrtest.py`)

### 3.1 立体声转单声道

```python
def _stereo_to_mono(self, audio_bytes: bytes) -> bytes:
    """将立体声 PCM 数据转换为单声道

    立体声格式：[L0, R0, L1, R1, ...] (左右声道交替)
    单声道格式：[M0, M1, ...]

    转换方法：取左声道（简单有效）
    """
    # 计算立体声采样数（每 4 字节一个立体声采样）
    sample_count = len(audio_bytes) // 4

    if sample_count == 0:
        return audio_bytes

    # 创建单声道数据数组
    mono_data = array.array('h')  # 16-bit signed int

    for i in range(sample_count):
        # 提取左声道（每个立体声采样的第 1 个 2 字节）
        left_sample = struct.unpack_from('<h', audio_bytes, i * 4)[0]
        mono_data.append(left_sample)

    return mono_data.tobytes()
```

**作用**：把立体声数据转换为单声道，取左声道。

---

### 3.2 音频归一化

```python
def _normalize_audio(self, audio_bytes: bytes) -> bytes:
    """音频归一化：调整音量到合适水平

    将音频的最大振幅归一化到 80% 的最大值，避免削波。
    """
    # 转换为采样数组
    sample_count = len(audio_bytes) // 2
    samples = array.array('h')
    for i in range(sample_count):
        sample = struct.unpack_from('<h', audio_bytes, i * 2)[0]
        samples.append(sample)

    # 找到最大振幅
    max_amplitude = max(abs(s) for s in samples) if samples else 0

    # 如果音量太小，进行放大
    if max_amplitude > 0 and max_amplitude < 16000:
        # 计算放大倍数，目标是 80% 的最大值
        target_amplitude = 32768 * 0.8  # 80% of max 16-bit value
        gain = min(target_amplitude / max_amplitude, 4.0)  # 限制最大增益

        # 应用增益
        normalized = array.array('h')
        for sample in samples:
            new_sample = int(sample * gain)
            # 防止溢出
            new_sample = max(-32768, min(32767, new_sample))
            normalized.append(new_sample)

        return normalized.tobytes()

    return audio_bytes
```

**作用**：小音量录音也能识别，防止音量过大削波。

---

### 3.3 保存为 WAV（改进版）

```python
def _save_as_wav(self, audio_bytes: bytes) -> str:
    """将 PCM 数据保存为 WAV 文件

    关键改进：
    1. 自动检测立体声/单声道
    2. 立体声转单声道（解决识别率低的核心问题）
    3. 音频归一化（提高小音量识别率）
    """
    wav_path = tempfile.mktemp(suffix=".wav")

    # 检测是否为立体声
    # 立体声 PCM 数据量应该是 4 的倍数（每采样4字节）
    is_stereo = (len(audio_bytes) % 4 == 0) and (len(audio_bytes) > 0)

    if is_stereo:
        # 转换立体声为单声道
        audio_bytes = self._stereo_to_mono(audio_bytes)

    # 音频归一化
    audio_bytes = self._normalize_audio(audio_bytes)

    # 保存为单声道 WAV
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)  # 单声道
        wf.setsampwidth(2)  # 16-bit = 2 bytes
        wf.setframerate(16000)  # 16kHz
        wf.writeframes(audio_bytes)

    return wav_path
```

**作用**：完整改进，解决识别率低的核心问题。

---

## 📊 数据格式对比

| 格式 | 采样数/秒 | 字节/采样 | 数据大小/秒 |
|------|-----------|-----------|-------------|
| 立体声 | 16000 | 4 | 64000 bytes |
| 单声道 | 16000 | 2 | 32000 bytes |

---

## 🔄 转换过程

```
原始录音 (立体声 163840 bytes)
    ↓
_stereo_to_mono() → 取左声道，数据减半 (81920 bytes)
    ↓
_normalize_audio() → 放大小音量
    ↓
保存为 WAV (单声道)
    ↓
SenseVoice 识别
```
