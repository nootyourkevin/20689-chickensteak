# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

端侧AI语言学习机 (Edge-AI Language Learner) — 嵌入式竞赛作品。
一台基于飞凌ELF2 (RK3588) 的掌上设备，通过语音对话聊天的方式帮助用户学习英语单词。
所有AI推理 (ASR + LLM + TTS) 完全在端侧运行。

**完整项目文档见 [PROJECT_BRIEF.md](./PROJECT_BRIEF.md)** — 包含硬件规格、技术架构、模型选型、团队分工、时间线和任务状态。

**详细技术规格见 [plans/active/language-learner-edge-ai/plan.md](./plans/active/language-learner-edge-ai/plan.md)**

## Key Constraints

- 主控: 飞凌ELF2 (RK3588, 8GB LPDDR4) — 不可更换
- NPU: 6 TOPS INT8, 3 cores
- OS: Linux 5.10 + Ubuntu 22.04 (ELF2-Desktop)
- UI: Qt 5.15 (预装)
- 开发周期: 4周, 团队3人

## Build, Test, and Development Commands

_待项目代码初始化后补充。_
