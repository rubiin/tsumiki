---
title: 高级配置
description: Tsumiki 高级配置模式
---

熟悉了[配置](/zh-cn/configuring/config)基础后，这些模式可以帮助您进一步优化 Tsumiki。

## 自定义组件

兼容 Waybar 的自定义组件，可运行外部 shell 命令，支持可配置的输出解析和点击处理。

```toml
[[widgets.custom_widget]]
id = "volume"
exec = "pamixer --get-volume"
label_format = "󰕾 {}%"
interval = 1000
on_scroll_up = "pamixer -i 5"
on_scroll_down = "pamixer -d 5"
exec_on_event = true

[layout]
left_section = ["@custom_widget:volume", "workspaces"]
```

完整配置选项：

| 键                 | 类型   | 默认值    | 描述                                              |
| ------------------ | ------ | --------- | ------------------------------------------------- |
| `id`               | string | —         | 在布局中引用的唯一标识符 (`@custom_widget:my-id`) |
| `exec`             | string | —         | 要执行的 shell 命令；纯点击按钮可省略             |
| `icon`             | string | —         | 静态图标字形，等同于 `format_icons.default`       |
| `interval`         | int    | `0`       | 刷新间隔（毫秒），0 = 仅执行一次                  |
| `return_type`      | string | `"plain"` | 输出格式：`"plain"` 或 `"json"`                   |
| `label_format`     | string | `"{}"`    | 格式字符串，`{}` 将被输出替换                     |
| `format`           | string | —         | Waybar 中 `label_format` 的名称                   |
| `exec_on_event`    | bool   | `false`   | 点击/滚动后重新执行命令                           |
| `max_length`       | int    | `0`       | 最大文本长度（0 = 无限制）                        |
| `min_length`       | int    | `0`       | 最小文本长度（用空格填充）                        |
| `rotate`           | int    | `0`       | 文本旋转角度（度）                                |
| `tooltip`          | bool   | `true`    | 显示带输出的工具提示                              |
| `tooltip_format`   | string | —         | 工具提示格式字符串                                |
| `tooltip_text`     | string | —         | 静态工具提示，用于输出永不变化的组件              |
| `on_click`         | string | —         | 左键单击命令                                      |
| `on_click_right`   | string | —         | 右键单击命令                                      |
| `on_click_middle`  | string | —         | 中键单击命令                                      |
| `on_scroll_up`     | string | —         | 向上滚动命令                                      |
| `on_scroll_down`   | string | —         | 向下滚动命令                                      |
| `signal`           | int    | —         | sig* 事件触发器的信号编号                         |
| `restart_interval` | int    | —         | 持久脚本的重启间隔                                |

## 组件组

将具有共享间距和样式的组件分组：
在布局中使用 `@group:N`（从零开始的索引）或 `@group:id`（文本 ID）引用组：

```toml
[[widget_groups]]
id = "sys-group"
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]
```

在布局中使用 `@group:sys-group` 引用。

```toml
[layout]
right_section = ["@group:sys-group", "system_tray"]
```

## 可折叠组

将较少使用的组件隐藏在切换按钮后面：

```toml
[[collapsible_groups]]
id = "utility-tools"
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
label_format = "󰍽"
tooltip = "工具"
style_classes = ["utility-tools"]
```

在布局中使用 `@collapsible:utility-tools` 引用。

```toml

right_section = ["@collapsible:utility-tools", "system_tray"]

```
