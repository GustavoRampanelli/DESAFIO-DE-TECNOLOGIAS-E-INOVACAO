"""
Camada de Acesso a Dados e Migrações do SGDI.
Fornece conexão com o banco SQLite, verificação e execução de migrações
automáticas de esquema e queries padrão de demandas com cálculo de SLA.
"""

import sqlite3
from datetime import timedelta
from werkzeug.security import generate_password_hash
from config import (
    DB_PATH,
    SLA_DIAS_POR_PRIORIDADE,
    SLA_PADRAO_DIAS,
    PERFIL_ADMIN,
    PERFIL_COLABORADOR,
    SENHA_PADRAO,
    ADMIN_PADRAO
)
from services.sla_service import parse_data


# Trilha de auditoria (Sprint 5): append-only, protegida por triggers contra UPDATE/DELETE
SQL_TABELA_AUDITORIA = '''
CREATE TABLE IF NOT EXISTS logs_auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora TEXT NOT NULL,
    usuario_id INTEGER,
    usuario_nome TEXT,
    acao TEXT NOT NULL,
    entidade TEXT,
    entidade_id INTEGER,
    descricao TEXT NOT NULL,
    detalhes TEXT,
    ip TEXT,
    user_agent TEXT,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);
CREATE INDEX IF NOT EXISTS idx_logs_data_hora ON logs_auditoria (data_hora);
CREATE INDEX IF NOT EXISTS idx_logs_entidade ON logs_auditoria (entidade, entidade_id);
CREATE INDEX IF NOT EXISTS idx_logs_usuario ON logs_auditoria (usuario_id);
CREATE INDEX IF NOT EXISTS idx_logs_acao ON logs_auditoria (acao);
CREATE TRIGGER IF NOT EXISTS trg_logs_auditoria_bloqueia_update
BEFORE UPDATE ON logs_auditoria
BEGIN
    SELECT RAISE(ABORT, 'Registros de auditoria são imutáveis e não podem ser alterados.');
END;
CREATE TRIGGER IF NOT EXISTS trg_logs_auditoria_bloqueia_delete
BEFORE DELETE ON logs_auditoria
BEGIN
    SELECT RAISE(ABORT, 'Registros de auditoria são imutáveis e não podem ser excluídos.');
END;
'''


def get_db():
    """Retorna conexão ativa com o banco SQLite com Row Factory configurada."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def garantir_migracao_db(conn):
    """Garante que a coluna data_conclusao exista na tabela demandas e faz backfill se necessário."""
    cursor = conn.cursor()
    colunas = [col[1] for col in cursor.execute('PRAGMA table_info(demandas)').fetchall()]
    if 'data_conclusao' not in colunas:
        cursor.execute('ALTER TABLE demandas ADD COLUMN data_conclusao TEXT')
        conn.commit()

    # Preenche conclusões para demandas antigas com status Concluída que estejam sem data_conclusao
    concluidas_sem_data = cursor.execute(
        "SELECT id, data_criacao, prioridade FROM demandas WHERE status = 'Concluída' AND data_conclusao IS NULL"
    ).fetchall()
    
    for row in concluidas_sem_data:
        did = row['id']
        dc_str = row['data_criacao']
        pr = row['prioridade']
        sla = SLA_DIAS_POR_PRIORIDADE.get(pr, SLA_PADRAO_DIAS)
        dc = parse_data(dc_str)
        if dc:
            duracao_horas = max(6, int(sla * 24 * 0.45))
            dt_conc = (dc + timedelta(hours=duracao_horas)).strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('UPDATE demandas SET data_conclusao = ? WHERE id = ?', (dt_conc, did))
    if concluidas_sem_data:
        conn.commit()

    garantir_controle_acesso(conn)
    conn.executescript(SQL_TABELA_AUDITORIA)


def garantir_controle_acesso(conn):
    """Adiciona senha (hash) e perfil aos usuários e garante que exista ao menos um administrador."""
    cursor = conn.cursor()
    colunas = [col[1] for col in cursor.execute('PRAGMA table_info(usuarios)').fetchall()]
    if 'senha_hash' not in colunas:
        cursor.execute('ALTER TABLE usuarios ADD COLUMN senha_hash TEXT')
    if 'perfil' not in colunas:
        cursor.execute(f"ALTER TABLE usuarios ADD COLUMN perfil TEXT NOT NULL DEFAULT '{PERFIL_COLABORADOR}'")

    # Usuários anteriores à Sprint 5 recebem a senha padrão (armazenada apenas como hash)
    sem_senha = cursor.execute('SELECT id FROM usuarios WHERE senha_hash IS NULL').fetchall()
    for row in sem_senha:
        cursor.execute(
            'UPDATE usuarios SET senha_hash = ? WHERE id = ?',
            (generate_password_hash(SENHA_PADRAO), row['id'])
        )

    tem_admin = cursor.execute('SELECT 1 FROM usuarios WHERE perfil = ?', (PERFIL_ADMIN,)).fetchone()
    if not tem_admin:
        nome, email = ADMIN_PADRAO
        cursor.execute(
            'INSERT OR IGNORE INTO usuarios (nome, email, senha_hash, perfil) VALUES (?, ?, ?, ?)',
            (nome, email, generate_password_hash(SENHA_PADRAO), PERFIL_ADMIN)
        )
        cursor.execute('UPDATE usuarios SET perfil = ? WHERE email = ?', (PERFIL_ADMIN, email))

    conn.commit()


def listar_usuarios(conn):
    """Retorna lista de todos os usuários ordenados por nome (sem expor o hash de senha)."""
    return conn.execute('SELECT id, nome, email FROM usuarios ORDER BY nome').fetchall()


def ler_usuario_id(conn, valor):
    """Retorna o id do usuário se ele existir no banco; caso contrário None."""
    if not valor or not str(valor).isdigit():
        return None
    usuario = conn.execute('SELECT id FROM usuarios WHERE id = ?', (int(valor),)).fetchone()
    return usuario[0] if usuario else None


# Query padrão com joins e cálculo SQL de SLA / Fora do SLA (sem responsável = fora do SLA)
SELECT_DEMANDAS = '''
    SELECT d.*, s.nome AS solicitante_nome, r.nome AS responsavel_nome,
    datetime(d.data_criacao, '+' || (CASE d.prioridade WHEN 'Crítica' THEN 2 WHEN 'Alta' THEN 5 WHEN 'Média' THEN 10 WHEN 'Baixa' THEN 20 ELSE 30 END) || ' days') AS data_limite,
    (CASE
        WHEN d.status = 'Cancelada' THEN 'cancelada'
        WHEN d.status = 'Concluída' THEN
            (CASE WHEN d.data_conclusao IS NOT NULL AND d.data_conclusao > datetime(d.data_criacao, '+' || (CASE d.prioridade WHEN 'Crítica' THEN 2 WHEN 'Alta' THEN 5 WHEN 'Média' THEN 10 WHEN 'Baixa' THEN 20 ELSE 30 END) || ' days') THEN 'concluida_atrasada' ELSE 'concluida_no_prazo' END)
        WHEN d.responsavel_id IS NULL THEN 'sem_responsavel_fora_sla'
        WHEN datetime(d.data_criacao, '+' || (CASE d.prioridade WHEN 'Crítica' THEN 2 WHEN 'Alta' THEN 5 WHEN 'Média' THEN 10 WHEN 'Baixa' THEN 20 ELSE 30 END) || ' days') < datetime('now', 'localtime') THEN 'atrasada'
        ELSE 'no_prazo'
    END) AS status_sla
    FROM demandas d
    LEFT JOIN usuarios s ON s.id = d.solicitante_id
    LEFT JOIN usuarios r ON r.id = d.responsavel_id
'''
