# ELF2 音频调试记录

## 2026-07-08

### 问题描述

使用3.5mm有源喇叭时出现以下问题：

| 场景 | 喇叭播放 | 耳机播放 |
|------|----------|----------|
| 插上耳机录制 | - | ✓ 正常 |
| 插上喇叭录制 | ✗ 没声音 | ✓ 有声音 |
| 拔下喇叭录制 | ✓ 声音很小 | ✓ 正常 |
| 浏览器视频 | ✓ 声音很大 | - |

### 已排查内容

1. **录音设备**: card 1, device 0 (rockchip-nau8822)
2. **录音源设置**:
   - Main Mic Switch: on ✓
   - Headset Mic Switch: off ✓
3. **PulseAudio默认输出**: alsa_output.platform-nau8822-sound.stereo-fallback ✓
4. **Active Port**: analog-output-headphones

### 插拔喇叭时 amixer 变化

| 控件 | 拔下喇叭 | 插上喇叭 |
|------|----------|----------|
| Headphone Jack | off | on |
| Headphone Switch | off | on |
| Headphone Volume | 0,0 | 57,57 |
| Headphone Playback Switch | off,off | on,on |
| Speaker Volume | 47,47 | 0,0 ← 自动变0 |

### 关键发现

- 插上喇叭时，Speaker Volume 被自动设为 0
- 插上喇叭时录制的音频，耳机能听到正常声音 → 录音本身没问题
- 但插上喇叭时录制的音频，喇叭播放没声音 → 问题在播放端
- 浏览器视频喇叭声音大 → 硬件没问题

### 待解决

- 插上喇叭时录制的音频，为什么喇叭播放没声音？
- 拔下喇叭录制的音频，喇叭播放声音很小，怎么调大？

### 相关命令

```bash
# 录音
arecord -D hw:1,0 -f S16_LE -r 16000 -c 2 -d 5 test.wav

# 播放
aplay -D plughw:1,0 test.wav

# 检查录音设备
arecord -l

# 查看 amixer 设置
amixer -c 1 contents

# 设置音量
amixer -c 1 cset name='Headphone Volume' 50,50
amixer -c 1 cset name='Speaker Volume' 47,47

# PulseAudio 操作
pactl list sinks short
pactl set-sink-volume alsa_output.platform-nau8822-sound.stereo-fallback 100%
pactl set-sink-port alsa_output.platform-nau8822-sound.stereo-fallback analog-output-headphones
```

### 音频设备信息

- 录音设备: card 1 (rockchip-nau8822), hw:1,0
- 播放设备: card 1 (rockchip-nau8822), plughw:1,0
- 3.5mm口对应 Headphone 通道
- Speaker 通道是板载小喇叭
