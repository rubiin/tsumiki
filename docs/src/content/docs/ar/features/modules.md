---
title: مرجع الوحدات
description: توثيق كامل لجميع وحدات تسوميكي
sidebar:
  order: 2
---

الوحدات هي أسطح واجهة أكبر تتجاوز الشريط، مثل الإرساء والإشعارات والنظرة العامة وOSD. يتم تكوينها تحت `[modules.<الاسم>]` في `config.toml`.

على عكس الأدوات، معظم الوحدات هي نوافذ مستقلة أو تراكبات تحتاج إلى تفعيل صريح.

---

## الشريط

الشريط نفسه هو وحدة. يكوّن الموضع والطبقة وسلوك الإخفاء التلقائي.

```toml
[modules.bar]
layer = "top"           # "top" | "overlay" | "bottom" | "background"
auto_hide = false
auto_hide_timeout = 3000   # مللي ثانية
location = "top"           # "top" | "bottom"
```

- **`layer`**: طبقة هيبرلاند — `top` يُعرض فوق النوافذ، `background` يُعرض تحتها.
- **`auto_hide`**: يخفي الشريط بعد المهلة عند عدم تمرير المؤشر.
- **`location`**: موضع الشريط على الشاشة.

---

## نظام الإشعارات

يعرض إشعارات سطح المكتب عند وصولها، مع التكديس والتجميع وعدم الإزعاج.

```toml
[modules.notification]
enabled = true
anchor = "top-right"
auto_dismiss = true
respect_expire = true
dnd_on_screencast = true
ignored = []
transition_type = "slide-left"       # "slide-left" | "slide-right" | "slide-up" | "slide-down" | "crossfade"
transition_duration = 350
per_app_limits = {}
play_sound = false
max_actions = 3
dismiss_on_hover = false
sound_file = "notification4"
max_lines = 4
max_expanded_lines = 20

[modules.notification.timeout]
low = 3000
normal = 8000
critical = 15000

[modules.notification.persist]
enabled = true
low = true
normal = true
critical = true
max_count = 200
```

- **`anchor`**: موضع الشاشة لنافذة الإشعارات.
- **`auto_dismiss`**: رفض الإشعارات تلقائياً بعد انتهاء مهلة.
- **`respect_expire`**: احترام مهلة انتهاء الصلاحية من مرسل الإشعار.
- **`dnd_on_screencast`**: تفعيل وضع عدم الإزعاج أثناء تسجيل الشاشة.
- **`per_app_limits`**: الحد من الإشعارات لكل تطبيق: `{ "app_name": 5 }`.
- **`persist`**: حفظ الإشعارات على القرص لاسترجاعها بعد إعادة التشغيل.

---

## الإرساء (Dock)

مشغل تطبيقات مثبتة مع الإخفاء الذكي ومعاينات النوافذ وتجميع التطبيقات.

```toml
[modules.dock]
enabled = false
ignored = []
icon_size = 40
behavior = "intellihide"            # "intellihide" | "always_show"
tooltip = false
layer = "top"
show_when_no_windows = false
group_apps = true
truncation_size = 20
orientation = "horizontal"
always_show_focused = true
hide_special_workspace_apps = false
show_launcher = true
launcher_position = "last"          # "first" | "last"
ignored = []
```

- **`behavior`**: `intellihide` يخفي الإرساء عندما تتداخل نافذة؛ `always_show` يبقيه مرئياً.
- **`s`**: يعرض صوراً مصغرة للنوافذ عند تمرير المؤشر.
- **`group_apps`**: يجمع نوافذ متعددة من نفس التطبيق.
- **`show_launcher`**: يضيف أيقونة مشغل تطبيقات إلى الإرساء.
- **`hide_special_workspace_apps`**: يخفي التطبيقات في مساحات العمل الخاصة.

### اختصارات لوحة المفاتيح

| الإجراء                   | الاختصار                      |
| ------------------------- | ----------------------------- |
| التركيز على العميل التالي | `Super+Tab`                   |
| التركيز على العميل السابق | `Super+Shift+Tab`             |
| فتح المشغل                | `Super+Space`                 |
| نقل العميل إلى مساحة عمل  | زر أيمن → "نقل إلى مساحة عمل" |

---

## النظرة العامة (Exposé مساحات العمل)

نظرة عامة بملء الشاشة لجميع مساحات العمل ونوافذها.

```toml
[modules.overview]
enabled = false
layer = "top"
anchor = "center"
transition_type = "crossfade"
transition_duration = 350
```

تفتح باختصار لوحة مفاتيح قابل للتكوين (افتراضي: `Super+W`). تعرض صوراً مصغرة لمساحات العمل مع النقر للتركيز.

---

## مشغل التطبيقات

مشغل تطبيقات يعمل بلوحة المفاتيح مع البحث وتخطيط شبكة/قائمة والسحب للتثبيت.

```toml
[modules.launcher]
enabled = false
tooltip = true
icon_size = 35
anchor = "center"
width = 280
height = 320
layout = "grid"                    # "grid" | "list"
grid_columns = 3
grid_spacing = 12
plugins_enabled = true              # إضافات الأوامر المائلة (/calc, /translate)
plugins_dir = ""                    # الافتراضي: <config>/plugins
```

- **`layout`**: `grid` يعرض أيقونات التطبيقات في شبكة؛ `list` يعرضها كقائمة بالأسماء.
- **`anchor`**: الموضع على الشاشة (`center`, `top`, `bottom`, إلخ).
- **`plugins_enabled`**: تفعيل إضافات الأوامر المائلة (`/calc`, `/translate`, ...).
- **`plugins_dir`**: مجلد يحتوي على إضافات بايثون؛ الافتراضي `<config>/plugins`.

### الأوامر المائلة والإضافات

اكتب `/` في مربع البحث لتصفح الأوامر المتاحة أو استخدم واحداً مباشرة، مثل `/calc 2+2` أو `/translate bonjour`. الإضافات مكتوبة بلغة بايثون — ضع ملف `.py` (أو مجلد حزمة) في `plugins/` وأعد تشغيل الشريط.

الإضافات المضمنة:

- **`/calc`** — رياضيات ووحدات وعملات عبر libqalculate (`qalc`)، مثل `/calc 100 cm to inches`.
- **`/translate`** — ترجمة مع اكتشاف تلقائي للغة المصدر، مثل `/translate bonjour`.
- **`/emoji`** — بحث رموز تعبيرية دون اتصال، مثل `/emoji rocket`.
- **`/clipboard-history`** — يبحث في سجل `cliphist` وينسخ عنصراً مرة أخرى، مثل `/clipboard-history https://`.
- **`/currency`** — تحويل بين العملات بأسعار حية (Frankfurter، بدون مفتاح API)، مثل `/currency 100 usd to eur`.
- **`/kill`** — يبحث في العمليات قيد التشغيل ويقتل المحددة (SIGTERM، أو SIGKILL مع `-9`)، مثل `/kill firefox`. الاستعلام الرقمي يُعامل كمنفذ — `/kill 3000` يقتل ما يستمع على المنفذ 3000.
- **`/search`** — بحث على الويب (DuckDuckGo، بدون مفتاح API) وفتح نتيجة في المتصفح مع نسخ رابطها إلى الحافظة، مثل `/search fabric hyprland`.

لوحة المفاتيح: `أعلى`/`أسفل` ينقلان التحديد، `Enter` ينشّط الصف المميز، `Escape` يغلق.
