# 关键代码详解

本目录包含项目中所有关键代码的详细说明，按功能分类。

---

## 📁 文件列表

| 文件 | 说明 |
|------|------|
| [01_ASR_语音识别.md](01_ASR_语音识别.md) | ASR 接口、原版、改进版（立体声转单声道） |
| [03_TTS_语音合成.md](03_TTS_语音合成.md) | TTS 接口、Paroli TTS（RKNN 加速） |
| [04_录音器.md](04_录音器.md) | 录音器配置、设备打开、循环录音 |
| [05_模型串联.md](05_模型串联.md) | 核心串联逻辑：ASR → LLM → TTS |
| [06_启动入口.md](06_启动入口.md) | 各版本启动入口、命令行参数 |

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

## 📊 文件路径速查表

| 功能 | 文件路径 |
|------|----------|
| ASR 接口 | `src/line_c/asr/base.py` |
| ASR 原版 | `src/line_c/asr/sensevoice_asr.py` |
| ASR 改进版 | `src/line_c/asr/asrtest.py` |
| TTS 接口 | `src/line_c/tts/base.py` |
| Paroli TTS | `src/line_c/tts/paroli_tts.py` |
| 录音器 | `src/line_c/audio/recorder.py` |
| 模型串联 | `src/line_c/ui/pages/chat_page.py` |
| 原版入口 | `src/main.py` |
| 配置文件 | `src/line_c/config.py` |

---

## 📝 版本说明

| 版本 | 分支 | 主要功能 |
|------|------|----------|
| v1.0 | main | 基础版本（DeepSeek API） |
| v1.1 | v1.1 | ASR 改进（立体声转单声道） |
| v1.2 | v1.2 | MiMo API 支持 + 关键代码文档 |
