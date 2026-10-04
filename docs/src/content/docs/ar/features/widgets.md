---
title: مرجع الأدوات
description: مرجع كامل لتكوين جميع أدوات تسوميكي
sidebar:
  order: 1
---

هذه الصفحة توثق كل أداة متاحة في تسوميكي، وخيارات التكوين الخاصة بها، والقيم الافتراضية، والسلوك.

يتم تكوين الأدوات تحت `[widgets.<الاسم>]` في `config.toml` ويتم وضعها في الشريط عبر أقسام `layout`.

---

## أدوات معلومات النظام

### CPU

تعرض استخدام المعالج مع أوضاع عرض متعددة.

```toml
[widgets.cpu]
label_format = "{icon}"
icon = ""
tooltip = true
round = true
temperature_unit = "celsius"
sensor = "acpitz"
mode = "graph"          # "label" | "graph" | "circular"
graph_length = 4
```

### الذاكرة

تعرض استخدام الذاكرة مع أوضاع عرض متعددة.

```toml
[widgets.memory]
label_format = "{icon}"
icon = ""
tooltip = true
mode = "label"          # "label" | "graph" | "circular"
graph_length = 4
unit = "gb"
```

### GPU

تعرض استخدام بطاقة الرسوميات.

```toml
[widgets.gpu]
label_format = "{icon}"
icon = ""
tooltip = true
mode = "circular"       # "label" | "graph" | "circular"
graph_length = 4
```

### التخزين

تعرض استخدام القرص لمسار معين.

```toml
[widgets.storage]
path = "/"
label_format = "{icon}"
icon = "󰋊"
mode = "label"          # "label" | "graph" | "circular"
tooltip = true
graph_length = 4
unit = "gb"
```

### استخدام الشبكة

يراقب سرعات رفع/تنزيل الشبكة في الوقت الفعلي.

```toml
[widgets.network_usage]
tooltip = true
label_format = "{upload}   {download} "
upload_threshold = 1024
download_threshold = 1024
kb_digits = 0
mb_digits = 2
interval = 2000
```

### التحديثات

يتحقق من تحديثات حزم النظام.

```toml
[widgets.updates]
label_format = "{icon}"
available_icon = "󰏗"
no_updates_icon = "󰏖"
os = "arch"
interval = 3600
tooltip = true
flatpak = true
```

---

## أدوات الأجهزة والطاقة

### البطارية

تعرض مستوى البطارية مع إشعارات.

```toml
[widgets.battery]
full_battery_level = 100
hide_percent_when_full = true
tooltip = true
label_format = "{icon} {percent}"
```

### الصوت

يتحكم في مستوى صوت مخرج الصوت.

```toml
[widgets.volume]
tooltip = true
step_size = 5
```

### السطوع

يتحكم في سطوع الشاشة ولوحة المفاتيح.

```toml
[widgets.brightness]
tooltip = true
step_size = 5
```

### Bluetooth

يدير اتصالات Bluetooth والرؤية.

```toml
[widgets.bluetooth]
label = true
tooltip = true
```

### الميكروفون

يعرض حالة الميكروفون وكتمه.

```toml
[widgets.microphone]
label = false
tooltip = true
label_format = "{icon}"
```

### زر الطاقة

قائمة طاقة النظام مع إيقاف التشغيل وإعادة التشغيل والتعليق والإسبات والقفل وتسجيل الخروج.

```toml
[widgets.power]
icon = "󰐥"
tooltip = true
items_per_row = 3
icon_size = 100
confirm = true
```

### Hypridle

تشغيل/إيقاف مدير الخمول في هيبرلاند.

```toml
[widgets.hypridle]
enabled_icon = ""
disabled_icon = ""
label = true
tooltip = true
```

### Hyprsunset

تشغيل/إيقاف مرشح الضوء الأزرق.

```toml
[widgets.hyprsunset]
temperature = "2800k"
enabled_icon = "󱩌"
disabled_icon = "󰛨"
label = true
tooltip = true
```

---

## أدوات سطح المكتب ومساحات العمل

### مساحات العمل

تعرض أسطح المكتب الافتراضية مع التبديل بالنقر/التمرير.

```toml
[widgets.workspaces]
count = 10
hide_unoccupied = true
style = "numbered"       # "numbered" | "pill" | "icon" | "default" | "underline" | "bubble"
empty_scroll = false
label_format = "{id}"
icon_map = {}
show_special = false
show_urgent = false
```

### عنوان النافذة

يعرض عنوان النافذة المركزة حالياً.

```toml
[widgets.window_title]
icon = true
truncation = true
truncation_size = 50
tooltip = true
fallback = "class"       # "class" | "title"
```

### عدد النوافذ

يعرض عدد النوافذ في مساحة العمل الحالية.

```toml
[widgets.window_count]
label_format = " [{count}]"
hide_when_zero = true
tooltip = true
```

### شريط المهام

يعرض التطبيقات الجارية كأيقونات قابلة للنقر.

```toml
[widgets.taskbar]
icon_size = 22
ignored = []
tooltip = true
show_current_workspace_only = false
```

---

## أدوات التاريخ والوقت والتقويم

### قائمة التاريخ والوقت

تعرض التاريخ/الوقت الحالي مع تقويم منبثق وإشعارات الأحداث.

```toml
[widgets.date_time]
date_format = " %a %b %d,"
calendar = true
clock_format = "12h"   # "12h" | "24h"
```

### ساعة عالمية

تعرض الوقت في مناطق زمنية متعددة.

```toml
[widgets.world_clock]
icon = "󰃰"
use_24hr = true
label_format = "{icon}"
timezones = ["America/New_York", "Asia/Tokyo"]
```

---

## أدوات الوسائط والصوت

### عناصر التحكم في الوسائط MPRIS

تعرض الوسائط قيد التشغيل حالياً مع عناصر تحكم.

```toml
[widgets.mpris]
truncation_size = 20
tooltip = true
label_format = "{title} - {artist}"
hide_when_no_player = true
ignore = []
```

### مرئي الصوت Cava

تصور صوتي في الوقت الفعلي.

```toml
[widgets.cava]
bars = 10
color = "#89b4fa"
```

---

## أدوات مساعدة

### لقطة الشاشة

تلتقط لقطات شاشة مع دعم التعليقات التوضيحية.

```toml
[widgets.screenshot]
path = "Pictures/Screenshots"
icon = "󰄀"
tooltip = true
annotation = true
delayed = false
```

### تسجيل الشاشة

بدء/إيقاف تسجيل الشاشة مع صوت اختياري.

```toml
[widgets.recorder]
path = "Videos/Screencasting"
tooltip = true
audio = true
```

### OCR

استخراج النص من منطقة الشاشة.

```toml
[widgets.ocr]
icon = "󰐳"
tooltip = true
label = false
label_format = "{icon}"
```

### مدير الحافظة

سجل الحافظة مع دعم الصور.

```toml
[widgets.clipboard]
icon = ""
label = false
tooltip = true
show_images = true
enable_pinning = true
```

### مدير USB

إدارة تركيب وإخراج أقراص USB.

```toml
[widgets.usb_manager]
icon = "󰕓"
label = false
tooltip = true
```

---

## أدوات UI والتطبيقات

### الإعدادات السريعة

لوحة إعدادات سريعة شاملة مع معلومات المستخدم وعناصر التحكم والوسائط والاختصارات.

```toml
[widgets.quick_settings]
hover_reveal = false
```

### علبة النظام

علبة النظام لتطبيقات الخلفية.

```toml
[widgets.system_tray]
icon_size = 16
ignored = []
hidden = []
```

### خلفية الشاشة

يفتح نافذة اختيار الخلفية.

```toml
[widgets.wallpaper]
icon = "󰸉"
label = false
tooltip = true
```

### الإعدادات

يفتح واجهة إعدادات التطبيق.

```toml
[widgets.settings]
icon = "󰒓"
tooltip = true
label = false
```

### مبدل الثيمات

التبديل السريع بين الثيمات المثبتة.

```toml
[widgets.theme_switcher]
icon = ""
notify = false
```

### منتقي الرموز التعبيرية

البحث عن وإدراج رموز تعبيرية.

```toml
[widgets.emoji_picker]
icon = ""
label = false
tooltip = true
per_row = 9
per_column = 4
```

### لوحة كانبان

لوحة إدارة مهام بسيطة.

```toml
[widgets.kanban]
icon = "󱞁"
label = false
tooltip = true
```

### مؤقت بومودورو

مؤقت إنتاجية بومودورو.

```toml
[widgets.pomodoro]
icon = "🍅"
label = true
label_text = "Pomo"
tooltip = true
```

### مرافق Git

يعرض معلومات مستودع GitHub.

```toml
[widgets.github_tray]
icon = ""
label = false
tooltip = true
username = "rubiin"
max_repos = 10
```

### Cloudflare WARP

إدارة اتصال VPN لـ Cloudflare WARP.

```toml
[widgets.cloudflare_warp]
label = false
label_text = "WARP"
tooltip = true
```

### مبدل DNS

التبديل السريع بين مزودي DNS.

```toml
[widgets.dns_switcher]
icon = "󰚘"
label = false
label_text = "DNS"
tooltip = true
```

### مراقب IP

يعرض عنوان IP الحالي.

```toml
[widgets.ip_monitor]
icon = "󰖟"
label = false
label_text = "IP"
tooltip = true
```

### الطقس

يعرض أحوال الطقس الحالية لموقع ما.

```toml
[widgets.weather]
location = "kathmandu"
label_format = "{temperature} {condition}"
tooltip = true
temperature_unit = "celsius"
provider = "open-meteo"
```

---

## مجموعات الأدوات والمجموعات القابلة للطي

يمكن تجميع الأدوات مع أنماط مشتركة:

```toml
[[widget_groups]]
widgets = ["workspaces", "window_title"]
spacing = 2
style_classes = ["compact"]

[[collapsible_groups]]
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
tooltip = "أدوات مساعدة"
style_classes = ["utility-tools"]
```

أشر إلى المجموعات في التخطيط باستخدام `@group:N` أو `@collapsible:N` (فهرس يبدأ من صفر):

```toml
[layout]
left_section = ["@group:0", "window_title"]
right_section = ["@group:1", "@collapsible:0", "system_tray"]
```
