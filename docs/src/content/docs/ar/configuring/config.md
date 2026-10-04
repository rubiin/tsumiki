---
title: إعدادات
description: خيارات إعداد تسوميكي وإعدادات الأدوات
---

يستخدم تسوميكي TOML للإعدادات.

## ملفات الإعدادات

- `config.toml`: الأدوات، التخطيط، الوحدات، سلوك وقت التشغيل.
- `tsumiki.schema.json`: مرجع المخطط النهائي.

:::note
يتطلب المخطط أقسام `widget_groups` و `collapsible_groups` على المستوى الأعلى.
البدء من `example/config.toml` هو الطريقة الأكثر أماناً للبقاء متوافقاً مع المخطط.
:::

## مثال بداية سريعة

```toml
"$schema" = "./tsumiki.schema.json"

[general]
debug = false
auto_restart = true
multi_monitor = false

[layout]
left_section = ["workspaces", "window_title"]
middle_section = ["date_time"]
right_section = ["@group:0", "system_tray", "volume", "battery"]

[[widget_groups]]
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]

[[collapsible_groups]]
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
tooltip = "أدوات مساعدة"
style_classes = ["utility-tools"]

[modules.bar]
layer = "top"
location = "top"
auto_hide = false
auto_hide_timeout = 3000

[widgets.workspaces]
count = 10
hide_unoccupied = true

[widgets.date_time]
date_format = "%b %d %H:%M"

[widgets.volume]
tooltip = true
step_size = 5

[widgets.battery]
label = true
tooltip = true
```

## الأقسام الرئيسية

### `general`

السلوك العام مثل وضع التصحيح، إعادة التشغيل التلقائي، والتحكم بعدة شاشات.

| المفتاح          | النوع | الافتراضي | الوصف                                  |
| ---------------- | ----- | --------- | -------------------------------------- |
| `debug`          | bool  | `false`   | تفعيل التسجيل المفصل                   |
| `auto_restart`   | bool  | `true`    | إعادة التشغيل تلقائياً عند الانهيار    |
| `restart_delay`  | int   | `1500`    | التأخير قبل إعادة التشغيل (مللي ثانية) |
| `multi_monitor`  | bool  | `false`   | نسخ شريط لكل شاشة                      |
| `tooltips`       | bool  | `true`    | تفعيل تلميحات الأدوات                  |
| `check_updates`  | bool  | `false`   | التحقق من تحديثات تسوميكي              |
| `monitor_styles` | bool  | `true`    | مراقبة وإعادة تحميل تغييرات SCSS       |

### `layout`

يتحكم في موضع الأدوات في أقسام الشريط:

- `left_section`
- `middle_section`
- `right_section`

كل قيمة هي قائمة بمعرفات الأدوات. استخدم `@group:N` (فهرس يبدأ من صفر) لمجموعات الأدوات:

```toml
[layout]
left_section = ["@group:0", "window_title"]
middle_section = ["date_time"]
right_section = ["@group:1", "system_tray", "power"]
```

أنواع المرجع المتاحة:

| المرجع             | مثال                 | الوصف                        |
| ------------------ | -------------------- | ---------------------------- |
| اسم الأداة         | `"workspaces"`       | مرجع مباشر للأداة            |
| `@group:N`         | `"@group:0"`         | مجموعة أدوات حسب الفهرس      |
| `@collapsible:N`   | `"@collapsible:0"`   | مجموعة قابلة للطي حسب الفهرس |
| `@custom_button:N` | `"@custom_button:0"` | زر مخصص حسب الفهرس           |

### `modules`

يفعّل ويكوّن وحدات UI الأكبر مثل:

| الوحدة              | المفتاح                  | الوصف                            |
| ------------------- | ------------------------ | -------------------------------- |
| الشريط              | `modules.bar`            | موضع وطبقة اللوحة                |
| الإشعارات           | `modules.notification`   | نظام إشعارات سطح المكتب          |
| الإرساء             | `modules.dock`           | إرساء التطبيقات مع الإخفاء الذكي |
| النظرة العامة       | `modules.overview`       | عرض مساحات العمل                 |
| OSD                 | `modules.osd`            | شاشة عرض للصوت وغيرها            |
| مشغل التطبيقات      | `modules.launcher`       | بحث وتشغيل التطبيقات             |
| ساعة سطح المكتب     | `modules.desktop_clock`  | ساعة سطح مكتب زخرفية             |
| اقتباسات سطح المكتب | `modules.desktop_quotes` | تراكب اقتباسات ملهمة             |
| زوايا الشاشة        | `modules.screen_corners` | زوايا نشطة                       |
| ورقة الغش           | `modules.cheatsheet`     | مرجع اختصارات لوحة المفاتيح      |
| Activate Linux      | `modules.activate_linux` | مؤشر تنشيط النافذة               |

مثال إعدادات الإرساء:

```toml
[modules.dock]
enabled = true
behavior = "intellihide"
show_when_no_windows = false
icon_size = 40
```

راجع [مرجع الوحدات](/ar/features/modules) للخيارات الكاملة.

### `widgets`

إعدادات لكل أداة (أيقونات، تسميات، عتبات، فترات استقصاء، علامات سلوك).

أكثر من 45 أداة متاحة. راجع [مرجع الأدوات](/ar/features/widgets) الكامل لكل خيار.

الأدوات الشائعة تشمل:

| الأداة           | الوصف                             |
| ---------------- | --------------------------------- |
| `workspaces`     | مبدل سطح المكتب الافتراضي         |
| `window_title`   | عنوان النافذة النشطة              |
| `date_time`      | عرض التاريخ/الوقت                 |
| `system_tray`    | أيقونات علبة النظام               |
| `volume`         | التحكم في مستوى الصوت             |
| `battery`        | حالة البطارية                     |
| `cpu`            | مراقب استخدام المعالج             |
| `memory`         | مراقب استخدام الذاكرة             |
| `network_usage`  | مراقب سرعة الشبكة                 |
| `weather`        | أحوال الطقس                       |
| `power`          | قائمة الطاقة (إيقاف التشغيل، إلخ) |
| `quick_settings` | لوحة الإعدادات السريعة            |

## أنماط مساحات العمل

تدعم أداة مساحات العمل ستة أنماط عرض:

```toml
[widgets.workspaces]
style = "numbered"   # "numbered" | "pill" | "icon" | "minimal" | "underline" | "bubble"
```

- **numbered** — أرقام مع مؤشر نشط على شكل حبة (افتراضي)
- **pill** — مؤشرات حبة صغيرة بدون نص
- **icon** — أيقونات Nerd Font مخصصة لكل مساحة عمل
- **minimal** — نظيف وبسيط مع خلفية خفيفة
- **underline** — مساحة العمل النشطة تحصل على حد سفلي، بدون خلفية
- **bubble** — حاويات فقاعية دائرية

## مجموعات الأدوات والمجموعات القابلة للطي

جمّع الأدوات مع مسافات وأنماط مشتركة:

```toml
[[widget_groups]]
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]
```

المجموعات القابلة للطي تخفي الأدوات خلف مفتاح:

```toml
[[collapsible_groups]]
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
tooltip = "أدوات مساعدة"
style_classes = ["utility-tools"]
```

أشر إلى المجموعات في التخطيط باستخدام `@group:N` أو `@collapsible:N`.

## توليد الثيمات بـ Matugen

قم بتوليد لوحات ألوان تلقائياً من خلفية شاشتك:

```toml
[matugen]
enabled = true
wallpaper = "~/Pictures/wallpaper.jpg"
scheme = "scheme-tonal-spot"
mode = "dark"
contrast = 0.0
```

راجع [التثيم مع Matugen](/ar/theming/matugen) للتفاصيل.

## ملاحظة الترحيل

إذا كنت تقوم بالترقية من إصدارات أقدم، راجع [الترحيل من v2 إلى v3](/ar/resources/migration-v2-v3) قبل نسخ كتل الإعدادات القديمة.

## سير العمل الموصى به

1. ابدأ من `example/config.toml`.
2. حافظ على ملفك المخصص صغيراً ومركزاً.
3. غيّر قسماً واحداً في كل مرة.
4. أعد التشغيل باستخدام `./tsumiki.sh -start` للتحقق من السلوك.

## مصدر المرجع

هذه الصفحة هي نظرة عامة عملية.
للحصول على تعريفات كاملة للمفاتيح والقيم الافتراضية، راجع [مرجع الأدوات](/ar/features/widgets) و [مرجع الوحدات](/ar/features/modules).
للمخطط الكامل، استخدم `tsumiki.schema.json` في جذر المشروع.
