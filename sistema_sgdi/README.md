# SGDI - Sistema de Gestão de Demandas Internas

Sistema completo para gestão, acompanhamento, analytics e governança de demandas internas da empresa.

---

## 🚀 Funcionalidades Implementadas

- **📊 Painel Principal de Analytics & Governança:**
  - **Total de demandas:** Contagem consolidada de todas as demandas do sistema com taxas percentuais.
  - **Status geral (Abertas / Em andamento / Concluídas / Canceladas):** Visão quantitativa e visual por gráfico de rosca interativo.
  - **Evolução Temporal de Demandas:** Gráfico dinâmico de série histórica com curvas de volume de demandas abertas versus demandas concluídas por período.
  - **Desempenho por Responsável:** Tabela detalhada e gráfico de barras empilhadas com total, abertas, em andamento, concluídas, canceladas, fora do SLA, tempo médio de resolução e taxa de conclusão.
  - **Tempo Médio de Resolução:** Cálculo automático e formatado em dias/horas a partir da data de conclusão real (`data_conclusao - data_criacao`).
  - **Índice de Severidade do Backlog:** Score ponderado de criticidade das demandas ativas em escala de 1.0 a 4.0.
  - **Demandas que Requerem Atenção:** Destaque dinâmico das demandas em atraso ou prestes a vencer.

- **⚙️ Regras de Negócio e Governança:**
  - **🔴 Atrasados aparecem em vermelho:** Destaque visual rigoroso em vermelho para cards de alerta, badges de SLA e linhas da tabela (`.row-fora-sla`).
  - **⚠️ Sem responsável = Fora do SLA:** Qualquer demanda ativa sem responsável atribuído é considerada automaticamente em violação de SLA.
  - **⚖️ Críticos pesam mais que médio:** Ponderação de criticidade das demandas (Crítica: peso **4**, Alta: peso **3**, Média: peso **2**, Baixa: peso **1**).
  - **🚫 Cancelados fora do tempo médio:** Demandas com status `Cancelada` são rigorosamente excluídas do cálculo do tempo médio de resolução.

- **🔄 Filtros e Atualização Dinâmica:**
  - Filtragem combinada por **Período** (Todo o histórico, 7 dias, 30 dias, 90 dias ou datas personalizadas), **Responsável**, **Prioridade** e **Status**.
  - **Atualização Dinâmica (Client-side):** Endpoint JSON `/api/analytics` para recalcular KPIs e gráficos instantaneamente sem recarregar a tela.

- **📑 Exportação de Relatórios Corporativos:**
  - **PDF (`/exportar/pdf`):** Relatório executivo formatado com sumário executivo, métricas de SLA e tabela de demandas.
  - **Excel (`/exportar/excel`):** Planilha `.xlsx` estilizada com abas de Resumo Geral e Demandas Detalhadas.
  - **CSV (`/exportar/csv`):** Arquivo de dados delimitado por ponto e vírgula com codificação UTF-8 BOM para compatibilidade com Excel.
  - **Identidade Corporativa:** Todos os relatórios contêm cabeçalho com o nome da empresa (`SGDI - Sistema de Gestão de Demandas Internas | SSR - Gestão & Governança`), rodapé com filtros aplicados e timestamp exato de geração (`DD/MM/AAAA às HH:MM:SS`).

---

## 📁 Estrutura do Repositório

```text
├── static/                             # Arquivos estáticos
│   ├── style.css                       # Design System moderno, responsivo e estilos de impressão/SLA
│   └── logo.png                        # Identidade visual da aplicação
├── templates/                          # Templates Jinja2
│   ├── base.html                       # Layout base com navbar, logo e suporte a Chart.js
│   ├── dashboard.html                  # Painel Principal de Analytics com KPIs, gráficos e filtros dinâmicos
│   ├── index.html                      # Listagem de demandas (/demandas) com exportação e destaques SLA
│   ├── nova_demanda.html               # Formulário de criação com indicação de SLAs
│   ├── editar.html                     # Formulário de edição e registro de conclusão
│   └── detalhes.html                   # Visualização detalhada, SLA e comentários
├── app.py                              # Aplicação principal Flask, rotas de exportação e analytics
├── init_db.py                          # Script de inicialização do banco SQLite com seed realista
├── demandas.db                         # Banco de dados SQLite local
├── requirements.txt                    # Dependências do projeto (Flask, openpyxl, markdown-pdf, etc.)
├── Logo SSR.png                        # Logo original da empresa
└── README.md                           # Documentação do projeto
```

---

## 🛠️ Como Executar

### 1. Pré-requisitos
- Python 3.10+ instalado.

### 2. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 3. Inicializar o Banco de Dados (Opcional se já possuir `demandas.db`)
Para recriar as tabelas e carregar a massa de dados inicial de teste (usuários, demandas com SLA e conclusões):
```bash
python init_db.py
```

### 4. Iniciar a Aplicação
```bash
python app.py
```
Acesse no navegador: **`http://localhost:5000`**

### 5. Rotas Disponíveis
- **`http://localhost:5000/`** (ou `/dashboard` / `/analytics`): Painel Principal de Analytics com KPIs, gráficos e desempenho.
- **`http://localhost:5000/demandas`**: Gestão completa de demandas, filtros combinados e paginação.
- **`http://localhost:5000/nova_demanda`**: Cadastro de nova demanda.
- **`http://localhost:5000/detalhes/<id>`**: Visão detalhada de uma demanda e histórico de comentários.
- **`http://localhost:5000/editar/<id>`**: Atualização de dados e transição de status com cálculo de SLA.

---

*SGDI - Sistema de Gestão de Demandas Internas*