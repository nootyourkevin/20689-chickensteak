#!/bin/bash
# 传输 asrtest.py 到 ELF2 开发板的脚本

# 配置信息（请修改为你的实际信息）
ELF2_IP="192.168.1.100"  # ← 修改为你的 ELF2 IP 地址
ELF2_USER="elf"          # 默认用户名
ELF2_PASS=""             # 如果需要密码，填在这里（否则用密钥）

# 源文件路径
SOURCE_FILE="Language_learning-feature-chinese-word-focus/src/line_c/asr/asrtest.py"

# 目标路径（ELF2 上的 ASR 目录）
TARGET_DIR="/home/elf/language_learner/src/line_c/asr/"

echo "=== 传输 asrtest.py 到 ELF2 ==="
echo "源文件: $SOURCE_FILE"
echo "目标: $ELF2_USER@$ELF2_IP:$TARGET_DIR"
echo ""

# 检查源文件是否存在
if [ ! -f "$SOURCE_FILE" ]; then
    echo "错误: 源文件不存在: $SOURCE_FILE"
    exit 1
fi

# 创建目标目录（如果不存在）
echo "创建目标目录..."
ssh $ELF2_USER@$ELF2_IP "mkdir -p $TARGET_DIR" 2>/dev/null

# 传输文件
echo "传输文件..."
if [ -n "$ELF2_PASS" ]; then
    # 使用 sshpass（如果安装了的话）
    sshpass -p "$ELF2_PASS" scp "$SOURCE_FILE" "$ELF2_USER@$ELF2_IP:$TARGET_DIR"
else
    # 使用密钥认证
    scp "$SOURCE_FILE" "$ELF2_USER@$ELF2_IP:$TARGET_DIR"
fi

# 检查传输结果
if [ $? -eq 0 ]; then
    echo "✅ 传输成功！"
    echo ""
    echo "在 ELF2 上测试："
    echo "  ssh $ELF2_USER@$ELF2_IP"
    echo "  cd $TARGET_DIR"
    echo "  python3 -m asrtest"
else
    echo "❌ 传输失败"
    echo ""
    echo "请检查："
    echo "1. ELF2 IP 地址是否正确"
    echo "2. 网络连接是否正常"
    echo "3. SSH 服务是否开启"
    echo "4. 用户名和密码是否正确"
fi