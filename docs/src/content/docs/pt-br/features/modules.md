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
ignored = []
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
style = "default"
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

## Notas da Área de Trabalho

Notas adesivas na área de trabalho. Clique com o botão direito na área de trabalho e escolha **Nova nota** para criar uma, arraste-a pela faixa superior, digite diretamente nela e clique no ponto para alternar a cor. As notas são salvas por monitor em `desktop_notes.json`, no diretório de dados do Tsumiki, e restauradas ao reiniciar.

```toml
[modules.desktop_notes]
enabled = false
layer = "bottom"
note_width = 240 # Largura de cada nota em pixels
save_delay = 800 # Milissegundos de espera após uma edição antes de salvar
tooltip = true # Mostrar dicas nos botões da nota
```

A janela em tela cheia recebe os cliques da área de trabalho, então deve permanecer na camada `bottom`; use o botão (×) de uma nota para excluí-la.
