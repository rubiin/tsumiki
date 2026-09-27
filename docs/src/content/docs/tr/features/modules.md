---
title: Modüller Referansı
description: Tüm Tsumiki modüllerinin tam dokümantasyonu
sidebar:
  order: 2
---

## Çubuk

```toml
[modules.bar]
layer = "top"
auto_hide = false
location = "top"
```

## Bildirim Sistemi

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

## Genel Bakış

```toml
[modules.overview]
enabled = false
layer = "top"
anchor = "center"
```

## Uygulama Başlatıcı

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

`/` yazarak `/calc` veya `/translate` gibi komutları kullanabilirsiniz. Eklentiler `plugins/` klasöründeki Python dosyalarıdır.

Dahil edilen eklentiler:

- **`/calc`** — libqalculate (`qalc`) ile matematik, birim ve para birimi, örn. `/calc 100 cm to inches`.
- **`/translate`** — kaynak dili otomatik algılanan çeviri, örn. `/translate bonjour`.
- **`/emoji`** — çevrimdışı emoji arama, örn. `/emoji rocket`.
- **`/clipboard-history`** — `cliphist` geçmişinde arama yapar ve bir öğeyi tekrar kopyalar, örn. `/clipboard-history https://`.
- **`/currency`** — canlı kurlarla para birimi çevirme (Frankfurter, API anahtarı gerekmez), örn. `/currency 100 usd to eur`.
- **`/kill`** — çalışan süreçleri arar ve seçileni sonlandırır (SIGTERM veya `-9` ile SIGKILL), örn. `/kill firefox`. Sayısal bir argüman bağlantı noktası olarak ele alınır — `/kill 3000`, 3000 bağlantı noktasını dinleyen süreci sonlandırır.
- **`/search`** — web araması (DuckDuckGo, API anahtarı gerekmez); sonucu tarayıcıda açar ve URL'yi panoya kopyalar, örn. `/search fabric hyprland`.

Klavye: `Yukarı`/`Aşağı` seçimi taşır, `Enter` vurgulanan satırı etkinleştirir, `Escape` kapatır.

## OSD

```toml
[modules.osd]
enabled = false
timeout = 3000
osds = ["brightness", "volume"]
```

## Masaüstü Saati

```toml
[modules.desktop_clock]
enabled = false
type = "cookie"
layer = "bottom"
nepali_date = false
```

## Masaüstü Alıntıları

```toml
[modules.desktop_quotes]
enabled = false
interval = 600
```
