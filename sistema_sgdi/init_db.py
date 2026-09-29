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
demandas = [
    (
        'Corrigir bug no login',
        'Usuários não conseguem fazer login',
        1,
        '2024-01-15 10:30:00',
        'Concluída',
        'Crítica',
        3,
    ),
    (
        'Implementar relatório de vendas',
        'Precisamos de um relatório mensal',
        3,
        '2024-01-16 14:20:00',
        'Em andamento',
        'Média',
        2,
    ),
    (
        'Melhorar performance',
        'Sistema está lento',
        2,
        '2024-01-17 09:15:00',
        'Aberta',
        'Alta',
        1,
    ),
    (
        'Adicionar filtros',
        'Usuários querem filtrar demandas',
        1,
        '2024-01-18 11:00:00',
        'Aberta',
        'Baixa',
        None,
    ),
]

# Demandas extras para testar a paginação e os filtros (Sprint 3)
# ids da tabela usuarios (1 Arthur, 2 Gustavo, 3 Eduardo); tamanho 7 para variar as combinações com as outras listas
solicitante_teste = [1, 2, 3, 2, 1, 3, 1]
status_teste = ['Aberta', 'Em andamento', 'Concluída']
prioridade_teste = ['Baixa', 'Média', 'Alta', 'Crítica']
# ids da tabela usuarios (None = sem responsável); tamanho 5 para variar as combinações com as outras listas
responsavel_teste = [1, 2, 3, 1, None]
for i in range(5, 26):
    demandas.append(
        (
            f'Demanda de teste {i}',
            f'Descrição da demanda de teste {i}',
            solicitante_teste[i % len(solicitante_teste)],
            f'2024-02-{i:02d} 10:00:00',
            status_teste[i % len(status_teste)],
            prioridade_teste[i % len(prioridade_teste)],
            responsavel_teste[i % len(responsavel_teste)],
        )
    )

cursor.executemany(
    '''
INSERT INTO demandas (titulo, descricao, solicitante_id, data_criacao, status, prioridade, responsavel_id)
VALUES (?, ?, ?, ?, ?, ?, ?)
''',
    demandas,
)

# 5. Inserção de Comentários
comentarios = [
    (1, 'Vou investigar esse bug', 'Tech Team', '2024-01-15 11:00:00'),
    (
        1,
        'Bug corrigido na branch develop',
        'Desenvolvedor',
        '2024-01-15 16:30:00',
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