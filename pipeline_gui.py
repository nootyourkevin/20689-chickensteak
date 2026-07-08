#!/usr/bin/env python3
"""
端侧AI语言学习机 — GUI版管线
按住按钮录音，松开停止，自动识别→回复→播放

用法:
    python3 pipeline_gui.py
"""

import subprocess
import os
import sys
import time
import threading
import re
import tkinter as tk

# ============================================================
# 配置（和 pipeline_mvp.py 相同）
# ============================================================

RECORD_DEVICE = "hw:1,0"
RECORD_RATE = 16000
RECORD_CHANNELS = 2
RECORD_FORMAT = "S16_LE"

ASR_SCRIPT = "/root/SenseVoiceSmall-RKNN2/sensevoice_rknn.py"
ASR_PYTHON = "python3"

LLM_DEMO = "/home/elf/DeepSeek-R1-Distill-Qwen-1.5B_RKLLM/demo_Linux_aarch64/llm_demo"
LLM_MODEL = "/home/elf/DeepSeek-R1-Distill-Qwen-1.5B_RKLLM/DeepSeek-R1-Distill-Qwen-1.5B_W8A8_RK3588.rkllm"
LLM_LD_LIBRARY = "/home/elf/DeepSeek-R1-Distill-Qwen-1.5B_RKLLM/demo_Linux_aarch64/lib"

TTS_CLI = "/root/paroli-daemon/build/paroli-cli"
TTS_ENCODER = "/root/paroli-daemon/build/streaming-piper/ljspeech/encoder.onnx"
TTS_DECODER = "/root/paroli-daemon/build/streaming-piper/ljspeech/decoder.rknn"
TTS_CONFIG = "/root/paroli-daemon/build/streaming-piper/ljspeech/config.json"
TTS_ESPEAK_DATA = "/root/piper_phonemize/share/espeak-ng-data"
TTS_LD_LIBRARY = "/root/paroli-daemon/build/lib:/root/onnxruntime-linux-aarch64-1.14.1/lib:/root/piper_phonemize/lib"

PLAY_DEVICE = "plughw:1,0"
TMP_DIR = "/tmp/pipeline_gui"


# ============================================================
# 解析函数（从 pipeline_mvp.py 复制）
# ============================================================

def parse_asr_output(output):
    texts = []
    for line in output.strip().split('\n'):
        if '[Channel' not in line:
            continue
        content = re.sub(r'<\|[^|]*\|>', '', line)
        content = re.sub(r'\[[^\]]*\]', '', content)
        content = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d+\s+\w\s*', '', content)
        content = content.strip()
        if content:
            texts.append(content)
    return ' '.join(texts) if texts else ""


def parse_llm_output(output):
    match = re.search(r'robot:\s*(.*)', output, re.DOTALL)
    if not match:
        match = re.search(r'(?:回复|answer|response)[:：]\s*(.*)', output, re.DOTALL)
    reply = match.group(1) if match else output
    reply = re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL)
    reply = re.sub(r'\s*user:\s*$', '', reply)
    return reply.strip()


# ============================================================
# 管线步骤
# ============================================================

def run_cmd(cmd, desc="", timeout=60, input_data=None, env=None):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=timeout, input=input_data, env=env)
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1
    except Exception as e:
        return "", str(e), -1


def step_convert_to_mono(input_wav, output_wav):
    cmd = ["ffmpeg", "-y", "-i", input_wav, "-ac", "1", "-ar", str(RECORD_RATE), output_wav]
    _, _, rc = run_cmd(cmd, timeout=10)
    return rc


def step_asr(audio_file):
    cmd = [ASR_PYTHON, ASR_SCRIPT, "--audio_file", audio_file]
    stdout, stderr, rc = run_cmd(cmd, timeout=60)
    if rc == 0:
        return parse_asr_output(stdout + "\n" + stderr)
    return None


def step_llm(user_text):
    import threading as _threading
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = LLM_LD_LIBRARY
    cmd = [LLM_DEMO, LLM_MODEL, "2048", "4096"]

    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=env)
        proc.stdin.write(user_text + "\n")
        proc.stdin.flush()

        output_lines = []
        done = _threading.Event()

        def reader():
            for line in proc.stdout:
                output_lines.append(line)
                if line.strip().endswith("user:") or line.strip() == "user:":
                    done.set()
                    break

        t = _threading.Thread(target=reader, daemon=True)
        t.start()
        done.wait(timeout=60)
        time.sleep(0.5)

        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

        return parse_llm_output(''.join(output_lines))
    except:
        try:
            proc.kill()
        except:
            pass
        return None


def step_tts(text, output_wav):
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = TTS_LD_LIBRARY
    cmd = [TTS_CLI, "--encoder", TTS_ENCODER, "--decoder", TTS_DECODER,
           "-c", TTS_CONFIG, "--espeak_data", TTS_ESPEAK_DATA, "-f", output_wav]
    _, _, rc = run_cmd(cmd, timeout=30, input_data=text, env=env)
    return rc


def step_play(wav_file):
    cmd = ["aplay", "-D", PLAY_DEVICE, wav_file]
    run_cmd(cmd, timeout=30)


# ============================================================
# GUI
# ============================================================

class VoiceAssistantGUI:
    def __init__(self):
        os.makedirs(TMP_DIR, exist_ok=True)

        self.root = tk.Tk()
        self.root.title("VocaAI - 语言学习机")
        self.root.geometry("400x300")
        self.root.configure(bg="#1a1a2e")

        # 状态标签
        self.status_label = tk.Label(
            self.root, text="准备就绪", font=("Arial", 14),
            fg="white", bg="#1a1a2e"
        )
        self.status_label.pack(pady=20)

        # 对话显示
        self.chat_text = tk.Text(
            self.root, height=8, width=45, font=("Arial", 11),
            bg="#16213e", fg="white", wrap=tk.WORD
        )
        self.chat_text.pack(pady=10, padx=20)

        # 录音按钮
        self.record_btn = tk.Button(
            self.root, text="🎤 按住说话", font=("Arial", 16),
            bg="#e94560", fg="white", width=15, height=2,
            relief=tk.RAISED, bd=3
        )
        self.record_btn.pack(pady=20)

        # 绑定按下/松开事件
        self.record_btn.bind("<ButtonPress-1>", self.on_press)
        self.record_btn.bind("<ButtonRelease-1>", self.on_release)

        # 录音进程
        self.record_proc = None
        self.is_recording = False
        self.processing = False

    def on_press(self, event):
        """按下按钮，开始录音"""
        if self.processing:
            return

        self.is_recording = True
        self.record_btn.configure(text="🔴 录音中...", bg="#ff6b6b")
        self.status_label.configure(text="正在录音...")

        # 启动 arecord 录音
        raw_wav = os.path.join(TMP_DIR, "record_raw.wav")
        self.record_proc = subprocess.Popen([
            "arecord", "-D", RECORD_DEVICE,
            "-f", RECORD_FORMAT, "-r", str(RECORD_RATE),
            "-c", str(RECORD_CHANNELS), raw_wav
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def on_release(self, event):
        """松开按钮，停止录音并处理"""
        if not self.is_recording:
            return

        self.is_recording = False
        self.processing = True
        self.record_btn.configure(text="⏳ 处理中...", bg="#gray")
        self.status_label.configure(text="正在识别...")

        # 停止录音
        if self.record_proc:
            self.record_proc.terminate()
            self.record_proc.wait()
            self.record_proc = None

        # 在后台线程处理管线
        threading.Thread(target=self.process_pipeline, daemon=True).start()

    def process_pipeline(self):
        """完整管线：ASR → LLM → TTS → 播放"""
        raw_wav = os.path.join(TMP_DIR, "record_raw.wav")
        mono_wav = os.path.join(TMP_DIR, "record_mono.wav")
        tts_wav = os.path.join(TMP_DIR, "tts_output.wav")

        try:
            # 转单声道
            if step_convert_to_mono(raw_wav, mono_wav) != 0:
                self.update_status("❌ 转换失败")
                return

            # ASR
            self.root.after(0, lambda: self.status_label.configure(text="正在识别..."))
            user_text = step_asr(mono_wav)
            if not user_text:
                self.update_status("❌ 识别失败")
                return
            self.add_chat("你", user_text)

            # LLM
            self.root.after(0, lambda: self.status_label.configure(text="AI思考中..."))
            reply = step_llm(user_text)
            if not reply:
                self.update_status("❌ 回复失败")
                return
            self.add_chat("Leo", reply)

            # TTS
            self.root.after(0, lambda: self.status_label.configure(text="语音合成中..."))
            if step_tts(reply, tts_wav) != 0:
                self.update_status("❌ 合成失败")
                return

            # 播放
            self.root.after(0, lambda: self.status_label.configure(text="播放中..."))
            step_play(tts_wav)

            self.update_status("✅ 完成！再说一句吧")

        except Exception as e:
            self.update_status(f"❌ 错误: {e}")
        finally:
            self.processing = False
            self.root.after(0, lambda: self.record_btn.configure(
                text="🎤 按住说话", bg="#e94560"
            ))

    def update_status(self, text):
        self.root.after(0, lambda: self.status_label.configure(text=text))

    def add_chat(self, speaker, text):
        self.root.after(0, lambda: self.chat_text.insert(
            tk.END, f"{speaker}: {text}\n\n"
        ))
        self.root.after(0, lambda: self.chat_text.see(tk.END))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    gui = VoiceAssistantGUI()
    gui.run()
