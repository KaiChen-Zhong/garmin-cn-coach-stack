# Get笔记自动同步

本项目可以不依赖 Claude 手动转存，直接完成：

```text
Garmin 导出 -> 教练复盘 -> Markdown 报告 -> Get笔记
```

## 配置

在 `.env` 填入：

```text
GETNOTE_API_KEY=你的Get笔记OpenAPI Key
GETNOTE_CLIENT_ID=你的Get笔记Client ID
```

Garmin CN 登录仍按 `.env` 中的 Garmin 配置执行。

## 手动运行

今日快速复盘并写入 Get笔记：

```powershell
.\.venv\Scripts\python.exe main.py sync-getnote --daily --cn
```

深度复盘并写入 Get笔记：

```powershell
.\.venv\Scripts\python.exe main.py sync-getnote --deep --cn
```

自定义标题和标签：

```powershell
.\.venv\Scripts\python.exe main.py sync-getnote --daily --cn --title "Garmin 今日复盘 2026-05-29" --tags "Garmin,训练复盘,恢复"
```

## Windows 任务计划

程序：

```text
C:\Users\46713\garmin-cn-coach-stack\.venv\Scripts\python.exe
```

参数：

```text
C:\Users\46713\garmin-cn-coach-stack\main.py sync-getnote --daily --cn
```

起始目录：

```text
C:\Users\46713\garmin-cn-coach-stack
```

推荐频率：

- 每天早上：`sync-getnote --daily --cn`
- 每周末：`sync-getnote --deep --cn`

## MaxHermes / MaxClaw

MaxHermes / MaxClaw 已安装 Get笔记功能后，直接读取 Get笔记里的 Garmin 复盘即可。

提示词：

```text
请读取 Get笔记中最近的 Garmin 今日复盘、周复盘、训练计划和恢复日志。
基于今天、最近7天、上一周、最近30天，分析恢复状态、训练负荷、风险点和今天训练建议。
数据不足时明确指出缺口，不要编造。
```

