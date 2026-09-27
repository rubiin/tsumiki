---
title: 模块参考
description: 所有 Tsumiki 模块的完整文档
sidebar:
  order: 2
---

## 状态栏

```toml
[modules.bar]
layer = "top"
auto_hide = false
location = "top"
```

## 通知系统

```toml
[modules.notification]
enabled = true
anchor = "top-right"
auto_dismiss = true
```

## Dock

```toml
[modules.dock]
enabled = false
icon_size = 40
behavior = "intellihide"
group_apps = true
orientation = "horizontal"
```

## 概览

```toml
[modules.overview]
enabled = false
layer = "top"
anchor = "center"
```

## 应用启动器

```toml
[modules.launcher]
enabled = false
tooltip = true
icon_size = 35
ignored = []
anchor = "center"
width = 280
height = 320
layout = "grid"
grid_columns = 3
plugins_enabled = true
plugins_dir = ""
```

输入 `/` 可使用 `/calc`、`/translate` 等斜杠命令。插件是放在 `plugins/` 目录中的 Python 文件。

内置插件：

- **`/calc`** — 通过 libqalculate（`qalc`）计算数学、单位和货币，例如 `/calc 100 cm to inches`。
- **`/translate`** — 翻译，自动检测源语言，例如 `/translate bonjour`。
- **`/emoji`** — 离线表情搜索，例如 `/emoji rocket`。
- **`/clipboard-history`** — 搜索 `cliphist` 历史记录并重新复制条目，例如 `/clipboard-history https://`。
- **`/currency`** — 使用实时汇率（Frankfurter，无需 API 密钥）进行货币换算，例如 `/currency 100 usd to eur`。
- **`/kill`** — 搜索运行中的进程并终止选中的进程（SIGTERM，或使用 `-9` 强制 SIGKILL），例如 `/kill firefox`。纯数字参数视为端口——`/kill 3000` 会终止监听 3000 端口的进程。
- **`/search`** — 网页搜索（DuckDuckGo，无需 API 密钥），在浏览器中打开结果并将 URL 复制到剪贴板，例如 `/search fabric hyprland`。

键盘：`上`/`下` 移动选择，`Enter` 激活高亮行，`Escape` 关闭。

## OSD

```toml
[modules.osd]
enabled = false
timeout = 3000
osds = ["brightness", "volume"]
```

## 桌面时钟

```toml
[modules.desktop_clock]
enabled = false
type = "cookie"
layer = "bottom"
nepali_date = false
```

## 桌面语录

```toml
[modules.desktop_quotes]
enabled = false
interval = 600
```
