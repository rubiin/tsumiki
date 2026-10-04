---
title: Referência de Módulos
description: Documentação completa de todos os módulos do Tsumiki
sidebar:
  order: 2
---

## Barra

```toml
[modules.bar]
layer = "top"
auto_hide = false
location = "top"
```

## Sistema de Notificações

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

## Visão Geral

```toml
[modules.overview]
enabled = false
layer = "top"
anchor = "center"
```

## Lançador de Aplicativos

```toml
[modules.launcher]
enabled = false
tooltip = true
icon_size = 35
anchor = "center"
width = 280
height = 320
layout = "grid"
grid_columns = 3
grid_spacing = 12
plugins_enabled = true
plugins_dir = ""
```

Digite `/` para usar comandos como `/calc` ou `/translate`. Plugins são arquivos Python no diretório `plugins/`.

Plugins incluídos:

- **`/calc`** — matemática, unidades e moedas via libqalculate (`qalc`), ex.: `/calc 100 cm to inches`.
- **`/translate`** — tradução com idioma de origem detectado automaticamente, ex.: `/translate bonjour`.
- **`/emoji`** — busca offline de emojis, ex.: `/emoji rocket`.
- **`/clipboard-history`** — pesquisa o histórico do `cliphist` e copia um item de volta, ex.: `/clipboard-history https://`.
- **`/currency`** — conversão entre moedas com taxas ao vivo (Frankfurter, sem chave de API), ex.: `/currency 100 usd to eur`.
- **`/kill`** — pesquisa processos em execução e encerra o selecionado (SIGTERM, ou SIGKILL com `-9`), ex.: `/kill firefox`. Um argumento numérico é tratado como porta — `/kill 3000` encerra o que estiver escutando na porta 3000.
- **`/search`** — pesquisa na web (DuckDuckGo, sem chave de API) e abre um resultado no navegador copiando o URL para a área de transferência, ex.: `/search fabric hyprland`.

Teclado: `Cima`/`Baixo` movem a seleção, `Enter` ativa a linha destacada, `Escape` fecha.

## OSD

```toml
[modules.osd]
enabled = false
timeout = 3000
osds = ["brightness", "volume"]
```

## Relógio da Área de Trabalho

```toml
[modules.desktop_clock]
enabled = false
type = "cookie"
layer = "bottom"
```

## Citações da Área de Trabalho

```toml
[modules.desktop_quotes]
enabled = false
interval = 600
```
