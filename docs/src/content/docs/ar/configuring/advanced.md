---
title: إعدادات متقدمة
description: أنماط إعدادات متقدمة لتسوميكي
---

بمجرد أن تصبح مرتاحاً مع أساسيات [الإعدادات](/ar/configuring/config)، هذه الأنماط تساعدك في ضبط تسوميكي أكثر.

## ويدجت مخصصة

ويدجت مخصصة متوافقة مع Waybar تقوم بتشغيل أوامر shell خارجية مع تحليل مخرجات قابل للتكوين ومعالجة النقرات.

```toml
[[widgets.custom_widget]]
id = "volume"
exec = "pamixer --get-volume"
format = "󰕾 {}%"
interval = 1
on_scroll_up = "pamixer -i 5"
on_scroll_down = "pamixer -d 5"
exec_on_event = true

[layout]
left_section = ["@custom_widget:volume", "workspaces"]
```

خيارات التهيئة الكاملة:

| المفتاح            | النوع  | الافتراضي | الوصف                                                 |
| ------------------ | ------ | --------- | ----------------------------------------------------- |
| `id`               | string | —         | معرف فريد للإشارة في التخطيط (`@custom_widget:معرفي`) |
| `exec`             | string | مطلوب     | أمر shell للتنفيذ                                     |
| `interval`         | int    | `0`       | فترة التحديث بالثواني (0 = تنفيذ مرة واحدة)           |
| `return_type`      | string | `"plain"` | تنسيق المخرجات: `"plain"` أو `"json"`                 |
| `label_format`     | string | `"{}"`    | سلسلة تنسيق حيث يتم استبدال `{}` بالمخرجات            |
| `exec_on_event`    | bool   | `false`   | إعادة تشغيل الأمر بعد النقر/التمرير                   |
| `max_length`       | int    | `0`       | الحد الأقصى لطول النص (0 = بدون حد)                   |
| `min_length`       | int    | `0`       | الحد الأدنى لطول النص (يملأ بمسافات)                  |
| `rotate`           | int    | `0`       | تدوير النص بالدرجات                                   |
| `tooltip`          | bool   | `true`    | إظهار تلميح مع المخرجات                               |
| `tooltip_format`   | string | —         | سلسلة تنسيق التلميح                                   |
| `on_click`         | string | —         | أمر النقر الأيسر                                      |
| `on_click_right`   | string | —         | أمر النقر الأيمن                                      |
| `on_click_middle`  | string | —         | أمر النقر الأوسط                                      |
| `on_scroll_up`     | string | —         | أمر التمرير لأعلى                                     |
| `on_scroll_down`   | string | —         | أمر التمرير لأسفل                                     |
| `signal`           | int    | —         | رقم الإشارة لمشغلات الأحداث sig*                      |
| `restart_interval` | int    | —         | فترة إعادة التشغيل للنصوص البرمجية المستمرة           |

## مجموعات الأدوات

جمّع الأدوات مع مسافات وأنماط مشتركة:
أشر إلى مجموعة في تخطيطك باستخدام `@group:N` (فهرس يبدأ من صفر) أو `@group:id` (معرف نصي) :

```toml
[[widget_groups]]
id = "sys-group"
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]
```

أشر في التخطيط باستخدام `@group:sys-group`.

```toml
[layout]
right_section = ["@group:sys-group", "system_tray"]
```

## المجموعات القابلة للطي

أخفِ الأدوات الأقل استخداماً خلف مفتاح:

```toml
[[collapsible_groups]]
id = "utility-tools"
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
tooltip = "أدوات مساعدة"
style_classes = ["utility-tools"]
```

أشر في التخطيط باستخدام `@collapsible:utility-tools`.

```toml

right_section = ["@collapsible:utility-tools", "system_tray"]

```

## مجموعة أزرار مخصصة

مجموعة من أزرار الأوامر المخصصة. يمكن الإشارة إلى كل زر في المجموعة عبر `@custom_button:N` أو `@custom_button:id` :

```toml
[[widgets.custom_buttons]]
id = "firefox"
command = "firefox"
icon = "󰈹"
label_text = "Firefox"
tooltip_text = "فتح متصفح فايرفوكس"
label_format = "{icon}"
label = false
tooltip = true

[layout]
left_section = ["@custom_button:firefox"]
```
