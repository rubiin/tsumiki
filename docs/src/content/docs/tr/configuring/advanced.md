---
title: Gelişmiş Yapılandırma
description: Gelişmiş Tsumiki yapılandırma desenleri
---

[Yapılandırma](/tr/configuring/config) temellerine hakim olduktan sonra, bu desenler Tsumiki'yi daha da ince ayarlamanıza yardımcı olur.

## Özel Widget

Yapılandırılabilir çıktı ayrıştırma ve tıklama işleme ile harici shell komutları çalıştıran Waybar uyumlu özel widgetlar.

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

Tam yapılandırma seçenekleri:

| Anahtar            | Tür    | Varsayılan | Açıklama                                                                     |
| ------------------ | ------ | ---------- | ---------------------------------------------------------------------------- |
| `id`               | string | —          | Düzende referans için benzersiz tanımlayıcı (`@custom_widget:kimliğim`)      |
| `exec`             | string | —          | Çalıştırılacak shell komutu; yalnızca tıklamaya bağlı bir düğme için çıkarın |
| `icon`             | string | —          | Sabit simge glifi; `format_icons.default` ile aynı                           |
| `interval`         | int    | `0`        | Milisaniye cinsinden yenileme aralığı (0 = bir kez çalıştır)                 |
| `return_type`      | string | `"plain"`  | Çıktı formatı: `"plain"` veya `"json"`                                       |
| `label_format`     | string | `"{}"`     | `{}` yerine çıktının geçtiği format dizisi                                   |
| `format`           | string | —          | Waybar'daki `label_format` adı                                               |
| `exec_on_event`    | bool   | `false`    | Tıklama/kaydırmadan sonra komutu yeniden çalıştır                            |
| `max_length`       | int    | `0`        | Maksimum metin uzunluğu (0 = sınırsız)                                       |
| `min_length`       | int    | `0`        | Minimum metin uzunluğu (boşluklarla doldurur)                                |
| `rotate`           | int    | `0`        | Metni derece cinsinden döndür                                                |
| `tooltip`          | bool   | `true`     | Çıktıyla araç ipucu göster                                                   |
| `tooltip_format`   | string | —          | Araç ipucu format dizisi                                                     |
| `tooltip_text`     | string | —          | Çıktısı hiç değişmeyen widget için sabit araç ipucu                          |
| `on_click`         | string | —          | Sol tıklama komutu                                                           |
| `on_click_right`   | string | —          | Sağ tıklama komutu                                                           |
| `on_click_middle`  | string | —          | Orta tıklama komutu                                                          |
| `on_scroll_up`     | string | —          | Yukarı kaydırma komutu                                                       |
| `on_scroll_down`   | string | —          | Aşağı kaydırma komutu                                                        |
| `signal`           | int    | —          | sig* olay tetikleyicileri için sinyal numarası                               |
| `restart_interval` | int    | —          | Kalıcı betikler için yeniden başlatma aralığı                                |

## Widget Grupları

Widgetları paylaşımlı boşluk ve stil ile gruplayın:
Düzeninizde `@group:N` (sıfır tabanlı indeks) veya `@group:id` (metin kimliği) ile bir gruba referans verin:

```toml
[[widget_groups]]
id = "sys-group"
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]
```

Düzende `@group:sys-group` ile referans verin.

```toml
[layout]
right_section = ["@group:sys-group", "system_tray"]
```

## Daraltılabilir Gruplar

Daha az kullanılan widgetları bir toggle arkasında gizleyin:

```toml
[[collapsible_groups]]
id = "utility-tools"
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
label_format = "󰍽"
tooltip = "Araçlar"
style_classes = ["utility-tools"]
```

Düzende `@collapsible:utility-tools` ile referans verin.

```toml

right_section = ["@collapsible:utility-tools", "system_tray"]

```
