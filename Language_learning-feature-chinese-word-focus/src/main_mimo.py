#!/usr/bin/env python3
"""端侧AI语言学习机 — Line C v2 入口（MiMo 版本）。

使用小米 MiMo API，配置更快的中文响应。

启动方式：
    python src/main_mimo.py --voice --asr sensevoice --llm cloud --tts piper

环境变量：
    CLOUD_API_KEY   MiMo API 密钥
    CLOUD_API_URL   MiMo API 地址
"""

import os
import sys
import argparse
from pathlib import Path

# 确保 src/ 在 Python 搜索路径中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PyQt5.QtWidgets import QApplication

from line_c.config import DATABASE_PATH
from line_c.engine.vocabulary_repository import VocabularyRepository
from line_c.engine.user_repository import UserRepository
from line_c.engine.chat_session_repository import ChatSessionRepository
from line_c.engine.user_vocabulary_repository import UserVocabularyRepository
from line_c.engine.topic_generator import TopicGenerator
from line_c.engine.rss_feed_fetcher import RSSFeedFetcher
from line_c.llm.mock_llm import MockLLM
from line_c.llm.cloud_llm_mimo import CloudLLMMimo
from line_c.tts.mock_tts import MockTTS
from line_c.tts.paroli_tts import ParoliTTS
from line_c.asr.mock_asr import MockASR
from line_c.asr.sensevoice_asr import SenseVoiceASR
from line_c.hardware.gpio_button import GpioButton
from line_c.ui.main_window import MainWindow


def create_llm(backend: str, model: str = "mimo-v2.5"):
    """根据命令行参数创建对应的 LLM 适配器。"""
    if backend == "cloud":
        # MiMo API 配置（硬编码）
        api_key = "tp-c4o62wkbs8sxpzcbwe9l5qnfczohhex60xa9jd1glov436qm"
        api_url = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
        print(f"使用云端 API: {api_url}")
        print(f"使用模型: {model}")
        # MiMo 配置
        return CloudLLMMimo(
            api_url=api_url,
            api_key=api_key,
            model=model,
            max_tokens=500,      # 增加到 500，给思考和回复都留空间
            temperature=0.7,     # 标准温度
            top_p=0.9,           # 较宽词汇范围
            frequency_penalty=0.0,
            presence_penalty=0.0,
        )

    # 默认 mock
    print("使用 MockLLM（预设回复，无需联网）")
    return MockLLM()


def main():
    parser = argparse.ArgumentParser(description="端侧AI语言学习机 - Line C v2 (MiMo)")
    parser.add_argument(
        "--llm", choices=["mock", "cloud"], default="mock",
        help="LLM 后端选择 (默认: mock)"
    )
    parser.add_argument(
        "--voice", action="store_true",
        help="启用语音输入/输出模式（需要麦克风）"
    )
    parser.add_argument(
        "--asr", choices=["mock", "sensevoice"], default="mock",
        help="ASR 后端选择 (默认: mock)"
    )
    parser.add_argument(
        "--tts", choices=["mock", "piper"], default="mock",
        help="TTS 后端选择 (默认: mock)"
    )
    parser.add_argument(
        "--tts-speed", type=float, default=1.0,
        help="TTS 语速 (默认: 1.0, 1.0=正常, <1.0=更快, >1.0=更慢)"
    )
    parser.add_argument(
        "--gpio-chip", default="",
        help="GPIO 芯片路径 (ELF2 上默认 /dev/gpiochip0)"
    )
    parser.add_argument(
        "--gpio-line", type=int, default=17,
        help="GPIO 引脚号 (ELF2 上通过 gpioinfo 确认)"
    )
    args = parser.parse_args()

    # ── 初始化数据库 ──
    db_path = DATABASE_PATH
    vocab_repo = VocabularyRepository(db_path)
    user_repo = UserRepository(db_path)
    chat_session_repo = ChatSessionRepository(db_path)
    user_vocab_repo = UserVocabularyRepository(db_path)

    word_count = vocab_repo.word_count()
    print(f"数据库已连接: {db_path} ({word_count} 词)")
    print(f"角色数: {user_repo.count()}")

    if word_count == 0:
        print("提示：词库为空，请先运行 scripts/import_vocabulary.py 导入词汇数据")
        # 不退出，允许创建角色和浏览界面

    # ── 创建 LLM ──
    llm = create_llm(args.llm, model="mimo-v2.5")

    # ── 创建 TTS ──
    if args.tts == "piper":
        tts = ParoliTTS(length_scale=args.tts_speed, verbose=True)
        if not tts.is_available():
            print("警告：Paroli TTS 不可用，请检查模型路径")
    else:
        tts = MockTTS(verbose=(args.llm == "mock"))

    # ── 创建 RSS 抓取器 + 话题生成器 ──
    rss_fetcher = RSSFeedFetcher()
    # RSS 优先，LLM 为备选
    topic_gen = TopicGenerator(
        llm=llm if args.llm == "cloud" else None,
        rss_fetcher=rss_fetcher,
    )

    # ── Qt 应用 ──
    app = QApplication(sys.argv)

    # ── 主窗口 ──
    window = MainWindow(
        user_repo=user_repo,
        chat_session_repo=chat_session_repo,
        user_vocab_repo=user_vocab_repo,
        vocab_repo=vocab_repo,
        llm=llm,
        tts=tts,
    )
    # 注入话题生成器
    window.topic_feed_page.set_topic_generator(topic_gen)

    # ── 语音模式 ──
    if args.voice:
        if args.asr == "sensevoice":
            asr = SenseVoiceASR(verbose=True)
            if not asr.is_available():
                print("警告：SenseVoice ASR 不可用，请检查模型路径")
        else:
            asr = MockASR(verbose=True)
        print(f"语音模式已启用 (ASR: {asr.name})")

        # GPIO 按键（ELF2 专用，PC 上留空用键盘快捷键）
        gpio_btn = None
        if args.gpio_chip:
            try:
                gpio_btn = GpioButton(
                    chip_path=args.gpio_chip, line_num=args.gpio_line
                )
                gpio_btn.start()
                if gpio_btn.is_available():
                    print(f"  GPIO 按键已连接: {args.gpio_chip} line {args.gpio_line}")
                else:
                    print(f"  GPIO 未检测到（PC 环境？），使用空格键代替")
                    gpio_btn = None
            except Exception as e:
                print(f"  GPIO 初始化失败: {e}，使用空格键代替")
                gpio_btn = None

        window.chat_page.setup_voice(asr=asr, gpio_button=gpio_btn)

    window.show()

    print("VocaLand v2 界面已启动。")
    print("  首页：选择或创建角色")
    print("  话题页：选择话题开始聊天")
    print("  聊天页：点击不认识的单词查释义")
    if args.voice:
        print(f"  语音：空格键录音 / 点击麦克风按钮 (ASR: {asr.name}, TTS: {tts.name})")
    print("  复习页：闪卡式生词复习")
    print("关闭窗口退出。")

    exit_code = app.exec_()

    # 清理
    vocab_repo.close()
    user_repo.close()
    chat_session_repo.close()
    user_vocab_repo.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()