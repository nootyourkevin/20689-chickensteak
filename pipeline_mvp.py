#!/usr/bin/env python3
"""
端侧AI语言学习机 — MVP管线串联
ASR → LLM → TTS 端到端测试

用法:
    python3 pipeline_mvp.py

流程:
    1. 录音 (arecord, 5秒)
    2. 转单声道 (ffmpeg)
    3. ASR识别 (sensevoice_rknn.py)
    4. LLM生成回复 (llm_demo)
    5. TTS合成语音 (paroli-cli)
    6. 播放音频 (aplay)
"""

import subprocess
import os
import sys
import time
import tempfile
import signal

# ============================================================
# 配置 — 根据你的实际路径修改
# ============================================================

# 录音参数
RECORD_DEVICE = "hw:1,0"       # 录音设备 (card 1)
RECORD_RATE = 16000            # 采样率
RECORD_CHANNELS = 2            # 立体声录音
RECORD_DURATION = 5            # 录音时长(秒)
RECORD_FORMAT = "S16_LE"       # 格式

# ASR
ASR_SCRIPT = "/root/SenseVoiceSmall-RKNN2/sensevoice_rknn.py"
ASR_PYTHON = "python3"

# LLM
LLM_DEMO = "/home/elf/DeepSeek-R1-Distill-Qwen-1.5B_RKLLM/demo_Linux_aarch64/llm_demo"
LLM_MODEL = "/home/elf/DeepSeek-R1-Distill-Qwen-1.5B_RKLLM/DeepSeek-R1-Distill-Qwen-1.5B_W8A8_RK3588.rkllm"
LLM_LD_LIBRARY = "/home/elf/DeepSeek-R1-Distill-Qwen-1.5B_RKLLM/demo_Linux_aarch64/lib"

# TTS
TTS_CLI = "/root/paroli-daemon/build/paroli-cli"
TTS_ENCODER = "/root/paroli-daemon/build/streaming-piper/ljspeech/encoder.onnx"
TTS_DECODER = "/root/paroli-daemon/build/streaming-piper/ljspeech/decoder.rknn"
TTS_CONFIG = "/root/paroli-daemon/build/streaming-piper/ljspeech/config.json"
TTS_ESPEAK_DATA = "/root/piper_phonemize/share/espeak-ng-data"
TTS_LD_LIBRARY = "/root/paroli-daemon/build/lib:/root/onnxruntime-linux-aarch64-1.14.1/lib:/root/piper_phonemize/lib"

# 播放设备
PLAY_DEVICE = "plughw:1,0"

# 临时文件目录
TMP_DIR = "/tmp/pipeline_mvp"


# ============================================================
# 工具函数
# ============================================================

def run_cmd(cmd, desc="", timeout=60, input_data=None, env=None):
    """运行命令，返回 (stdout, stderr, returncode)"""
    print(f"  [{desc}] {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_data,
            env=env,
        )
        if result.returncode != 0:
            print(f"  [错误] {desc} 失败 (code {result.returncode})")
            print(f"  stderr: {result.stderr[:500]}")
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        print(f"  [错误] {desc} 超时 ({timeout}s)")
        return "", "timeout", -1
    except Exception as e:
        print(f"  [错误] {desc} 异常: {e}")
        return "", str(e), -1


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def cleanup():
    """清理临时文件"""
    # 可选：保留临时文件用于调试
    pass


# ============================================================
# 管线步骤
# ============================================================

def step_record(output_wav):
    """Step 1: 录音"""
    print("\n🎤 Step 1: 录音...")
    cmd = [
        "arecord",
        "-D", RECORD_DEVICE,
        "-f", RECORD_FORMAT,
        "-r", str(RECORD_RATE),
        "-c", str(RECORD_CHANNELS),
        "-d", str(RECORD_DURATION),
        output_wav,
    ]
    stdout, stderr, rc = run_cmd(cmd, desc="录音", timeout=RECORD_DURATION + 5)
    if rc == 0:
        print(f"  ✅ 录音完成: {output_wav}")
    return rc


def step_convert_to_mono(input_wav, output_wav):
    """Step 2: 立体声转单声道"""
    print("\n🔄 Step 2: 转单声道...")
    cmd = [
        "ffmpeg", "-y",
        "-i", input_wav,
        "-ac", "1",
        "-ar", str(RECORD_RATE),
        output_wav,
    ]
    stdout, stderr, rc = run_cmd(cmd, desc="转单声道", timeout=10)
    if rc == 0:
        print(f"  ✅ 转换完成: {output_wav}")
    return rc


def step_asr(audio_file):
    """Step 3: ASR语音识别"""
    print("\n👂 Step 3: ASR识别...")
    cmd = [ASR_PYTHON, ASR_SCRIPT, "--audio_file", audio_file]
    stdout, stderr, rc = run_cmd(cmd, desc="ASR", timeout=60)
    if rc == 0:
        # ASR的日志输出在stderr，识别结果也在stderr的日志行里
        # 合并stdout和stderr一起解析
        combined = stdout + "\n" + stderr
        text = parse_asr_output(combined)
        if not text:
            # fallback: 尝试只解析stdout
            text = parse_asr_output(stdout)
        print(f"  ✅ 识别结果: {text}")
        return text
    return None


def parse_asr_output(output):
    """
    解析 sensevoice_rknn.py 输出，提取识别文本。
    格式示例:
        2026-07-04 00:44:22,717 I [sensevoice_rknn.py:1393] [Channel 0] [0.71s - 3.14s] <|en|><|EMO_UNKNOWN|><|Speech|><|woitn|>喂
    或:
        [Channel 0] [0.71s - 3.14s] <|en|><|EMO_UNKNOWN|><|Speech|><|woitn|>喂
    """
    import re

    texts = []
    for line in output.strip().split('\n'):
        # 匹配包含 [Channel X] 的行
        if '[Channel' not in line:
            continue
        # 移除 <|...|> 标签
        content = re.sub(r'<\|[^|]*\|>', '', line)
        # 移除 [...] 方括号内容（时间戳、Channel等）
        content = re.sub(r'\[[^\]]*\]', '', content)
        # 移除日志时间戳 (2026-07-04 00:44:22,717 I)
        content = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d+\s+\w\s*', '', content)
        content = content.strip()
        if content:
            texts.append(content)

    return ' '.join(texts) if texts else ""


def step_llm(user_text):
    """
    Step 4: LLM生成回复
    llm_demo 是交互式的：user: 输入 → robot: 回复 → user: (等待下一轮)
    策略：启动进程，发送文本，用线程读取输出，看到下一个 "user:" 提示时停止。
    """
    print("\n🧠 Step 4: LLM生成回复...")
    print(f"  输入: {user_text}")

    import threading
    import time

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = LLM_LD_LIBRARY

    cmd = [LLM_DEMO, LLM_MODEL, "2048", "4096"]

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        # 发送用户文本
        proc.stdin.write(user_text + "\n")
        proc.stdin.flush()

        # 用线程读取输出，直到看到下一个 "user:" 提示
        output_lines = []
        done = threading.Event()

        def reader():
            for line in proc.stdout:
                output_lines.append(line)
                # 看到下一个 "user:" 提示说明回复完成
                if line.strip().endswith("user:") or line.strip() == "user:":
                    done.set()
                    break

        t = threading.Thread(target=reader, daemon=True)
        t.start()

        # 等待回复完成，最多60秒
        done.wait(timeout=60)
        time.sleep(0.5)  # 多等一下确保数据读完

        # 终止进程
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

        raw_output = ''.join(output_lines)
        reply = parse_llm_output(raw_output)

        if reply:
            print(f"  ✅ LLM回复: {reply}")
            return reply
        else:
            print(f"  ❌ LLM无回复，原始输出: {raw_output[:500]}")
            return None

    except Exception as e:
        print(f"  ❌ LLM异常: {e}")
        try:
            proc.kill()
        except:
            pass
        return None


def parse_llm_output(output):
    """
    解析 llm_demo 输出，提取 robot 的回复文本。
    格式示例：
        user: 你是谁
        robot: <think>
        ...
        </think>        您好！我是DeepSeek-R1...

        user:
    """
    import re

    # 找到 "robot:" 后面的内容
    match = re.search(r'robot:\s*(.*)', output, re.DOTALL)
    if not match:
        # fallback: 尝试找最后一个冒号后的内容
        match = re.search(r'(?:回复|answer|response)[:：]\s*(.*)', output, re.DOTALL)

    if match:
        reply = match.group(1)
    else:
        reply = output

    # 移除 <think>...</think> 标签及其内容
    reply = re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL)

    # 移除末尾的 "user:" 提示
    reply = re.sub(r'\s*user:\s*$', '', reply)

    # 移除多余空白
    reply = reply.strip()

    return reply


def step_tts(text, output_wav):
    """
    Step 5: TTS语音合成
    paroli-cli 通过 stdin 读取文本，-f 指定输出wav文件。
    """
    print("\n🔊 Step 5: TTS合成...")

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = TTS_LD_LIBRARY

    cmd = [
        TTS_CLI,
        "--encoder", TTS_ENCODER,
        "--decoder", TTS_DECODER,
        "-c", TTS_CONFIG,
        "--espeak_data", TTS_ESPEAK_DATA,
        "-f", output_wav,
    ]

    # 通过 stdin 传入文本
    stdout, stderr, rc = run_cmd(cmd, desc="TTS", timeout=30, input_data=text, env=env)
    if rc == 0:
        print(f"  ✅ TTS完成: {output_wav}")
    return rc


def step_play(wav_file):
    """Step 6: 播放音频"""
    print("\n🔈 Step 6: 播放音频...")
    cmd = ["aplay", "-D", PLAY_DEVICE, wav_file]
    stdout, stderr, rc = run_cmd(cmd, desc="播放", timeout=30)
    if rc == 0:
        print("  ✅ 播放完成")
    return rc


# ============================================================
# 主流程
# ============================================================

def run_pipeline():
    """运行一次完整的对话管线"""
    ensure_dir(TMP_DIR)

    # 临时文件路径
    raw_wav = os.path.join(TMP_DIR, "record_raw.wav")
    mono_wav = os.path.join(TMP_DIR, "record_mono.wav")
    tts_wav = os.path.join(TMP_DIR, "tts_output.wav")

    print("=" * 60)
    print("  端侧AI语言学习机 — MVP管线测试")
    print("=" * 60)

    start_time = time.time()

    # Step 1: 录音
    if step_record(raw_wav) != 0:
        print("\n❌ 录音失败，管线终止")
        return False

    # Step 2: 转单声道
    if step_convert_to_mono(raw_wav, mono_wav) != 0:
        print("\n❌ 转换失败，管线终止")
        return False

    # Step 3: ASR识别
    user_text = step_asr(mono_wav)
    if not user_text:
        print("\n❌ ASR识别失败，管线终止")
        return False

    # Step 4: LLM生成回复
    reply_text = step_llm(user_text)
    if not reply_text:
        print("\n❌ LLM生成失败，管线终止")
        return False

    # Step 5: TTS合成
    if step_tts(reply_text, tts_wav) != 0:
        print("\n❌ TTS合成失败，管线终止")
        return False

    # Step 6: 播放
    if step_play(tts_wav) != 0:
        print("\n❌ 播放失败")
        return False

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print(f"  ✅ 管线完成！端到端耗时: {elapsed:.1f}s")
    print("=" * 60)
    return True


def run_loop():
    """循环对话模式"""
    print("\n🎤 进入循环对话模式 (Ctrl+C 退出)\n")

    while True:
        try:
            success = run_pipeline()
            if not success:
                print("\n管线失败，是否重试？(y/n)")
                if input().strip().lower() != 'y':
                    break
            print("\n按 Enter 继续下一轮对话...")
            input()
        except KeyboardInterrupt:
            print("\n\n👋 退出对话")
            break


# ============================================================
# 入口
# ============================================================

def test_asr():
    """单独测试ASR"""
    print("=== 测试 ASR ===")
    wav = input("输入wav文件路径: ").strip()
    if not wav:
        wav = os.path.join(TMP_DIR, "record_mono.wav")
    result = step_asr(wav)
    print(f"识别结果: {result}")


def test_llm():
    """单独测试LLM"""
    print("=== 测试 LLM ===")
    try:
        text = input("输入测试文本 (默认: '你是谁'): ").strip()
    except UnicodeDecodeError:
        # 终端编码问题，用默认值
        text = ""
    if not text:
        text = "你是谁"
    result = step_llm(text)
    print(f"LLM回复: {result}")


def test_tts():
    """单独测试TTS"""
    print("=== 测试 TTS ===")
    text = input("输入英文文本 (默认: 'Hello, how are you?'): ").strip()
    if not text:
        text = "Hello, how are you?"
    output = os.path.join(TMP_DIR, "test_tts.wav")
    ensure_dir(TMP_DIR)
    rc = step_tts(text, output)
    if rc == 0:
        print(f"播放合成音频...")
        step_play(output)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--loop":
            run_loop()
        elif arg == "--test-asr":
            test_asr()
        elif arg == "--test-llm":
            test_llm()
        elif arg == "--test-tts":
            test_tts()
        elif arg == "--help":
            print("用法:")
            print("  python3 pipeline_mvp.py           # 运行一次完整管线")
            print("  python3 pipeline_mvp.py --loop    # 循环对话模式")
            print("  python3 pipeline_mvp.py --test-asr  # 单独测试ASR")
            print("  python3 pipeline_mvp.py --test-llm  # 单独测试LLM")
            print("  python3 pipeline_mvp.py --test-tts  # 单独测试TTS")
        else:
            print(f"未知参数: {arg}，使用 --help 查看用法")
    else:
        run_pipeline()
