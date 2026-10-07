from datetime import datetime
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'demandas.db')

# 1. Apaga o banco de dados antigo com duplicatas para reiniciar limpo
if os.path.exists(DB_PATH):
  os.remove(DB_PATH)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 2. Criação das tabelas com PRIMARY KEY AUTOINCREMENT
cursor.execute('''
CREATE TABLE IF NOT EXISTS demandas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    descricao TEXT,
    solicitante_id INTEGER NOT NULL,
    data_criacao TEXT,
    status TEXT NOT NULL DEFAULT 'Aberta',
    prioridade TEXT NOT NULL DEFAULT 'Média',
    responsavel_id INTEGER,
    data_conclusao TEXT,
    FOREIGN KEY (solicitante_id) REFERENCES usuarios(id),
    FOREIGN KEY (responsavel_id) REFERENCES usuarios(id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS comentarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    demanda_id INTEGER,
    comentario TEXT,
    autor TEXT,
    data TEXT,
    FOREIGN KEY (demanda_id) REFERENCES demandas(id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    nome TEXT NOT NULL,
    email TEXT UNIQUE
)
''')

# 3. Inserção de Usuários
usuarios = [
    ('Arthur Spada', 'arthur@email.com'),
    ('Gustavo Rampanelli', 'gustavo@email.com'),
    ('Eduardo', 'eduardo@email.com'),
]
cursor.executemany(
    'INSERT OR IGNORE INTO usuarios (nome, email) VALUES (?, ?)', usuarios
)

# 4. Inserção de Demandas (deixando o SQLite gerar o ID automático)
#    solicitante_id e responsavel_id apontam para a tabela usuarios (1 Arthur, 2 Gustavo, 3 Eduardo)
from datetime import timedelta

agora = datetime.now()

demandas = [
    (
        'Corrigir bug no login',
        'Usuários não conseguem fazer login na plataforma principal',
        1,
        (agora - timedelta(days=20)).strftime('%Y-%m-%d 10:30:00'),
        'Concluída',
        'Crítica',
        3,
        (agora - timedelta(days=20) + timedelta(hours=6)).strftime('%Y-%m-%d 16:30:00'),
    ),
    (
        'Implementar relatório de vendas',
        'Precisamos de um relatório mensal consolidado por setor',
        3,
        (agora - timedelta(days=1, hours=2)).strftime('%Y-%m-%d %H:%M:%S'),
        'Em andamento',
        'Média',
        2,
        None,
    ),
    (
        'Melhorar performance do banco',
        'Otimizar queries de busca e índices no banco de dados',
        2,
        (agora - timedelta(hours=14)).strftime('%Y-%m-%d %H:%M:%S'),
        'Aberta',
        'Alta',
        1,
        None,
    ),
    (
        'Adicionar filtros na listagem',
        'Usuários querem filtrar demandas por status e responsável',
        1,
        (agora - timedelta(hours=6)).strftime('%Y-%m-%d %H:%M:%S'),
        'Aberta',
        'Baixa',
        None,
        None,
    ),
]

# Demandas extras para testar paginação, métricas analíticas e SLA
solicitante_teste = [1, 2, 3, 2, 1, 3, 1]
status_teste = ['Aberta', 'Em andamento', 'Concluída']
prioridade_teste = ['Baixa', 'Média', 'Alta', 'Crítica']
responsavel_teste = [1, 2, 3, 1, None]

# SLAs em dias: Crítica=2, Alta=5, Média=10, Baixa=20
sla_dias_map = {'Crítica': 2, 'Alta': 5, 'Média': 10, 'Baixa': 20}

for i in range(5, 26):
    st = status_teste[i % len(status_teste)]
    pr = prioridade_teste[i % len(prioridade_teste)]
    resp = responsavel_teste[i % len(responsavel_teste)]
    solic = solicitante_teste[i % len(solicitante_teste)]
    
    # Alterna entre demandas criadas recentemente (no prazo) e demandas mais antigas (atrasadas)
    if i % 3 == 0:
        # Recentes (dentro do SLA)
        dt_criacao = agora - timedelta(days=(i % 4) + 1, hours=i * 2)
    else:
        # Mais antigas (algumas ultrapassando o SLA se ativas)
        dt_criacao = agora - timedelta(days=12 + (i % 15), hours=i)
        
    dt_criacao_str = dt_criacao.strftime('%Y-%m-%d %H:%M:%S')
    
    dt_conclusao_str = None
    if st == 'Concluída':
        # Conclusão realista: de 6h a 6 dias após criação
        horas_resolucao = 6 + (i * 7) % 120
        dt_conclusao = dt_criacao + timedelta(hours=horas_resolucao)
        dt_conclusao_str = dt_conclusao.strftime('%Y-%m-%d %H:%M:%S')

    demandas.append(
        (
            f'Demanda de teste {i}',
            f'Descrição detalhada para teste de fluxo da demanda {i}',
            solic,
            dt_criacao_str,
            st,
            pr,
            resp,
            dt_conclusao_str,
        )
    )

# Demandas canceladas para testar exclusão de tempo médio e status
demandas.append(
    (
        'Refatorar layout legado de relatórios',
        'Demanda descontinuada após alinhamento de prioridades e escopo',
        2,
        (agora - timedelta(days=8)).strftime('%Y-%m-%d %H:%M:%S'),
        'Cancelada',
        'Baixa',
        1,
        None,
    )
)
demandas.append(
    (
        'Migração experimental de banco para NoSQL',
        'Cancelado devido a inviabilidade técnica de arquitetura após validação do time',
        3,
        (agora - timedelta(days=15)).strftime('%Y-%m-%d %H:%M:%S'),
        'Cancelada',
        'Média',
        None,
        None,
    )
)

cursor.executemany(
    '''
INSERT INTO demandas (titulo, descricao, solicitante_id, data_criacao, status, prioridade, responsavel_id, data_conclusao)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
''',
    demandas,
)

# 5. Inserção de Comentários
comentarios = [
    (1, 'Vou investigar esse bug prioritário no login', 'Tech Team', (agora - timedelta(days=20, hours=-1)).strftime('%Y-%m-%d 11:00:00')),
    (
        1,
        'Bug corrigido e testado na branch develop',
        'Desenvolvedor',
        (agora - timedelta(days=20, hours=-6)).strftime('%Y-%m-%d 16:30:00'),
    ),
]

cursor.executemany(
    '''
INSERT INTO comentarios (demanda_id, comentario, autor, data)
VALUES (?, ?, ?, ?)
''',
    comentarios,
)

conn.commit()
conn.close()

print('Banco de dados recriado com sucesso!')