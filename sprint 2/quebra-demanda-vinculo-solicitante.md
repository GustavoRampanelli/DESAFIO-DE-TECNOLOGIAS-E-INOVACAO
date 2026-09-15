# Quebra de Demanda — Vínculo de Solicitante a Usuário Cadastrado
**Sistema:** SGDI (sistema_sgdi_legado_aluno) · **Papel responsável por este documento:** PO
**Time:** PO  · Dev · Tech Lead

---

## 1. Contexto (mensagem original do time)

> "Precisamos evoluir o cadastro de demandas para permitir o controle adequado de solicitantes. Hoje, o campo de solicitante é apenas um texto livre (nome digitado), o que impede a rastreabilidade e não permite saber com precisão quantas demandas estão abertas por usuário. A ideia é substituir esse campo por um vínculo com um usuário cadastrado no sistema."

**Achado da análise técnica do código atual (`app.py` / `init_db.py`):**
- A tabela `demandas` tem a coluna `solicitante` como `TEXT` livre — sem nenhuma tabela de usuários existente hoje.
- A tabela `comentarios` tem o mesmo problema no campo `autor` (fora do escopo desta demanda, mas vale registrar como ponto futuro — ver seção 6).
- Todas as queries são construídas com f-string (`INSERT ... VALUES ('{titulo}'...)`), ou seja, há **SQL Injection** em todos os endpoints que escrevem no banco. Isso não faz parte do escopo pedido, mas deve ser registrado como débito técnico (seção 6), pois qualquer tela nova que a gente criar (ex.: cadastro de usuário) não pode repetir esse padrão.

---

## 2. Requisito claro (para virar História de Usuário no backlog)

**User Story**
> Como Tech Lead / gestor de demandas, quero que cada demanda seja vinculada a um usuário cadastrado no sistema (e não a um texto livre), para que eu tenha rastreabilidade, evite duplicidade/erros de digitação e consiga contar e filtrar demandas por solicitante.

**Regras de negócio**
1. O campo `solicitante` deixa de ser texto livre e passa a ser uma referência (chave estrangeira) para um cadastro de usuário.
2. Deve existir uma tela/rota de **cadastro de usuários** (hoje não existe nenhuma).
3. Ao criar ou editar uma demanda, o solicitante é selecionado a partir da lista de usuários cadastrados (não digitado).
4. Deve ser possível ver, por usuário, quantas demandas ele possui (contagem) — base para filtros e relatórios futuros.
5. Os dados legados (nomes em texto na tabela atual) precisam ser migrados para usuários cadastrados, sem perda de histórico.

**Critérios de aceite**
- [ ] Dado que estou cadastrando uma nova demanda, quando abro o formulário, então o campo "solicitante" é uma lista de seleção de usuários cadastrados (não um input de texto).
- [ ] Dado que um usuário não existe ainda no cadastro, quando tento selecioná-lo na demanda, então o sistema não permite (ele precisa existir previamente).
- [ ] Dado que uma demanda já existente tem um solicitante em texto livre, quando a migração é executada, então essa demanda passa a apontar para um usuário cadastrado equivalente, sem duplicar nomes parecidos.
- [ ] Dado que acesso a listagem/detalhe de um usuário, quando visualizo, então consigo ver a quantidade de demandas abertas por ele.
- [ ] Dado que uso o filtro de demandas, quando escolho um solicitante, então vejo apenas as demandas daquele usuário.

**Fora do escopo desta demanda** (para não inflar o card)
- Login/autenticação de usuários.
- Corrigir o SQL Injection existente em todo o sistema (registrar como débito técnico separado).
- Vincular `autor` dos comentários a usuário (mesma lógica, mas é outro card).

---

## 3. Divisão de tarefas — quem faz o quê

| # | Tarefa | Responsável | Descrição curta |
|---|--------|-------------|------------------|
| 1 | Escrever requisito e critérios de aceite | **PO** | Este documento — transformar a conversa em requisito rastreável |
| 2 | Modelar tabela `usuarios` e FK `solicitante_id` em `demandas` | **Tech Lead** | Definir colunas (id, nome, e-mail, ativo/inativo), tipo de relacionamento, índice em `solicitante_id` |
| 3 | Definir estratégia de migração dos dados legados | **Tech Lead** | Como transformar os nomes em texto (`João Silva`, `Maria Santos`...) em registros de usuário sem duplicar |
| 4 | Escrever script de migração dos dados | **Dev** (com apoio do Tech Lead) | Rodar sobre `demandas.db` atual, criar usuários a partir dos nomes distintos e atualizar `solicitante_id` |
| 5 | Criar CRUD de cadastro de usuários (tela + rota) | **Dev** | Pré-requisito para o passo 6 — precisa existir antes de trocar o formulário de demanda |
| 6 | Trocar campo texto por `<select>` de usuário em `nova_demanda.html` | **Dev** | Formulário de criação passa a usar a lista de usuários |
| 7 | Trocar campo texto por `<select>` de usuário em `editar.html` | **Dev** | Mesma lógica na edição |
| 8 | Ajustar `index.html` e `detalhes.html` para exibir o nome do usuário vinculado | **Dev** | Hoje exibem `solicitante` como texto; passam a exibir via join com `usuarios` |
| 9 | Implementar contagem de demandas por usuário | **Dev** | Base de dados/consulta para os relatórios pedidos |
| 10 | Implementar filtro de demandas por solicitante | **Dev** | Endpoint/tela de filtro, reaproveitando a contagem do item 9 |
| 11 | Revisão técnica do código entregue | **Tech Lead** | Checar consistência do modelo, uso de parâmetros nas queries novas (não repetir f-string), nomes de colunas |
| 12 | Roteiro de teste manual (não há testes automatizados no projeto) | **Dev + Tech Lead** | Criar demanda, editar, listar, filtrar, checar contagem, checar que dado legado migrou certo |
| 13 | Validar entrega contra os critérios de aceite | **PO** | Confirmar que os critérios da seção 2 foram atendidos |
| 14 | Atualizar README do projeto | **PO ou Dev** | Documentar o novo modelo de solicitante |

---

## 4. Ordem sugerida e estimativa de tempo

A ordem segue dependência técnica (não dá para trocar o formulário antes de existir a tabela/cadastro de usuário). Estimativas em horas — ajuste conforme a disponibilidade real do time; são um ponto de partida, não uma promessa.

| Ordem | Tarefa (# da tabela acima) | Responsável | Estimativa | Depende de |
|---|---|---|---|---|
| 1 | 1 — Requisito e critérios | PO | 1h | — |
| 2 | 2 — Modelagem da tabela `usuarios` + FK | Tech Lead | 1–2h | 1 |
| 3 | 3 — Estratégia de migração | Tech Lead | 1h | 2 |
| 4 | 5 — CRUD de cadastro de usuário | Dev | 3–4h | 2 |
| 5 | 4 — Script de migração dos dados legados | Dev | 2–3h | 3, 4 |
| 6 | 6 e 7 — Trocar campo texto por select (novo/editar) | Dev | 2h | 4, 5 |
| 7 | 8 — Ajustar listagem/detalhe para exibir usuário | Dev | 1–2h | 5 |
| 8 | 9 — Contagem de demandas por usuário | Dev | 1–2h | 6, 7 |
| 9 | 10 — Filtro por solicitante | Dev | 1–2h | 8 |
| 10 | 11 — Revisão técnica | Tech Lead | 1h | 6–9 |
| 11 | 12 — Roteiro de teste manual | Dev + Tech Lead | 1–2h | 10 |
| 12 | 13 — Validação contra critérios de aceite | PO | 1h | 11 |
| 13 | 14 — Atualizar README | PO/Dev | 30min | 12 |

**Total estimado:** aproximadamente 17–24h de trabalho combinado do time.

---

## 5. Cards para a ferramenta de gestão de projetos

Sugestão de como abrir os cards (título + responsável + coluna inicial). Copie linha a linha para o board (Trello/GitHub Projects/Jira):

| Card | Responsável | Coluna inicial |
|---|---|---|
| Modelar tabela `usuarios` e FK `solicitante_id` | Tech Lead | A Fazer |
| Definir estratégia de migração de solicitantes legados | Tech Lead | A Fazer |
| Criar CRUD de cadastro de usuários | Dev | Backlog (bloqueado até modelagem) |
| Script de migração dos dados legados | Dev | Backlog (bloqueado) |
| Trocar campo solicitante por select — tela Nova Demanda | Dev | Backlog (bloqueado) |
| Trocar campo solicitante por select — tela Editar Demanda | Dev | Backlog (bloqueado) |
| Exibir usuário vinculado em Listagem e Detalhes | Dev | Backlog (bloqueado) |
| Contagem de demandas por usuário | Dev | Backlog (bloqueado) |
| Filtro de demandas por solicitante | Dev | Backlog (bloqueado) |
| Revisão técnica da entrega | Tech Lead | Backlog |
| Roteiro de teste manual | Dev + Tech Lead | Backlog |
| Validação final contra critérios de aceite | PO | Backlog |
| Atualizar README | PO/Dev | Backlog |

---

## 6. Pensando na escalabilidade futura (o "pega" do desafio)

O card parece simples (trocar texto por seleção), mas decisões tomadas agora podem travar o sistema depois. Pontos para o Tech Lead validar na modelagem:

- **Não usar exclusão física de usuário.** Se um usuário for removido do cadastro fisicamente, todas as demandas vinculadas a ele perdem a referência (ou quebram). Usar um campo de status (ativo/inativo) em vez de deletar.
- **Índice em `solicitante_id`.** Sem índice, contagem e filtro por solicitante ficam lentos conforme o volume de demandas cresce.
- **Modelo pensando em múltiplos papéis.** Hoje só existe "solicitante", mas é comum sistemas assim evoluírem para "aprovador", "responsável técnico", "atendente". Vale desenhar a tabela `usuarios` de forma genérica (não amarrada só ao conceito de solicitante) para não precisar remodelar de novo.
- **Preparar terreno para autenticação futura.** O sistema não tem login hoje; se a tabela de usuários for bem desenhada agora, a implementação futura de login reaproveita o cadastro em vez de duplicá-lo.
- **Não repetir o padrão de SQL via f-string nas telas novas.** O código legado tem SQL Injection em todos os endpoints (`INSERT`, `UPDATE`, `DELETE` com f-string). Isso é um débito técnico do sistema como um todo — não faz parte desta demanda, mas deve ser registrado à parte para não ser copiado no CRUD de usuários novo.
- **O campo `autor` de comentários tem o mesmo problema de texto livre.** Fica fora do escopo agora, mas é candidato natural para a próxima demanda de evolução, usando a mesma tabela `usuarios`.

---

