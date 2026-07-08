# 端侧AI语言学习机 — 开发进度记录

## 最后更新：2026-07-04

---

## 本次对话完成的工作

### 1. 代理配置（网络问题解决）
- ELF2板卡上安装了Clash Verge代理软件
- 代理端口：`127.0.0.1:7897`（mihomo内核）
- 启动方式：`sudo /usr/bin/verge-mihomo -d /root/.local/share/io.github.clash-verge-rev.clash-verge-rev -f /root/.local/share/io.github.clash-verge-rev.clash-verge-rev/clash-verge.yaml &`
- 需要设置环境变量：
  ```bash
  export http_proxy=http://127.0.0.1:7897
  export https_proxy=http://127.0.0.1:7897
  ```
- git代理配置：
  ```bash
  git config --global http.proxy http://127.0.0.1:7897
  git config --global https.proxy http://127.0.0.1:7897
  ```

---

### 2. Line B — ASR模块（✅ 完成）

**任务：** 在ELF2上编译sherpa-onnx（开启RKNN支持），部署SenseVoiceSmall-RKNN2，测试ASR识别率与延迟

**完成步骤：**
1. 克隆sherpa-onnx仓库：`/home/elf/sherpa-onnx`
2. 安装依赖：`sudo apt install alsa-utils libasound2-dev pkg-config`
3. 安装RKNN SDK头文件和库（从`rknn-toolkit2`仓库复制到`/usr/lib`和`/usr/include`）
4. cmake配置：`cmake -DSHERPA_ONNX_ENABLE_RKNN=ON -DCMAKE_BUILD_TYPE=Release ..`
5. 编译：`make -j2`（-j8会OOM）
6. 克隆SenseVoiceSmall-RKNN2模型：`/root/SenseVoiceSmall-RKNN2`
7. 安装Python依赖：`pip install kaldi_native_fbank onnxruntime sentencepiece soundfile pyyaml "numpy<2"` + `rknn_toolkit_lite2`
8. 测试ASR：
   - 中文：RTF 0.064，约15.7倍实时
   - 英文：RTF 0.09，约11倍实时
   - 录音测试：`arecord -D hw:1,0 -f S16_LE -r 16000 -c 2 -d 20 test.wav`（立体声录，ffmpeg转单声道）

**关键文件位置：**
- sherpa-onnx编译产物：`/home/elf/sherpa-onnx/build/bin/`
- SenseVoiceSmall-RKNN2模型：`/root/SenseVoiceSmall-RKNN2/`
- 运行命令：`python3 /root/SenseVoiceSmall-RKNN2/sensevoice_rknn.py --audio_file <wav文件>`

---

### 3. Line B — LLM模块（✅ 完成）

**任务：** 配置RKLLM Runtime环境，加载DeepSeek-R1-Distill-Qwen-1.5B (w8a8)，验证推理性能和输出质量

**完成步骤：**
1. 克隆rknn-llm仓库：`/root/rknn-llm`（浅克隆 `--depth 1`）
2. 从ModelScope下载预转换模型：`/home/elf/DeepSeek-R1-Distill-Qwen-1.5B_RKLLM`
   - 模型文件：`DeepSeek-R1-Distill-Qwen-1.5B_W8A8_RK3588.rkllm`（约2GB）
3. 运行demo：`./llm_demo ../DeepSeek-R1-Distill-Qwen-1.5B_W8A8_RK3588.rkllm 2048 4096`

**性能数据：**
- 生成速度：13.73 tokens/sec
- 内存占用：1.73 GB
- 模型加载：7.3秒

**关键文件位置：**
- LLM demo：`/home/elf/DeepSeek-R1-Distill-Qwen-1.5B_RKLLM/demo_Linux_aarch64/llm_demo`
- 模型文件：`/home/elf/DeepSeek-R1-Distill-Qwen-1.5B_RKLLM/DeepSeek-R1-Distill-Qwen-1.5B_W8A8_RK3588.rkllm`
- 运行命令：
  ```bash
  cd /home/elf/DeepSeek-R1-Distill-Qwen-1.5B_RKLLM/demo_Linux_aarch64/
  export LD_LIBRARY_PATH=./lib
  ./llm_demo ../DeepSeek-R1-Distill-Qwen-1.5B_W8A8_RK3588.rkllm 2048 4096
  ```

---

### 4. Line B — TTS模块（✅ 完成）

**任务：** 部署Paroli/Piper TTS (RKNN加速)，测试语音合成质量和首字延迟

**完成步骤：**
1. 克隆paroli-daemon仓库：`/root/paroli-daemon`
2. 安装依赖：
   ```bash
   sudo apt install -y libsoxr-dev libspdlog-dev libfmt-dev libopus-dev libogg-dev nlohmann-json3-dev
   ```
   - libopusenc从源码编译：`/root/libopusenc`
   - xtensor/xtl从源码编译（最新版，支持`xtensor/containers/`路径）
3. 下载onnxruntime：`/root/onnxruntime-linux-aarch64-1.14.1`
4. 下载piper-phonemize：`/root/piper_phonemize`
5. cmake配置：`cmake .. -DORT_ROOT=... -DPIPER_PHONEMIZE_ROOT=... -DCMAKE_BUILD_TYPE=Release -DUSE_RKNN=ON`
6. 编译：`make -j2`
7. 下载TTS模型：`/root/paroli-daemon/build/streaming-piper/ljspeech/`（英文模型）
8. 测试TTS：
   - RTF 0.18-0.21，约4.8-5.5倍实时
   - 生成wav文件，用`aplay -D plughw:1,0`播放

**关键文件位置：**
- paroli-cli：`/root/paroli-daemon/build/paroli-cli`
- 模型文件：`/root/paroli-daemon/build/streaming-piper/ljspeech/`
- espeak-ng-data：`/root/piper_phonemize/share/espeak-ng-data`
- 运行命令：
  ```bash
  cd /root/paroli-daemon/build
  export LD_LIBRARY_PATH=./lib:/root/onnxruntime-linux-aarch64-1.14.1/lib:/root/piper_phonemize/lib
  ./paroli-cli --encoder ./streaming-piper/ljspeech/encoder.onnx --decoder ./streaming-piper/ljspeech/decoder.rknn -c ./streaming-piper/ljspeech/config.json --espeak_data /root/piper_phonemize/share/espeak-ng-data
  ```

**注意：** TTS只支持英文（ljspeech模型），不支持中文。根据PRD，设备只用英语回复，所以够用。

---

### 5. 音频设备信息
- 录音设备：card 1（rockchipnau8822），`arecord -D hw:1,0`
- 播放设备：card 1（rockchipnau8822），`aplay -D plughw:1,0`（用plughw自动转格式）
- 耳机已接上，音量已调到最大
- 录音需要录立体声（`-c 2`），再用ffmpeg转单声道给ASR

---

## 当前进度总结

| 模块 | 状态 | 性能 |
|------|------|------|
| ASR (SenseVoiceSmall-RKNN2) | ✅ 完成 | RTF 0.06-0.09，15.7倍实时 |
| LLM (DeepSeek-R1.5B-RKLLM) | ✅ 完成 | 13.73 tok/s，1.73GB内存 |
| TTS (Paroli/Piper-RKNN) | ✅ 完成 | RTF 0.18-0.21，4.8倍实时 |
| 管线串联 (VAD→ASR→LLM→TTS) | ⬜ 未开始 | — |

---

## 下一步工作

### B4：管线串联
- 写Python脚本串联 ASR → LLM → TTS
- MVP方案：录固定时长音频 → ASR识别 → LLM生成回复 → TTS合成 → 播放
- 后续优化：加VAD自动检测语音起止

### 其他待办
- Line A：硬件调试（MIPI屏、麦克风、GPIO按键、3D外壳）
- Line C：词汇库构建、LLM提示词工程、SRS引擎、Qt界面
- 系统集成：端到端联调

---

## 磁盘空间使用情况

| 目录 | 大小 | 说明 |
|------|------|------|
| /home/elf/rknn-toolkit2 | 5.8GB | 可删除（头文件已复制到系统目录） |
| /home/elf/sherpa-onnx | 5.3GB | 编译产物，暂留 |
| /home/elf/DeepSeek-R1-Distill-Qwen-1.5B_RKLLM | 5.0GB | LLM模型+demo |
| /root/SenseVoiceSmall-RKNN2 | ~1GB | ASR模型 |
| /root/paroli-daemon | ~1GB | TTS项目 |
| /root/rknn-llm | 1.1GB | RKLLM仓库 |

**可用空间约6GB，紧张。** 可删除rknn-toolkit2省5.8GB。

---

## 注意事项

1. **代理问题**：每次新开终端需要重新设置代理环境变量
2. **权限问题**：root和elf用户混用，注意文件权限
3. **编译并行数**：RK3588 8GB内存，make用`-j2`避免OOM
4. **git safe.directory**：root和elf混用会触发，用`git config --global --add safe.directory <路径>`解决
5. **音频格式**：录音用立体声(`-c 2`)，ASR需要单声道，用ffmpeg转换
6. **播放音频**：用`aplay -D plughw:1,0`（plughw自动转格式，避免"Channels count non available"错误）

---

## 2026-07-04 对话完成的工作

### 7. VocaLand 应用 ASR 集成（✅ 完成）

**任务：** 将 Line C 的 VocaLand 应用与 Line B 的 SenseVoice ASR 集成，实现语音输入功能

**问题排查与修复：**

1. **PyAudio 录音设备问题**
   - 问题：PyAudio 默认使用错误的录音设备，录到静音
   - 解决：在 `recorder.py` 中指定 `input_device_index=1`（ELF2 card 1）

2. **音频格式问题**
   - 问题：SenseVoice 期望立体声输入，但代码转换成了单声道
   - 解决：修改 `sensevoice_asr.py` 的 `_save_as_wav()` 直接保存立体声

3. **VAD 检测失败问题**
   - 问题：转换成单声道后，VAD 无法检测到语音段
   - 解决：保留立体声格式（与单独测试一致）

4. **ASR 输出解析问题**
   - 问题：SenseVoice 将识别结果输出到 STDERR，代码只解析 STDOUT
   - 解决：合并 STDOUT + STDERR 后再解析

5. **输出格式解析问题**
   - 问题：日志信息被误识别为识别结果
   - 解决：只解析包含 `[Channel 0]` 的行，过滤日志时间戳

**最终状态：**
- ✅ PyAudio 录音正常（立体声 16kHz）
- ✅ SenseVoice ASR 识别成功（中文识别率良好）
- ✅ DeepSeek Cloud API 对话正常
- ✅ Paroli TTS 语音合成正常（22050Hz）
- ✅ 完整语音对话链路：录音 → ASR → LLM → TTS → 播放

**启动命令：**
```bash
cd /home/elf/Language_learner
CLOUD_API_KEY=sk-xxx DISPLAY=:0 PYTHONPATH=src python src/main.py --voice --asr sensevoice --llm cloud
```

**修改的文件：**
- `src/line_c/audio/recorder.py` — 指定录音设备 index=1
- `src/line_c/asr/sensevoice_asr.py` — 保留立体声 + 解析 STDERR + 过滤日志

---

### 8. 当前进度总结（更新）

| 模块 | 状态 | 性能 |
|------|------|------|
| ASR (SenseVoiceSmall-RKNN2) | ✅ 完成 | RTF 0.06-0.09，15.7倍实时 |
| LLM (DeepSeek-R1.5B-RKLLM) | ✅ 完成 | 13.73 tok/s，1.73GB内存 |
| TTS (Paroli/Piper-RKNN) | ✅ 完成 | RTF 0.18-0.21，4.8倍实时 |
| VocaLand 应用 | ✅ 完成 | 194个单元测试通过 |
| ASR 集成到 VocaLand | ✅ 完成 | 语音识别正常工作 |
| LLM 集成到 VocaLand | ⬜ 待对接 | 目前用 Cloud API |
| TTS 集成到 VocaLand | ⬜ 待对接 | 目前用 MockTTS |
| 管线串联 (VAD→ASR→LLM→TTS) | ⬜ 未开始 | — |

---

### 9. 下一步工作

**Line B 集成：**
- 对接 RKLLM 到 VocaLand（替换 Cloud API）
- 对接 Paroli TTS 到 VocaLand（替换 MockTTS）
- 性能优化（模型按需加载/卸载）

**Line A：**
- 硬件调试（MIPI屏、GPIO按键、3D外壳）

**Line C：**
- 词汇库扩充
- 提示词工程优化
- Qt 界面美化
