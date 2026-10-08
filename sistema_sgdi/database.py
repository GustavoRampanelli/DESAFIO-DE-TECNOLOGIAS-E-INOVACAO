"""
Camada de Acesso a Dados e Migrações do SGDI.
Fornece conexão com o banco SQLite, verificação e execução de migrações
automáticas de esquema e queries padrão de demandas com cálculo de SLA.
"""

import sqlite3
from datetime import timedelta
from config import DB_PATH, SLA_DIAS_POR_PRIORIDADE, SLA_PADRAO_DIAS
from services.sla_service import parse_data


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


def listar_usuarios(conn):
    """Retorna lista de todos os usuários ordenados por nome."""
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
