"""
Serviço de Auditoria e Rastreabilidade do SGDI (Sprint 5).
Centraliza o registro padronizado das ações dos usuários na trilha append-only
`logs_auditoria`, o cálculo de diferenças (antes/depois) das demandas, as consultas
filtradas da tela de auditoria e o log técnico em arquivo para análise de incidentes.
"""

import os
import io
import csv
import json
import math
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from flask import request, session, has_request_context, Response
from config import (
    NOME_EMPRESA,
    NOME_ORGANIZACAO,
    ACOES_AUDITORIA,
    ACOES_SEGURANCA,
    POR_PAGINA_AUDITORIA,
    LOG_DIR,
    LOG_ARQUIVO,
    LOG_TAMANHO_MAX_BYTES,
    LOG_QTD_BACKUPS
)

logger = logging.getLogger('sgdi')

# Campos da demanda acompanhados na trilha: coluna -> rótulo legível
CAMPOS_DEMANDA = {
    'titulo': 'Título',
    'descricao': 'Descrição',
    'solicitante_id': 'Solicitante',
    'status': 'Status',
    'prioridade': 'Prioridade',
    'responsavel_id': 'Responsável',
    'data_conclusao': 'Data de conclusão',
}
CAMPOS_USUARIO = {'solicitante_id', 'responsavel_id'}


# =====================================================================
# LOG TÉCNICO EM ARQUIVO
# =====================================================================

def configurar_log_arquivo():
    """Configura o logger 'sgdi' com arquivo rotativo em logs/sgdi.log (formato padronizado)."""
    if logger.handlers:
        return logger
    os.makedirs(LOG_DIR, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_ARQUIVO,
        maxBytes=LOG_TAMANHO_MAX_BYTES,
        backupCount=LOG_QTD_BACKUPS,
        encoding='utf-8',
        delay=True
    )
    handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-7s | %(message)s', '%Y-%m-%d %H:%M:%S'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def registrar_erro(exception):
    """Registra no arquivo de log um erro não tratado com rota, usuário e stack trace."""
    usuario, ip, _ = _contexto_requisicao()
    rota = f'{request.method} {request.path}' if has_request_context() else '-'
    logger.error(
        'ERRO | rota=%s | usuario=%s | ip=%s | %s: %s',
        rota, usuario.get('nome') or '-', ip or '-', type(exception).__name__, exception,
        exc_info=exception
    )


# =====================================================================
# REGISTRO NA TRILHA DE AUDITORIA
# =====================================================================

def _contexto_requisicao():
    """Retorna (usuário da sessão, ip, user agent) quando há uma requisição ativa."""
    if not has_request_context():
        return {}, None, None
    usuario = {
        'id': session.get('usuario_id'),
        'nome': session.get('usuario_nome'),
    }
    user_agent = (request.user_agent.string or '')[:255]
    return usuario, request.remote_addr, user_agent


def registrar_log(conn, acao, descricao, entidade=None, entidade_id=None, detalhes=None, usuario=None):
    """
    Grava um evento na trilha de auditoria usando a conexão (e a transação) do chamador.
    Não faz commit: a operação de negócio e o seu log são confirmados juntos, garantindo
    que nunca exista alteração sem registro nem registro de alteração não efetivada.
    """
    usuario_sessao, ip, user_agent = _contexto_requisicao()
    usuario = usuario or usuario_sessao
    data_hora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn.execute(
        '''
        INSERT INTO logs_auditoria
        (data_hora, usuario_id, usuario_nome, acao, entidade, entidade_id, descricao, detalhes, ip, user_agent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            data_hora,
            usuario.get('id'),
            usuario.get('nome'),
            acao,
            entidade,
            entidade_id,
            descricao,
            json.dumps(detalhes, ensure_ascii=False, default=str) if detalhes else None,
            ip,
            user_agent,
        )
    )
    logger.info('AUDITORIA | %s | usuario=%s | %s', acao, usuario.get('nome') or '-', descricao)


# =====================================================================
# SNAPSHOT E DIFERENÇAS DE DEMANDAS
# =====================================================================

def _nomes_usuarios(conn):
    return {row['id']: row['nome'] for row in conn.execute('SELECT id, nome FROM usuarios').fetchall()}


def _valor_legivel(campo, valor, nomes):
    if campo in CAMPOS_USUARIO:
        return nomes.get(valor, f'Usuário #{valor}') if valor else None
    return valor if valor not in ('', None) else None


def snapshot_demanda(conn, demanda_id):
    """Retorna o estado legível da demanda (nomes no lugar de ids) ou None se não existir."""
    row = conn.execute('SELECT * FROM demandas WHERE id = ?', (demanda_id,)).fetchone()
    if not row:
        return None
    nomes = _nomes_usuarios(conn)
    estado = {rotulo: _valor_legivel(campo, row[campo], nomes) for campo, rotulo in CAMPOS_DEMANDA.items()}
    estado['Data de criação'] = row['data_criacao']
    return estado


def calcular_diferencas(conn, antes, depois):
    """Compara dois registros de demanda e retorna {rótulo: {'antes': x, 'depois': y}} só do que mudou."""
    nomes = _nomes_usuarios(conn)
    diferencas = {}
    for campo, rotulo in CAMPOS_DEMANDA.items():
        valor_antes = _valor_legivel(campo, antes[campo], nomes)
        valor_depois = _valor_legivel(campo, depois.get(campo), nomes)
        if valor_antes != valor_depois:
            diferencas[rotulo] = {'antes': valor_antes, 'depois': valor_depois}
    return diferencas


# =====================================================================
# CONSULTA DA TRILHA (TELA DE AUDITORIA E HISTÓRICO DA DEMANDA)
# =====================================================================

def construir_filtro_auditoria(filtros):
    """Monta WHERE parametrizado a partir dos filtros da tela de auditoria."""
    condicoes = []
    parametros = []

    usuario = str(filtros.get('usuario', '')).strip()
    if usuario.isdigit():
        condicoes.append('usuario_id = ?')
        parametros.append(int(usuario))

    acao = filtros.get('acao', '').strip()
    if acao == 'SEGURANCA':
        condicoes.append(f"acao IN ({', '.join('?' for _ in ACOES_SEGURANCA)})")
        parametros.extend(sorted(ACOES_SEGURANCA))
    elif acao in ACOES_AUDITORIA:
        condicoes.append('acao = ?')
        parametros.append(acao)

    demanda = str(filtros.get('demanda', '')).strip().lstrip('#')
    if demanda.isdigit():
        condicoes.append("entidade = 'demanda' AND entidade_id = ?")
        parametros.append(int(demanda))

    data_inicio = filtros.get('data_inicio', '').strip()
    if data_inicio:
        condicoes.append('data_hora >= ?')
        parametros.append(f'{data_inicio} 00:00:00')

    data_fim = filtros.get('data_fim', '').strip()
    if data_fim:
        condicoes.append('data_hora <= ?')
        parametros.append(f'{data_fim} 23:59:59')

    where = 'WHERE ' + ' AND '.join(condicoes) if condicoes else ''
    return where, parametros


def _formatar_logs(rows):
    """Converte registros em dicts, decodificando o JSON de detalhes e o rótulo da ação."""
    logs = []
    for row in rows:
        log = dict(row)
        log['acao_label'] = ACOES_AUDITORIA.get(log['acao'], log['acao'])
        try:
            log['detalhes'] = json.loads(log['detalhes']) if log['detalhes'] else {}
        except ValueError:
            log['detalhes'] = {'Registro': log['detalhes']}
        logs.append(log)
    return logs


def listar_logs(conn, filtros, pagina=1):
    """Retorna logs filtrados e paginados (mais recentes primeiro) com totais de paginação."""
    where, parametros = construir_filtro_auditoria(filtros)
    total = conn.execute(f'SELECT COUNT(*) FROM logs_auditoria {where}', parametros).fetchone()[0]
    total_paginas = max(1, math.ceil(total / POR_PAGINA_AUDITORIA))
    pagina = min(max(pagina, 1), total_paginas)

    rows = conn.execute(
        f'SELECT * FROM logs_auditoria {where} ORDER BY id DESC LIMIT ? OFFSET ?',
        parametros + [POR_PAGINA_AUDITORIA, (pagina - 1) * POR_PAGINA_AUDITORIA]
    ).fetchall()
    return _formatar_logs(rows), total, pagina, total_paginas


def listar_todos_logs(conn, filtros):
    """Retorna todos os logs filtrados (sem paginação) para exportação."""
    where, parametros = construir_filtro_auditoria(filtros)
    rows = conn.execute(f'SELECT * FROM logs_auditoria {where} ORDER BY id DESC', parametros).fetchall()
    return _formatar_logs(rows)


def logs_da_demanda(conn, demanda_id):
    """Linha do tempo de auditoria de uma demanda específica (ordem cronológica)."""
    rows = conn.execute(
        "SELECT * FROM logs_auditoria WHERE entidade = 'demanda' AND entidade_id = ? ORDER BY id ASC",
        (demanda_id,)
    ).fetchall()
    return _formatar_logs(rows)


def resumo_auditoria(conn):
    """KPIs da trilha: total de eventos, eventos de hoje, alertas de segurança e usuários ativos."""
    hoje = datetime.now().strftime('%Y-%m-%d')
    _, params_seguranca = construir_filtro_auditoria({'acao': 'SEGURANCA'})
    return {
        'data_hoje': hoje,
        'total': conn.execute('SELECT COUNT(*) FROM logs_auditoria').fetchone()[0],
        'hoje': conn.execute('SELECT COUNT(*) FROM logs_auditoria WHERE data_hora >= ?', (f'{hoje} 00:00:00',)).fetchone()[0],
        'seguranca': conn.execute(
            f"SELECT COUNT(*) FROM logs_auditoria WHERE acao IN ({', '.join('?' for _ in params_seguranca)})",
            params_seguranca
        ).fetchone()[0],
        'exclusoes': conn.execute("SELECT COUNT(*) FROM logs_auditoria WHERE acao = 'EXCLUIR'").fetchone()[0],
    }


def _detalhes_texto(detalhes):
    partes = []
    for chave, valor in detalhes.items():
        if isinstance(valor, dict) and 'antes' in valor:
            partes.append(f"{chave}: {valor['antes'] or '-'} -> {valor['depois'] or '-'}")
        else:
            partes.append(f'{chave}: {valor if valor not in (None, "") else "-"}')
    return ' | '.join(partes)


def gerar_csv_auditoria(logs, filtros):
    """Gera o relatório CSV da trilha de auditoria (utf-8-sig, delimitador ;) no padrão dos demais relatórios."""
    sio = io.StringIO()
    writer = csv.writer(sio, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    writer.writerow([f'{NOME_EMPRESA} - {NOME_ORGANIZACAO}'])
    writer.writerow(['RELATÓRIO DE AUDITORIA E RASTREABILIDADE'])
    writer.writerow([])
    writer.writerow(['ID', 'Data/Hora', 'Usuário', 'Ação', 'Entidade', 'ID Entidade', 'Descrição', 'Detalhes', 'IP'])

    for log in logs:
        writer.writerow([
            log['id'],
            log['data_hora'],
            log['usuario_nome'] or 'Não identificado',
            log['acao_label'],
            log['entidade'] or '-',
            log['entidade_id'] or '-',
            log['descricao'],
            _detalhes_texto(log['detalhes']),
            log['ip'] or '-',
        ])

    writer.writerow([])
    filtros_txt = ', '.join(f'{k}={v}' for k, v in filtros.items() if v) or 'Nenhum'
    writer.writerow(['Filtros aplicados', filtros_txt])
    writer.writerow(['Total de eventos', len(logs)])
    writer.writerow(['Gerado em', datetime.now().strftime('%d/%m/%Y %H:%M:%S')])

    nome_arquivo = f"auditoria_sgdi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        sio.getvalue().encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={nome_arquivo}'}
    )
