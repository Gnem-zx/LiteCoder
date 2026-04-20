# LiteCoder

[English](README.md) | [中文](README_zh.md)

> 这个项目来自对 Claude Code 源码架构的学习与拆解。在理解其核心思路后，基于一个开源项目做了简化实现：保留高价值的 Agent 编码能力，去掉复杂且不必要的工程负担，让代码更容易阅读、改造和二次开发。


LiteCoder 是一个轻量级的终端 AI 编码助手。它把常见的 Agent 编码流程（读文件、改文件、执行命令、保存会话）整合成一个可直接在本地使用的 CLI 工具。

## 这个项目做了什么

- 提供交互式 REPL：可以直接在终端里持续对话式编程。
- 内置常用工具能力：`read_file`、`edit_file`、`write_file`、`bash`、`glob`、`grep`、`agent`。
- 支持会话持久化：会话可保存、恢复、切换，数据存放在工作目录下的 `.litecoder/`。
- 支持上下文压缩：自动压缩长上下文，降低 token 膨胀。
- 支持持久规则：可通过 `/rule` 维护本地规则，并自动注入系统提示词。
- 支持中英文界面：可通过环境变量或启动参数控制语言。

## 安装与启动

### 1) 安装依赖

如果你使用 `uv`（推荐）：

```bash
uv pip install -e .
```

或使用 pip：

```bash
pip install -e .
```

### 2) 配置模型环境变量

可在工作目录 `.env` 中配置（示例）：

```env
LITECODER_API_KEY=sk-xxxx
LITECODER_BASE_URL=https://api.openai.com/v1
LITECODER_MODEL=gpt-4o
LITECODER_LANG=zh
```

### 3) 启动

```bash
litecoder
```

首次启动会引导你完成基础配置，并把配置写入工作目录。

## 使用方法

常用命令：

```text
/help                 查看帮助
/model [name]         查看/切换模型
/tokens               查看 token 用量
/compact              手动压缩上下文
/diff                 查看当前会话改动文件
/save                 保存当前会话
/sessions             列出已保存会话
/session ...          会话操作（list/new/switch/save/current）
/rule ...             规则操作（list/add/del/clear）
/reset                清空当前对话历史
quit                  退出
```

## 使用示例

### 示例 1：修复代码

```text
你 > 读取 src/main.py，修复导入错误并给出最小改动
```

模型会按需调用工具（如 `read_file`、`edit_file`），并返回修改结果。

### 示例 2：保存并切换会话

```text
/save
/sessions
/session switch session_1710000000
```

### 示例 3：添加长期规则

```text
/rule add 修改代码前先读取目标文件
/rule add 提交答案时优先给最小改动方案
```

添加后会自动应用到后续对话。

## 项目结构（简版）

```text
litecoder/
  cli.py         交互入口与命令处理
  agent.py       Agent 循环与工具调度
  llm.py         LLM 调用与流式处理
  context.py     上下文压缩策略
  session.py     会话存取
  prompt.py      系统提示词拼装
  tools/         工具实现
```

## 致谢

感谢源作者 [何宇峰](https://github.com/he-yufeng) 及其 CoreCoder 相关开源工作与架构研究分享，为本项目提供了非常重要的启发与参考。
