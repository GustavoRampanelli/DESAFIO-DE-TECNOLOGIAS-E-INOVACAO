from datetime import datetime
import os
import sqlite3

# 1. Apaga o banco de dados antigo com duplicatas para reiniciar limpo
if os.path.exists('demandas.db'):
  os.remove('demandas.db')

conn = sqlite3.connect('demandas.db')
cursor = conn.cursor()

# 2. Criação das tabelas com PRIMARY KEY AUTOINCREMENT
cursor.execute('''
CREATE TABLE IF NOT EXISTS demandas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    descricao TEXT,
    solicitante TEXT,
    data_criacao TEXT
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
demandas = [
    (
        'Corrigir bug no login',
        'Usuários não conseguem fazer login',
        'João Silva',
        '2024-01-15 10:30:00',
    ),
    (
        'Implementar relatório de vendas',
        'Precisamos de um relatório mensal',
        'Maria Santos',
        '2024-01-16 14:20:00',
    ),
    (
        'Melhorar performance',
        'Sistema está lento',
        'Pedro Costa',
        '2024-01-17 09:15:00',
    ),
    (
        'Adicionar filtros',
        'Usuários querem filtrar demandas',
        'Ana Lima',
        '2024-01-18 11:00:00',
    ),
]

cursor.executemany(
    '''
INSERT INTO demandas (titulo, descricao, solicitante, data_criacao)
VALUES (?, ?, ?, ?)
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