# SGDI - Sistema de Gestão de Demandas Internas

Sistema completo para gestão, acompanhamento e governança de demandas internas da empresa.

---

## 🚀 Funcionalidades Implementadas

- **Gestão de Solicitantes e Responsáveis:** Demandas vinculadas a usuários cadastrados (`solicitante_id` e `responsavel_id`), garantindo rastreabilidade e integridade referencial.
- **Níveis de Prioridade:** Classificação de demandas em `Baixa`, `Média`, `Alta` e `Crítica` (padrão: `Média`).
- **Ciclo de Vida / Status:** Acompanhamento dos status `Aberta`, `Em andamento` e `Concluída`.
- **Filtros Combinados:** Filtragem simultânea na listagem por:
  - Termo no título da demanda (`q`)
  - Status
  - Prioridade
  - Usuário responsável
- **Paginação:** Navegação fluida com limite configurado (10 demandas por página), mantendo os filtros ativos entre as páginas.
- **Detalhes e Comentários:** Histórico de acompanhamento com registro de comentários, autor e data.
- **Segurança:** Consultas ao banco de dados com parametrização (proteção contra SQL Injection).

---

## 📁 Estrutura do Repositório

```text
├── ADR/                                # Architectural Decision Records
│   ├── [exemple] ADR PDF.md
│   └── [exemple] ADR PDF.pdf
├── sprint 2/                           # Documentação e artefatos de entrega da Sprint
│   ├── Demanda Sprint 02.pdf
│   └── quebra-demanda-vinculo-solicitante.md
├── static/                             # Arquivos estáticos (CSS customizado)
│   └── style.css
├── templates/                          # Templates Jinja2
│   ├── base.html                       # Layout base com menu e busca rápida
│   ├── index.html                      # Listagem com filtros e paginação
│   ├── nova_demanda.html               # Formulário de criação
│   ├── editar.html                     # Formulário de edição
│   └── detalhes.html                   # Visualização detalhada e comentários
├── app.py                              # Aplicação principal Flask e rotas
├── init_db.py                          # Script de inicialização do banco SQLite com seed
├── demandas.db                         # Banco de dados SQLite local
├── requirements.txt                    # Dependências do projeto
├── Logo SSR.png                        # Identidade visual
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

### 3. Inicializar o Banco de Dados
Para criar as tabelas e carregar a massa de dados inicial de teste (usuários e demandas):
```bash
python init_db.py
```

### 4. Iniciar a Aplicação
```bash
python app.py
```
Acesse no navegador: **`http://localhost:5000`**

---

*SGDI - Sistema de Gestão de Demandas Internas*