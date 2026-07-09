# 关键代码详解

本文档列出项目中所有关键代码，按功能分类说明。

---

## 目录

1. [ASR 语音识别](#1-asr-语音识别)
2. [LLM 大语言模型](#2-llm-大语言模型)
3. [TTS 语音合成](#3-tts-语音合成)
4. [录音器](#4-录音器)
5. [模型串联](#5-模型串联)
6. [启动入口](#6-启动入口)

---

## 1. ASR 语音识别

### 1.1 ASR 接口定义 (`src/line_c/asr/base.py`)

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

### 1.2 SenseVoice ASR 原版 (`src/line_c/asr/sensevoice_asr.py`)

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

### 1.3 SenseVoice ASR 改进版 (`src/line_c/asr/asrtest.py`)

```python
def _stereo_to_mono(self, audio_bytes: bytes) -> bytes:
    """将立体声 PCM 数据转换为单声道

    立体声格式：[L0, R0, L1, R1, ...] (左右声道交替)
    单声道格式：[M0, M1, ...]
    """
    # 计算立体声采样数（每 4 字节一个立体声采样）
    sample_count = len(audio_bytes) // 4

    # 创建单声道数据数组
    mono_data = array.array('h')  # 16-bit signed int

    for i in range(sample_count):
        # 提取左声道（每个立体声采样的第 1 个 2 字节）
        left_sample = struct.unpack_from('<h', audio_bytes, i * 4)[0]
        mono_data.append(left_sample)

    return mono_data.tobytes()


def _normalize_audio(self, audio_bytes: bytes) -> bytes:
    """音频归一化：调整音量到合适水平

    将音频的最大振幅归一化到 80% 的最大值，避免削波。
    """
    # 找到最大振幅
    max_amplitude = max(abs(s) for s in samples)

    # 如果音量太小，进行放大
    if max_amplitude > 0 and max_amplitude < 16000:
        # 计算放大倍数，目标是 80% 的最大值
        target_amplitude = 32768 * 0.8
        gain = min(target_amplitude / max_amplitude, 4.0)  # 限制最大增益

        # 应用增益
        normalized = array.array('h')
        for sample in samples:
            new_sample = int(sample * gain)
            new_sample = max(-32768, min(32767, new_sample))  # 防止溢出
            normalized.append(new_sample)

        return normalized.tobytes()

    return audio_bytes


def _save_as_wav(self, audio_bytes: bytes) -> str:
    """将 PCM 数据保存为 WAV 文件

    关键改进：
    1. 自动检测立体声/单声道
    2. 立体声转单声道（解决识别率低的核心问题）
    3. 音频归一化（提高小音量识别率）
    """
    wav_path = tempfile.mktemp(suffix=".wav")

    # 检测是否为立体声
    is_stereo = (len(audio_bytes) % 4 == 0) and (len(audio_bytes) > 0)

    if is_stereo:
        # 转换立体声为单声道
        audio_bytes = self._stereo_to_mono(audio_bytes)

    # 音频归一化
    audio_bytes = self._normalize_audio(audio_bytes)

    # 保存为单声道 WAV
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)  # 单声道
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_bytes)

    return wav_path
```

**改进**：
1. 立体声转单声道（取左声道）
2. 音频归一化（小音量也能识别）
3. 详细调试信息

---

## 2. LLM 大语言模型

### 2.1 LLM 接口定义 (`src/line_c/llm/base.py`)

```python
@dataclass
class LLMResponse:
    """LLM 的一次回复结果"""
    text: str                         # 回复文本
    latency_ms: float = 0.0           # 响应耗时（毫秒）
    tokens_used: int = 0              # 使用的 token 数


class BaseLLM(ABC):
    """LLM 抽象基类——所有大模型后端的统一接口"""

    @abstractmethod
    def chat(self, system_prompt: str, messages: List[dict]) -> LLMResponse:
        """发送对话请求

        参数：
        - system_prompt: 系统提示词
        - messages: 对话历史 [{"role": "user", "content": "..."}]

        返回：
        - LLMResponse: 包含回复文本和元信息
        """
        ...
```

**作用**：定义 LLM 的统一接口。

---

### 2.2 DeepSeek API (`src/line_c/llm/cloud_llm.py`)

```python
class CloudLLM(BaseLLM):
    """通过 HTTP 调用云端大模型 API"""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        model: str = "deepseek-chat",
        max_tokens: int = 150,
        temperature: float = 0.7,
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def chat(self, system_prompt: str, messages: List[dict]) -> LLMResponse:
        """发送请求到云端 API"""
        full_messages = [{"role": "system", "content": system_prompt}]
        full_messages.extend(messages)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": full_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        start = time.time()
        response = requests.post(
            self.api_url,
            headers=headers,
            json=body,
            timeout=30,
        )
        elapsed_ms = (time.time() - start) * 1000

        data = response.json()
        reply_text = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("total_tokens", 0)

        return LLMResponse(
            text=reply_text,
            latency_ms=elapsed_ms,
            tokens_used=tokens,
        )
```

**作用**：调用 DeepSeek 云端 API 获取 LLM 回复。

---

### 2.3 MiMo API (`src/line_c/llm/cloud_llm_mimo.py`)

```python
class CloudLLMMimo(BaseLLM):
    """通过 HTTP 调用小米 MiMo API"""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        model: str = "mimo-v2.5",
        max_tokens: int = 500,
        temperature: float = 0.7,
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def chat(self, system_prompt: str, messages: List[dict]) -> LLMResponse:
        """发送请求到 MiMo API"""
        full_messages = [{"role": "system", "content": system_prompt}]
        full_messages.extend(messages)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": full_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        start = time.time()
        response = requests.post(
            self.api_url,
            headers=headers,
            json=body,
            timeout=30,
        )
        elapsed_ms = (time.time() - start) * 1000

        data = response.json()
        message = data["choices"][0]["message"]

        # MiMo 思考模式：优先使用 content，如果为空则使用 reasoning_content
        reply_text = message.get("content", "")
        if not reply_text:
            reply_text = message.get("reasoning_content", "")

        tokens = data.get("usage", {}).get("total_tokens", 0)

        return LLMResponse(
            text=reply_text,
            latency_ms=elapsed_ms,
            tokens_used=tokens,
        )
```

**作用**：调用小米 MiMo API，支持思考模式。

---

## 3. TTS 语音合成

### 3.1 TTS 接口定义 (`src/line_c/tts/base.py`)

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
```

**作用**：定义 TTS 的统一接口。

---

### 3.2 Paroli TTS (`src/line_c/tts/paroli_tts.py`)

```python
class ParoliTTS(BaseTTS):
    """Paroli/Piper TTS 适配器（RKNN 加速）"""

    def speak(self, text: str) -> TTSResponse:
        """调用 paroli-cli 合成语音"""
        # 构建命令
        cmd = [
            "sudo", "-n",
            "/root/paroli-daemon/build/paroli-cli",
            "--encoder", "/root/paroli-daemon/build/streaming-piper/ljspeech/encoder.onnx",
            "--decoder", "/root/paroli-daemon/build/streaming-piper/ljspeech/decoder.rknn",
            "-c", "/root/paroli-daemon/build/streaming-piper/ljspeech/config.json",
            "--espeak_data", "/root/piper_phonemize/share/espeak-ng-data",
            "-f", wav_path,
            "--length_scale", str(self._length_scale),
        ]

        # 执行命令
        result = subprocess.run(cmd, capture_output=True, timeout=30)

        # 读取生成的 WAV 文件
        with wave.open(wav_path, "rb") as wf:
            audio_bytes = wf.readframes(wf.getnframes())
            sample_rate = wf.getframerate()

        return TTSResponse(
            audio_bytes=audio_bytes,
            sample_rate=sample_rate,
            latency_ms=elapsed_ms,
        )
```

**作用**：调用 Paroli/Piper TTS 合成语音（RKNN 加速）。

---

## 4. 录音器

### 4.1 录音器 (`src/line_c/audio/recorder.py`)

```python
class AudioRecorder(QObject):
    """从麦克风采集音频"""

    CHUNK = 1024           # 每次读取的帧数（缓冲区大小）
    CHANNELS = 2           # 立体声（ELF2 设备只支持立体声）
    RATE = 16000           # 采样率 16kHz

    def _record_thread(self):
        """后台线程：打开 PyAudio 并循环读取音频帧"""
        import pyaudio

        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16,      # 16-bit 整数格式
            channels=self.CHANNELS,      # 立体声
            rate=self.RATE,              # 16kHz 采样率
            input_device_index=1,        # ELF2 使用 card 1 (rockchipnau8822)
            frames_per_buffer=self.CHUNK,
        )

        while self._recording:
            try:
                data = stream.read(self.CHUNK, exception_on_overflow=False)
            except Exception:
                break
            self._frames.append(data)

            # 计算 RMS 电平（用于 UI 显示音量条）
            sample_count = len(data) // 2
            samples = struct.unpack(f"<{sample_count}h", data)
            rms = math.sqrt(sum(s * s for s in samples) / sample_count)
            level = min(rms / 32768.0 * 100.0, 100.0)
            self.audio_level.emit(level)

        # 线程退出时返回录音数据
        all_data = b"".join(self._frames)
        self._frames = []
        self._recording = False
        self.recording_finished.emit(all_data)

    def stop(self):
        """设置停止标志。录音线程会在下一次 read() 后退出。"""
        self._recording = False
```

**作用**：从麦克风采集立体声音频数据。

---

## 5. 模型串联

### 5.1 核心串联逻辑 (`src/line_c/ui/pages/chat_page.py`)

```python
# 录音完成 → 触发 ASR
def _on_recording_finished(self, pcm_data: bytes):
    """录音完成 → 后台线程跑 ASR 转写"""
    if not pcm_data or len(pcm_data) < 3200:  # < 0.1 秒 = 误触
        return

    def _run():
        result = self._asr.transcribe(pcm_data)  # ASR 识别
        text = result.text
        self.asr_result_ready.emit(text)  # 发送信号到主线程

    threading.Thread(target=_run).start()


# ASR 结果 → 显示到输入框
def _on_asr_result(self, text: str):
    """ASR 识别结果 → 输入框 → 自动发送"""
    if not text:
        self._reset_input_state("输入你想说的话...")
        return

    self.input_box.setPlainText(text.strip())  # 把识别结果放到输入框
    QTimer.singleShot(200, self._on_send)  # 200ms 后自动发送


# 发送消息 → 调用 LLM
def _on_send(self):
    """发送消息 → 获取 LLM 回复"""
    text = self.input_box.toPlainText().strip()
    if not text or not self._llm:
        return

    # 添加用户消息到对话历史
    self._conversation_history.append({"role": "user", "content": text})

    # 构建系统提示词
    system_prompt = self._prompt_builder.build()

    # 调用 LLM（后台线程）
    def _run():
        response = self._llm.chat(system_prompt, self._conversation_history)
        self._on_llm_response(response.text)

    threading.Thread(target=_run).start()


# LLM 回复 → 显示到界面
def _on_llm_response(self, reply_text: str):
    """收到 LLM 回复 → 显示到界面 → 触发 TTS"""
    if not reply_text:
        return

    # 添加 AI 回复到对话历史
    self._conversation_history.append({"role": "assistant", "content": reply_text})

    # 显示到界面
    self._add_bubble(reply_text, is_user=False)

    # 触发 TTS 播放
    self._speak_async(reply_text)


# TTS 播放 → 语音输出
def _speak_async(self, text: str):
    """后台线程跑 TTS 合成 + 播放"""
    def _run():
        try:
            # TTS 合成
            tts_resp = self._tts.speak(text)
            if tts_resp and tts_resp.audio_bytes:
                # 播放音频
                self._player.play(tts_resp.audio_bytes, tts_resp.sample_rate)
        except Exception as e:
            print(f"TTS 播放异常: {e}")

    threading.Thread(target=_run).start()


# 打断 TTS
def _start_recording(self):
    """开始录音：打断 TTS → 启动录音器"""
    if not self._voice_mode or self._recording:
        return

    # 软件去抖 300ms（防止快速双击）
    now = time.monotonic() * 1000
    if now - self._last_press_time < 300:
        return
    self._last_press_time = now

    # 打断正在播放的 TTS
    if self._player is not None:
        self._player.stop()  # 停止播放

    self._recording = True
    self._recorder.start()

    # UI 反馈
    self.mic_button.setChecked(True)
    self.input_box.setPlaceholderText("🎤 正在录音... 松开按钮结束")
    self.input_box.setEnabled(False)
```

**作用**：把 ASR → LLM → TTS 串联起来，实现完整的语音对话流程。

---

## 6. 启动入口

### 6.1 原版 (`src/main.py`)

```python
def create_llm(backend: str):
    """根据命令行参数创建对应的 LLM 适配器"""
    if backend == "cloud":
        api_key = os.environ.get("CLOUD_API_KEY", CLOUD_API_KEY)
        api_url = os.environ.get("CLOUD_API_URL", CLOUD_API_URL)
        return CloudLLM(api_url=api_url, api_key=api_key)
    return MockLLM()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", choices=["mock", "cloud"], default="mock")
    parser.add_argument("--voice", action="store_true")
    parser.add_argument("--asr", choices=["mock", "sensevoice"], default="mock")
    parser.add_argument("--tts", choices=["mock", "piper"], default="mock")
    args = parser.parse_args()

    # 创建 LLM
    llm = create_llm(args.llm)

    # 创建 TTS
    if args.tts == "piper":
        tts = ParoliTTS()
    else:
        tts = MockTTS()

    # 语音模式
    if args.voice:
        if args.asr == "sensevoice":
            asr = SenseVoiceASR()
        else:
            asr = MockASR()

        window.chat_page.setup_voice(asr=asr)
```

**作用**：命令行入口，根据参数创建不同的 ASR/LLM/TTS。

---

### 6.2 MiMo 版本 (`src/main_mimo.py`)

```python
def create_llm(backend: str, model: str = "mimo-v2.5"):
    """根据命令行参数创建对应的 LLM 适配器"""
    if backend == "cloud":
        # MiMo API 配置（硬编码）
        api_key = "tp-c4o62wkbs8sxpzcbwe9l5qnfczohhex60xa9jd1glov436qm"
        api_url = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
        return CloudLLMMimo(
            api_url=api_url,
            api_key=api_key,
            model=model,
            max_tokens=500,
            temperature=0.7,
        )
    return MockLLM()
```

**作用**：MiMo 版本，硬编码 MiMo API 配置。

---

## 📊 文件清单

| 文件 | 作用 |
|------|------|
| `src/line_c/asr/base.py` | ASR 接口定义 |
| `src/line_c/asr/sensevoice_asr.py` | SenseVoice ASR 原版 |
| `src/line_c/asr/asrtest.py` | SenseVoice ASR 改进版 |
| `src/line_c/llm/base.py` | LLM 接口定义 |
| `src/line_c/llm/cloud_llm.py` | DeepSeek API |
| `src/line_c/llm/cloud_llm_mimo.py` | MiMo API |
| `src/line_c/tts/base.py` | TTS 接口定义 |
| `src/line_c/tts/paroli_tts.py` | Paroli TTS |
| `src/line_c/audio/recorder.py` | 录音器 |
| `src/line_c/ui/pages/chat_page.py` | 模型串联核心 |
| `src/main.py` | 原版启动入口 |
| `src/main_mimo.py` | MiMo 版本启动入口 |

---

## 🔄 数据流

```
用户按键
    ↓
录音器 (recorder.py)
    ↓ 立体声 PCM
ASR (sensevoice_asr.py / asrtest.py)
    ↓ 文字
LLM (cloud_llm.py / cloud_llm_mimo.py)
    ↓ 文字
TTS (paroli_tts.py)
    ↓ 音频
播放器 (player.py)
    ↓
用户听到 AI 回复
```

---

## 📝 版本说明

| 版本 | 文件 | ASR | LLM | TTS |
|------|------|-----|-----|-----|
| 原版 | `main.py` | SenseVoice 原版 | DeepSeek 云端 | Paroli |
| MiMo | `main_mimo.py` | SenseVoice 原版 | MiMo 云端 | Paroli |
| 测试版 | `main_test.py` | SenseVoice 改进版 | DeepSeek 云端 | Paroli |
| V4 Flash | `main_deepseek_v4_flash.py` | SenseVoice 原版 | DeepSeek V4 Flash | Paroli |
