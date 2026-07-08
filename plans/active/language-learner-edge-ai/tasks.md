# Tasks: 端侧AI语言学习机

## Now

- [ ] **A1: ELF2环境搭建** — 烧写官方Ubuntu镜像，确认NPU驱动版本，安装基础工具链 (gcc, cmake, python3, git)。验证 `cat /sys/kernel/debug/rknpu/version` 返回的NPU驱动版本。
- [ ] **B1: 研究rkllama完整管线** — Clone并尝试编译rkllama项目，分析其代码结构（VAD→ASR→LLM→TTS如何串联），输出一份管线数据流分析文档。

## Next

- [ ] A2: 音频外设验证 — 用arecord/aplay测试板载麦克风和耳机输出，确认Codec驱动正常
- [ ] A3: MIPI屏点亮 — 连接官方7寸屏，确认显示正常，测试Qt demo
- [ ] B2: sherpa-onnx编译 — 在ELF2上编译sherpa-onnx（开启RKNN支持），运行SenseVoiceSmall demo
- [ ] B3: RKLLM环境搭建 — 编译/安装RKLLM Runtime，加载测试模型，跑通demo
- [ ] C1: 词汇库构建 — 整理CET-4词表(JSON)，设计SQLite schema，编写导入脚本
- [ ] C2: LLM提示词原型 — 在PC上用Qwen2.5-1.5B(CPU版)测试三层提示词架构，调优角色设定

## Later

- [ ] A4: 按键GPIO接入 — 设计按键布局(3-5键)，焊接按键，编写GPIO驱动
- [ ] A5: 3D外壳设计 — Fusion 360建模，参考Retro Lite CM5/The Xela，适配ELF2板型
- [ ] A6: 系统镜像制作 — 将所有组件打包为可烧写的镜像
- [ ] B4: 管线串联 — VAD→ASR→数据格式转换→LLM→数据格式转换→TTS，跑通端到端
- [ ] B5: 性能优化 — 模型按需加载/卸载，内存管理，目标端到端<3s
- [ ] C3: 词汇状态机实现 — unknown→introduced→attempted→learning→mastered 状态迁移
- [ ] C4: SRS间隔复习引擎 — SM-2算法实现，复习调度
- [ ] C5: Qt对话界面 — 简洁对话气泡UI，状态指示(听/想/说)，词汇学习摘要
- [ ] INT1: 端到端集成 — Line A+B+C串联，完整对话闭环测试
- [ ] INT2: 验收测试 — 按plan.md的8条Acceptance Checks逐条验证

## Blocked

_无阻塞项_

## Done

- [x] 项目规划与调研 — 技术选型、硬件确认、内存预算分析、参考项目调研 (2026-05-14)
- [x] 文档输出 — plan.md, context.md, tasks.md, PRD_端侧AI语言学习机.docx, PROJECT_BRIEF.md (2026-05-14)
