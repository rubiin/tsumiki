---
title: Configuração Avançada
description: Padrões de configuração avançada do Tsumiki
---

Depois de se sentir confortável com o básico da [Configuração](/pt-br/configuring/config), estes padrões ajudam você a ajustar ainda mais o Tsumiki.

## Widget Personalizado

Widgets personalizados compatíveis com Waybar que executam comandos shell externos com análise de saída configurável e manipulação de cliques.

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

Opções completas de configuração:

| Chave              | Tipo   | Padrão      | Descrição                                                               |
| ------------------ | ------ | ----------- | ----------------------------------------------------------------------- |
| `id`               | string | —           | Identificador único para referência no layout (`@custom_widget:meu-id`) |
| `exec`             | string | obrigatório | Comando shell a ser executado                                           |
| `interval`         | int    | `0`         | Intervalo de atualização em milissegundos (0 = executar uma vez)        |
| `return_type`      | string | `"plain"`   | Formato de saída: `"plain"` ou `"json"`                                 |
| `label_format`     | string | `"{}"`      | String de formato onde `{}` é substituído pela saída                    |
| `exec_on_event`    | bool   | `false`     | Reexecutar comando após clique/rolagem                                  |
| `max_length`       | int    | `0`         | Comprimento máximo do texto (0 = sem limite)                            |
| `min_length`       | int    | `0`         | Comprimento mínimo do texto (preenche com espaços)                      |
| `rotate`           | int    | `0`         | Rotacionar texto em graus                                               |
| `tooltip`          | bool   | `true`      | Mostrar dica de ferramenta com a saída                                  |
| `tooltip_format`   | string | —           | String de formato da dica de ferramenta                                 |
| `on_click`         | string | —           | Comando de clique esquerdo                                              |
| `on_click_right`   | string | —           | Comando de clique direito                                               |
| `on_click_middle`  | string | —           | Comando de clique do meio                                               |
| `on_scroll_up`     | string | —           | Comando de rolagem para cima                                            |
| `on_scroll_down`   | string | —           | Comando de rolagem para baixo                                           |
| `signal`           | int    | —           | Número do sinal para gatilhos de eventos sig*                           |
| `restart_interval` | int    | —           | Intervalo de reinicialização para scripts persistentes                  |

## Grupos de Widgets

Agrupe widgets com espaçamento e estilo compartilhados:
Referencie um grupo em seu layout com `@group:N` (índice baseado em zero) ou `@group:id` (identificador de texto):

```toml
[[widget_groups]]
id = "sys-group"
widgets = ["updates", "battery"]
spacing = 4
style_classes = ["bordered"]
```

Referencie no layout com `@group:sys-group`.

```toml
[layout]
right_section = ["@group:sys-group", "system_tray"]
```

## Grupos Recolhíveis

Oculte widgets menos usados atrás de uma alternância:

```toml
[[collapsible_groups]]
id = "utility-tools"
widgets = ["ocr", "screenshot", "recorder"]
spacing = 4
icon = "󰒓"
label_format = "{icon}"
tooltip = "Ferramentas"
style_classes = ["utility-tools"]
```

Referencie no layout com `@collapsible:utility-tools`.

```toml

right_section = ["@collapsible:utility-tools", "system_tray"]

```
