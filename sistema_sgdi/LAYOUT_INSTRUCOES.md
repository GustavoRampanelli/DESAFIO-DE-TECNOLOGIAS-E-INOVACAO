# Guia de Estilo & Instruções de Layout (Inspiração: Obsidian)
## SGDI - Sistema de Gestão de Demandas Internas

Este documento estabelece as diretrizes arquiteturais, visuais e de componentes para a reformulação do layout da aplicação SGDI, abandonando padrões genéricos de templates convencionais e adotando a estética e usabilidade do **Obsidian** (ambiente markdown, workspaces modulares, paleta escura focada em legibilidade e tags técnicas).

---

## 1. Filosofia de Design: Obsidian Workspace

O Obsidian é reconhecido por sua interface limpa, minimalista, orientada a produtividade e com alto foco no conteúdo:
- **Superfícies Escuras Profundas (Dark Graphite):** Fundo grafite profundo que reduz fadiga visual e dá destaque imediato a dados críticos e gráficos.
- **Divisores e Painéis Cirúrgicos:** Bordas sutis de 1px (`#323238`) substituindo sombras volumosas e gradientes artificiais.
- **Tipografia Técnica & Monospaçada:** Combinação de *Inter* para leitura natural com *JetBrains Mono* / *Consolas* para identificadores (`#024`), códigos, prazos e métricas de SLA.
- **Tags no Formato Obsidian (`#tag`):** Classificação visual com sintaxe de hashtag e preenchimento translúcido suave (`#critica`, `#fora-sla`, `#em-andamento`).
- **Callouts Nativos do Obsidian (`[!danger]`, `[!warning]`, `[!info]`):** Caixas de aviso elegantes com barra lateral colorida e ícone monocromático.
- **Acento Violeta Obsidian:** Acento de destaque na cor ametista/violeta (`#7c3aed` / `#a855f7`), combinada com alertas rigorosos em vermelho carmesim (`#ef4444`) para atrasos e violações de SLA.

---

## 2. Paleta de Cores e Tokens CSS

```css
:root {
    /* Superfícies & Painéis (Obsidian Canvas) */
    --obs-bg-main: #141416;          /* Fundo principal da aplicação */
    --obs-bg-pane: #1b1b1e;          /* Painéis e cards de conteúdo */
    --obs-bg-card: #212126;          /* Cards elevados e células ativas */
    --obs-bg-hover: #292930;         /* Estado hover e seleção */
    --obs-bg-active: #32323b;        /* Item ativo/pressionado */
    --obs-border: #323238;           /* Bordas sutis dos painéis */
    --obs-border-focus: #52525e;     /* Borda em foco/destaque */

    /* Tipografia */
    --obs-text-normal: #e3e3e8;      /* Texto padrão de alta legibilidade */
    --obs-text-muted: #8e8e99;       /* Metadados, rótulos e descrições */
    --obs-text-faint: #5e5e68;       /* Placeholders e divisores */
    --obs-font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    --obs-font-mono: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;

    /* Cores de Acento & Governança */
    --obs-accent: #7c3aed;           /* Violeta assinatura Obsidian */
    --obs-accent-light: #8b5cf6;
    --obs-accent-glow: rgba(124, 58, 237, 0.25);

    /* Estados de SLA & Criticidade */
    --obs-danger: #ef4444;           /* Vermelho rigoroso: Atrasos & Fora SLA */
    --obs-danger-bg: rgba(239, 68, 68, 0.12);
    --obs-danger-border: rgba(239, 68, 68, 0.35);

    --obs-warning: #f59e0b;          /* Âmbar: Em andamento / Atenção */
    --obs-warning-bg: rgba(245, 158, 11, 0.12);
    --obs-warning-border: rgba(245, 158, 11, 0.35);

    --obs-success: #10b981;          /* Esmeralda: Concluído no prazo */
    --obs-success-bg: rgba(16, 185, 129, 0.12);
    --obs-success-border: rgba(16, 185, 129, 0.35);

    --obs-info: #0284c7;             /* Azul grafite: Informações gerais */
    --obs-info-bg: rgba(2, 132, 199, 0.12);
}
```

---

## 3. Estrutura de Componentes

### 3.1. Barra de Navegação (Obsidian Ribbon & Tabs)
- Topo escuro fosco com altura enxuta (54px), borda inferior sutil de 1px.
- Botões em formato de abas de arquivo (*Tabs*):
  - `📊 Painel Analytics`
  - `📋 Demandas`
  - `🚨 Críticas & Atrasadas` *(Nova visão dedicada em destaque vermelho/violeta)*
  - `+ Nova Demanda` *(Botão primário acentuado)*
- Caixa de busca rápida com atalho visual (estilo Command Palette `Ctrl+K`).

### 3.2. Visão Dedicada: Críticas & Atrasadas (`/criticas-atrasadas`)
- Destinada a **War Room**, triagem diária e foco imediato do time técnico e liderança.
- **Critérios de Filtro Automático:**
  1. Demandas ativas com Prioridade = `Crítica`.
  2. Demandas ativas com Prazo Estourado (`status_sla = 'atrasada'`).
  3. Demandas ativas Sem Responsável Atribuído (`status_sla = 'sem_responsavel_fora_sla'`).
- **Cards de Resumo de Emergência:**
  - `🔥 Críticas Atrasadas`: Duplo risco (máxima urgência).
  - `🚨 Fora do SLA Geral`: Prazo violado ou sem responsável.
  - `⚡ Críticas no Prazo`: Monitoramento preventivo ativo.
  - `👤 Sem Responsável`: Gargalos de distribuição pendentes.
- **Painéis de Triagem Rápida:**
  - Visualização em tabela compacta estilo nota markdown ou modo split-cards.
  - Ações expressas de atribuição de responsável e edição de prazo.

### 3.3. Callouts Estilo Obsidian
```html
<div class="obs-callout obs-callout-danger">
    <div class="obs-callout-title">
        <span class="obs-callout-icon">🚨</span>
        <strong>Atenção Imediata</strong>
    </div>
    <div class="obs-callout-content">
        Existem 11 demandas fora do SLA exigindo triagem imediata.
    </div>
</div>
```

### 3.4. Badges em Formato Tag Obsidian (`#tag`)
Em vez de pílulas arredondadas convencionais, o SGDI passa a usar tags com prefixo `#`:
- `#critica` (vermelho escuro)
- `#alta` (laranja suave)
- `#fora-sla` (borda vermelha pulsante)
- `#sem-responsavel` (tag de alerta)
- `#concluida` (verde esmeralda suave)

### 3.5. Gráficos Chart.js Adaptados para Obsidian Dark
- Fundo transparente com eixos e linhas de grade em cinza sutil (`rgba(255, 255, 255, 0.08)`).
- Paleta dos gráficos ajustada para tons Obsidian: violeta (`#8b5cf6`), esmeralda (`#10b981`), carmesim (`#ef4444`), âmbar (`#f59e0b`) e ciano (`#06b6d4`).
- Tooltips personalizados com fundo `#1e1e21` e borda `#323238`.

---

## 4. Roteiro de Implementação
1. **Documento de Instruções:** Salvo em `LAYOUT_INSTRUCOES.md`.
2. **Atualização do Design System CSS (`static/style.css`):** Substituição do tema claro pelo tema Obsidian Workspace.
3. **Criação da Rota Dedicada (`app.py`):** Rota `@app.route('/criticas-atrasadas')` com métricas específicas de emergência.
4. **Novo Template Jinja2 (`templates/criticas_atrasadas.html`):** Layout Obsidian para War Room de demandas críticas e atrasadas.
5. **Atualização da Barra de Navegação (`templates/base.html`):** Inclusão da aba *Críticas & Atrasadas* com badge de alerta em tempo real.
6. **Harmonização das Telas Existentes:** Painel Analytics, Listagem de Demandas, Detalhes e Formulários ajustados para a nova estética.
