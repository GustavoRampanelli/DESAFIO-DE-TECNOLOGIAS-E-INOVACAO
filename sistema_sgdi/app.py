import os
import math
import sqlite3
import io
import csv
from datetime import datetime, timedelta
import werkzeug
if not hasattr(werkzeug, '__version__'):
    try:
        import importlib.metadata
        werkzeug.__version__ = importlib.metadata.version('werkzeug')
    except Exception:
        werkzeug.__version__ = '3.1.3'

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, Response
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from markdown_pdf import MarkdownPdf, Section

app = Flask(__name__)
app.secret_key = '123456'

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'demandas.db')
NOME_EMPRESA = 'SGDI - Sistema de Gestão de Demandas Internas'
NOME_ORGANIZACAO = 'SSR - Gestão & Governança'


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# Configurações de paginação, status, prioridades e pesos
POR_PAGINA = 10
STATUS_OPCOES = ['Aberta', 'Em andamento', 'Concluída', 'Cancelada']
PRIORIDADE_OPCOES = ['Baixa', 'Média', 'Alta', 'Crítica']
PRIORIDADE_PADRAO = 'Média'

# Pesos de criticidade: Críticos pesam mais que Médio
PESO_PRIORIDADE = {
    'Crítica': 4,
    'Alta': 3,
    'Média': 2,
    'Baixa': 1,
}

# SLA Inteligente por Prioridade (em dias)
SLA_DIAS_POR_PRIORIDADE = {
    'Crítica': 2,
    'Alta': 5,
    'Média': 10,
    'Baixa': 20,
}
SLA_PADRAO_DIAS = 30

FILTROS_OPCOES = {
    'status': STATUS_OPCOES,
    'prioridade': PRIORIDADE_OPCOES,
}


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


def parse_data(valor):
    """Converte string para datetime com múltiplos formatos suportados."""
    if not valor:
        return None
    val = str(valor).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d'):
        try:
            return datetime.strptime(val[:19] if len(val) >= 19 and fmt == '%Y-%m-%d %H:%M:%S' else val, fmt)
        except (ValueError, TypeError):
            pass
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return None


def formatar_tempo_resolucao(dias):
    """Formata a duração em dias e horas de maneira amigável em português."""
    if dias is None or dias <= 0:
        return "0h"
    if dias < 1.0:
        horas = round(dias * 24.0, 1)
        if horas.is_integer():
            horas = int(horas)
        return f"{horas}h"
    elif dias < 2.0:
        horas_rest = round((dias - 1.0) * 24.0)
        if horas_rest > 0:
            return f"1 dia e {horas_rest}h"
        return "1 dia"
    else:
        return f"{dias:.1f} dias".replace('.', ',')


def calcular_prazo(prioridade):
    """Retorna o prazo de SLA configurado para a prioridade."""
    dias = SLA_DIAS_POR_PRIORIDADE.get(prioridade, SLA_PADRAO_DIAS)
    return f"{dias} dias"


def listar_usuarios(conn):
    return conn.execute('SELECT id, nome, email FROM usuarios ORDER BY nome').fetchall()


def ler_usuario_id(conn, valor):
    """Retorna o id do usuário se ele existir; caso contrário None."""
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


def construir_filtro_sql(filtros_req):
    """Monta cláusula WHERE e parâmetros SQL a partir dos filtros recebidos."""
    condicoes = []
    parametros = []
    agora = datetime.now()

    # Filtro de Busca por termo
    termo = (filtros_req.get('q') or '').strip()
    if termo:
        condicoes.append('d.titulo LIKE ?')
        parametros.append(f'%{termo}%')

    # Filtro de Status
    status = filtros_req.get('status', '').strip()
    if status in STATUS_OPCOES:
        condicoes.append('d.status = ?')
        parametros.append(status)

    # Filtro de Prioridade
    prioridade = filtros_req.get('prioridade', '').strip()
    if prioridade in PRIORIDADE_OPCOES:
        condicoes.append('d.prioridade = ?')
        parametros.append(prioridade)

    # Filtro de Responsável
    responsavel = str(filtros_req.get('responsavel', '')).strip()
    if responsavel == 'sem_responsavel':
        condicoes.append('d.responsavel_id IS NULL')
    elif responsavel.isdigit():
        condicoes.append('d.responsavel_id = ?')
        parametros.append(int(responsavel))

    # Filtro de Período (7d, 30d, 90d, custom)
    periodo = filtros_req.get('periodo', 'todos').strip()
    if periodo == '7d':
        dt_limite = (agora - timedelta(days=7)).strftime('%Y-%m-%d 00:00:00')
        condicoes.append('d.data_criacao >= ?')
        parametros.append(dt_limite)
    elif periodo == '30d':
        dt_limite = (agora - timedelta(days=30)).strftime('%Y-%m-%d 00:00:00')
        condicoes.append('d.data_criacao >= ?')
        parametros.append(dt_limite)
    elif periodo == '90d':
        dt_limite = (agora - timedelta(days=90)).strftime('%Y-%m-%d 00:00:00')
        condicoes.append('d.data_criacao >= ?')
        parametros.append(dt_limite)
    elif periodo == 'custom':
        dt_ini = filtros_req.get('data_inicio', '').strip()
        dt_fim = filtros_req.get('data_fim', '').strip()
        if dt_ini:
            condicoes.append('d.data_criacao >= ?')
            parametros.append(f'{dt_ini} 00:00:00')
        if dt_fim:
            condicoes.append('d.data_criacao <= ?')
            parametros.append(f'{dt_fim} 23:59:59')

    # Filtro de Prazo / SLA
    prazo = filtros_req.get('prazo', '').strip()
    if prazo == 'atrasadas':
        condicoes.append(
            "d.status NOT IN ('Concluída', 'Cancelada') AND (d.responsavel_id IS NULL OR datetime(d.data_criacao, '+' || (CASE d.prioridade WHEN 'Crítica' THEN 2 WHEN 'Alta' THEN 5 WHEN 'Média' THEN 10 WHEN 'Baixa' THEN 20 ELSE 30 END) || ' days') < datetime('now', 'localtime'))"
        )
    elif prazo == 'no_prazo':
        condicoes.append(
            "d.status = 'Concluída' OR (d.status != 'Cancelada' AND d.responsavel_id IS NOT NULL AND datetime(d.data_criacao, '+' || (CASE d.prioridade WHEN 'Crítica' THEN 2 WHEN 'Alta' THEN 5 WHEN 'Média' THEN 10 WHEN 'Baixa' THEN 20 ELSE 30 END) || ' days') >= datetime('now', 'localtime'))"
        )

    where = 'WHERE ' + ' AND '.join(condicoes) if condicoes else ''
    return where, parametros


def obter_metricas_analytics(conn, filtros_req=None):
    """Calcula todas as métricas gerais, de SLA, por responsável, evolução temporal e tempo médio."""
    filtros_req = filtros_req or {}
    where, parametros = construir_filtro_sql(filtros_req)

    cursor = conn.cursor()
    demandas = cursor.execute(f'{SELECT_DEMANDAS} {where} ORDER BY d.id ASC', parametros).fetchall()
    usuarios = listar_usuarios(conn)
    agora = datetime.now()

    total_demandas = len(demandas)
    total_abertas = 0
    total_em_andamento = 0
    total_concluidas = 0
    total_canceladas = 0

    total_atrasadas_prazo = 0
    total_sem_resp_fora_sla = 0
    total_no_prazo = 0
    concluidas_no_prazo = 0
    concluidas_atrasadas = 0

    tempos_conclusao = []
    tempos_por_prioridade = {p: [] for p in PRIORIDADE_OPCOES}
    concluidas_detalhadas = []
    demandas_atencao = []

    # Mapas para responsáveis
    usuarios_map = {u['id']: u['nome'] for u in usuarios}
    resp_stats = {u['id']: {
        'id': u['id'],
        'nome': u['nome'],
        'email': u['email'] or '',
        'iniciais': ''.join(p[0].upper() for p in u['nome'].split()[:2]),
        'total': 0,
        'abertas': 0,
        'em_andamento': 0,
        'concluidas': 0,
        'canceladas': 0,
        'fora_sla': 0,
        'pontos_criticidade': 0,
        'tempos': []
    } for u in usuarios}

    resp_stats[None] = {
        'id': None,
        'nome': 'Sem responsável (Não atribuído)',
        'email': 'Nenhum',
        'iniciais': 'SR',
        'total': 0,
        'abertas': 0,
        'em_andamento': 0,
        'concluidas': 0,
        'canceladas': 0,
        'fora_sla': 0,
        'pontos_criticidade': 0,
        'tempos': []
    }

    prioridade_stats = {p: {
        'prioridade': p,
        'peso': PESO_PRIORIDADE[p],
        'sla_dias': SLA_DIAS_POR_PRIORIDADE.get(p, SLA_PADRAO_DIAS),
        'total': 0,
        'abertas': 0,
        'em_andamento': 0,
        'concluidas': 0,
        'canceladas': 0,
        'fora_sla': 0,
        'tempos': []
    } for p in PRIORIDADE_OPCOES}

    # Agrupamentos para Evolução Temporal
    datas_criacao_map = {}
    datas_conclusao_map = {}

    pontos_criticidade_ativas_total = 0
    total_ativas_contadas = 0

    for d in demandas:
        st = d['status']
        pr = d['prioridade']
        resp_id = d['responsavel_id']
        peso = PESO_PRIORIDADE.get(pr, 2)
        dc = parse_data(d['data_criacao'])
        df = parse_data(d['data_conclusao'])
        sla_dias = SLA_DIAS_POR_PRIORIDADE.get(pr, SLA_PADRAO_DIAS)
        data_limite = dc + timedelta(days=sla_dias) if dc else None

        # Registro para Evolução Temporal
        if dc:
            dia_c = dc.strftime('%Y-%m-%d')
            datas_criacao_map[dia_c] = datas_criacao_map.get(dia_c, 0) + 1

        # Contagem de status
        if st == 'Aberta':
            total_abertas += 1
        elif st == 'Em andamento':
            total_em_andamento += 1
        elif st == 'Concluída':
            total_concluidas += 1
            if df:
                dia_f = df.strftime('%Y-%m-%d')
                datas_conclusao_map[dia_f] = datas_conclusao_map.get(dia_f, 0) + 1
        elif st == 'Cancelada':
            total_canceladas += 1

        # Estatísticas de responsável
        r_entry = resp_stats.get(resp_id, resp_stats[None])
        r_entry['total'] += 1
        if st == 'Aberta':
            r_entry['abertas'] += 1
        elif st == 'Em andamento':
            r_entry['em_andamento'] += 1
        elif st == 'Concluída':
            r_entry['concluidas'] += 1
        elif st == 'Cancelada':
            r_entry['canceladas'] += 1

        # Estatísticas de prioridade
        p_entry = prioridade_stats.get(pr)
        if p_entry:
            p_entry['total'] += 1
            if st == 'Aberta':
                p_entry['abertas'] += 1
            elif st == 'Em andamento':
                p_entry['em_andamento'] += 1
            elif st == 'Concluída':
                p_entry['concluidas'] += 1
            elif st == 'Cancelada':
                p_entry['canceladas'] += 1

        # Ponderação de criticidade para demandas ativas
        if st in ('Aberta', 'Em andamento'):
            pontos_criticidade_ativas_total += peso
            total_ativas_contadas += 1
            r_entry['pontos_criticidade'] += peso

        # LÓGICA DE TEMPO MÉDIO E SLA:
        # Cancelados fora do tempo médio!
        if st == 'Concluída':
            if dc and df:
                duracao_dias = max(0.01, (df - dc).total_seconds() / 86400.0)
                tempos_conclusao.append(duracao_dias)
                r_entry['tempos'].append(duracao_dias)
                if p_entry:
                    p_entry['tempos'].append(duracao_dias)

                is_concluida_atrasada = bool(data_limite and df > data_limite)
                if is_concluida_atrasada:
                    concluidas_atrasadas += 1
                else:
                    concluidas_no_prazo += 1

                concluidas_detalhadas.append({
                    'id': d['id'],
                    'titulo': d['titulo'],
                    'prioridade': pr,
                    'responsavel_nome': d['responsavel_nome'] or 'Sem responsável',
                    'duracao_dias': duracao_dias,
                    'tempo_formatado': formatar_tempo_resolucao(duracao_dias),
                    'data_conclusao': d['data_conclusao'],
                    'atrasada': is_concluida_atrasada
                })
        elif st != 'Cancelada':
            # Demanda Ativa (Aberta ou Em andamento)
            # REGRA: sem responsável = fora do SLA!
            is_sem_resp = (resp_id is None)
            is_prazo_estourado = bool(data_limite and agora > data_limite)
            is_fora_sla = is_sem_resp or is_prazo_estourado

            if is_fora_sla:
                if is_sem_resp:
                    total_sem_resp_fora_sla += 1
                if is_prazo_estourado:
                    total_atrasadas_prazo += 1

                r_entry['fora_sla'] += 1
                if p_entry:
                    p_entry['fora_sla'] += 1

                dias_atraso = (agora - data_limite).total_seconds() / 86400.0 if data_limite and agora > data_limite else 0
                motivo = "Sem responsável (fora do SLA)" if is_sem_resp else f"Prazo estourado (+{round(dias_atraso, 1)} dias)"
                
                demandas_atencao.append({
                    'id': d['id'],
                    'titulo': d['titulo'],
                    'status': st,
                    'prioridade': pr,
                    'peso': peso,
                    'responsavel_nome': d['responsavel_nome'] or 'Não atribuído',
                    'responsavel_id': d['responsavel_id'],
                    'data_criacao': d['data_criacao'],
                    'data_limite': data_limite.strftime('%Y-%m-%d %H:%M:%S') if data_limite else '-',
                    'dias_atraso': round(dias_atraso, 1),
                    'motivo': motivo,
                    'atrasada': True,
                    'sem_responsavel': is_sem_resp
                })
            else:
                total_no_prazo += 1
                dias_restantes = (data_limite - agora).total_seconds() / 86400.0 if data_limite else 0
                if dias_restantes <= 2:
                    demandas_atencao.append({
                        'id': d['id'],
                        'titulo': d['titulo'],
                        'status': st,
                        'prioridade': pr,
                        'peso': peso,
                        'responsavel_nome': d['responsavel_nome'] or 'Não atribuído',
                        'responsavel_id': d['responsavel_id'],
                        'data_criacao': d['data_criacao'],
                        'data_limite': data_limite.strftime('%Y-%m-%d %H:%M:%S') if data_limite else '-',
                        'dias_restantes': round(dias_restantes, 1),
                        'motivo': f"Vence em breve ({round(dias_restantes, 1)} dias)",
                        'atrasada': False,
                        'sem_responsavel': False
                    })

    # Total geral fora do SLA (atrasadas por prazo + sem responsável)
    total_fora_sla = (total_atrasadas_prazo + total_sem_resp_fora_sla)

    # Tempo médio de resolução geral (APENAS Concluídas - Canceladas fora do cálculo!)
    tempo_medio_dias = (sum(tempos_conclusao) / len(tempos_conclusao)) if tempos_conclusao else 0.0
    tempo_medio_horas = tempo_medio_dias * 24.0

    # Índice de Severidade / Criticidade Ponderada (Escala 1 a 4)
    # Críticos pesam mais que médio (Crítica=4, Alta=3, Média=2, Baixa=1)
    if total_ativas_contadas > 0:
        score_severidade = round(pontos_criticidade_ativas_total / total_ativas_contadas, 2)
        if score_severidade >= 3.0:
            severidade_classificacao = 'Severidade Alta / Crítica'
        elif score_severidade >= 2.0:
            severidade_classificacao = 'Severidade Moderada'
        else:
            severidade_classificacao = 'Severidade Baixa'
    else:
        score_severidade = 0.0
        severidade_classificacao = 'Sem demandas ativas'

    # Ordena recordes
    concluidas_detalhadas.sort(key=lambda x: x['duracao_dias'])
    demanda_mais_rapida = concluidas_detalhadas[0] if concluidas_detalhadas else None
    demanda_mais_lenta = concluidas_detalhadas[-1] if concluidas_detalhadas else None

    # Ordena demandas que requerem atenção: críticas e com maior atraso primeiro
    demandas_atencao.sort(key=lambda x: (x['peso'], x.get('dias_atraso', 0)), reverse=True)

    # Preparação da Evolução Temporal (últimos dias ordenados)
    todas_datas = sorted(set(list(datas_criacao_map.keys()) + list(datas_conclusao_map.keys())))
    if len(todas_datas) > 14:
        todas_datas = todas_datas[-14:]
    
    evolucao_labels = [datetime.strptime(d, '%Y-%m-%d').strftime('%d/%m') for d in todas_datas]
    evolucao_criadas = [datas_criacao_map.get(d, 0) for d in todas_datas]
    evolucao_concluidas = [datas_conclusao_map.get(d, 0) for d in todas_datas]

    # Lista consolidada por responsável
    total_ativas_geral = total_abertas + total_em_andamento
    lista_resp_stats = []
    for r_id, r in resp_stats.items():
        if r['total'] == 0 and r_id is None:
            continue
        ativas_u = r['abertas'] + r['em_andamento']
        carga_pct = round((ativas_u / total_ativas_geral * 100), 1) if total_ativas_geral > 0 else 0.0
        taxa_conclusao = round((r['concluidas'] / r['total'] * 100), 1) if r['total'] > 0 else 0.0
        tempo_med = (sum(r['tempos']) / len(r['tempos'])) if r['tempos'] else None

        lista_resp_stats.append({
            'id': r['id'],
            'nome': r['nome'],
            'email': r['email'],
            'iniciais': r['iniciais'],
            'total': r['total'],
            'abertas': r['abertas'],
            'em_andamento': r['em_andamento'],
            'concluidas': r['concluidas'],
            'canceladas': r['canceladas'],
            'fora_sla': r['fora_sla'],
            'atrasadas': r['fora_sla'],
            'taxa_conclusao': taxa_conclusao,
            'tempo_medio_dias': round(tempo_med, 2) if tempo_med else None,
            'tempo_medio_formatado': formatar_tempo_resolucao(tempo_med) if tempo_med else 'N/A',
            'pontos_criticidade': r['pontos_criticidade'],
            'carga_trabalho_pct': carga_pct
        })
    lista_resp_stats.sort(key=lambda x: x['total'], reverse=True)

    # Lista consolidada por prioridade
    lista_prioridade_stats = []
    for pr in PRIORIDADE_OPCOES:
        p = prioridade_stats[pr]
        tempo_med = (sum(p['tempos']) / len(p['tempos'])) if p['tempos'] else None
        lista_prioridade_stats.append({
            'prioridade': pr,
            'peso': p['peso'],
            'sla_dias': p['sla_dias'],
            'total': p['total'],
            'abertas': p['abertas'],
            'em_andamento': p['em_andamento'],
            'concluidas': p['concluidas'],
            'canceladas': p['canceladas'],
            'fora_sla': p['fora_sla'],
            'atrasadas': p['fora_sla'],
            'tempo_medio_dias': round(tempo_med, 2) if tempo_med else None,
            'tempo_medio_formatado': formatar_tempo_resolucao(tempo_med) if tempo_med else 'N/A',
        })

    # Percentuais gerais
    pct_abertas = round((total_abertas / total_demandas * 100), 1) if total_demandas > 0 else 0.0
    pct_em_andamento = round((total_em_andamento / total_demandas * 100), 1) if total_demandas > 0 else 0.0
    pct_concluidas = round((total_concluidas / total_demandas * 100), 1) if total_demandas > 0 else 0.0
    pct_canceladas = round((total_canceladas / total_demandas * 100), 1) if total_demandas > 0 else 0.0
    taxa_fora_sla_ativas = round((total_fora_sla / total_ativas_geral * 100), 1) if total_ativas_geral > 0 else 0.0

    total_avaliadas_sla = concluidas_no_prazo + concluidas_atrasadas + total_fora_sla + total_no_prazo
    total_no_sla = concluidas_no_prazo + total_no_prazo
    taxa_sla_geral = round((total_no_sla / total_avaliadas_sla * 100), 1) if total_avaliadas_sla > 0 else 100.0

    # Construção de texto dos filtros aplicados para o rodapé
    partes_filtros = []
    p_tipo = filtros_req.get('periodo', 'todos')
    if p_tipo == '7d': partes_filtros.append('Período: Últimos 7 dias')
    elif p_tipo == '30d': partes_filtros.append('Período: Últimos 30 dias')
    elif p_tipo == '90d': partes_filtros.append('Período: Últimos 90 dias')
    elif p_tipo == 'custom': partes_filtros.append(f"Período: {filtros_req.get('data_inicio', '')} até {filtros_req.get('data_fim', '')}")
    else: partes_filtros.append('Período: Todo o histórico')

    resp_f = filtros_req.get('responsavel', '')
    if resp_f == 'sem_responsavel': partes_filtros.append('Responsável: Sem responsável')
    elif resp_f.isdigit(): partes_filtros.append(f"Responsável: {usuarios_map.get(int(resp_f), resp_f)}")
    else: partes_filtros.append('Responsável: Todos')

    pr_f = filtros_req.get('prioridade', '')
    partes_filtros.append(f'Prioridade: {pr_f if pr_f else "Todas"}')

    st_f = filtros_req.get('status', '')
    partes_filtros.append(f'Status: {st_f if st_f else "Todos"}')

    texto_filtros = ' | '.join(partes_filtros)
    timestamp_geracao = agora.strftime('%d/%m/%Y às %H:%M:%S')

    return {
        'total_demandas': total_demandas,
        'total_abertas': total_abertas,
        'total_em_andamento': total_em_andamento,
        'total_concluidas': total_concluidas,
        'total_canceladas': total_canceladas,
        'total_pendentes': total_ativas_geral,
        'pct_abertas': pct_abertas,
        'pct_em_andamento': pct_em_andamento,
        'pct_concluidas': pct_concluidas,
        'pct_canceladas': pct_canceladas,
        'total_fora_sla': total_fora_sla,
        'total_atrasadas': total_fora_sla,
        'total_atrasadas_prazo': total_atrasadas_prazo,
        'total_sem_resp_fora_sla': total_sem_resp_fora_sla,
        'total_no_prazo': total_no_prazo,
        'concluidas_no_prazo': concluidas_no_prazo,
        'concluidas_atrasadas': concluidas_atrasadas,
        'taxa_fora_sla_ativas': taxa_fora_sla_ativas,
        'taxa_atraso_ativas': taxa_fora_sla_ativas,
        'taxa_sla_geral': taxa_sla_geral,
        'tempo_medio_dias': round(tempo_medio_dias, 2),
        'tempo_medio_horas': round(tempo_medio_horas, 1),
        'tempo_medio_formatado': formatar_tempo_resolucao(tempo_medio_dias),
        'total_concluidas_com_tempo': len(tempos_conclusao),
        'score_severidade': score_severidade,
        'severidade_classificacao': severidade_classificacao,
        'evolucao_temporal': {
            'labels': evolucao_labels,
            'criadas': evolucao_criadas,
            'concluidas': evolucao_concluidas
        },
        'usuarios_stats': lista_resp_stats,
        'prioridade_stats': lista_prioridade_stats,
        'demanda_mais_rapida': demanda_mais_rapida,
        'demanda_mais_lenta': demanda_mais_lenta,
        'demandas_atencao': demandas_atencao[:6],
        'filtros_aplicados': filtros_req,
        'texto_filtros': texto_filtros,
        'timestamp_geracao': timestamp_geracao,
        'demandas_lista': [dict(d) for d in demandas]
    }


# =====================================================================
# ROTAS PRINCIPAIS & ANALYTICS
# =====================================================================

@app.route('/')
@app.route('/dashboard')
@app.route('/analytics')
def index():
    """Painel Principal da Aplicação: Dashboard Analítico completo com filtros dinâmicos."""
    # Se o usuário passou parâmetros específicos de paginação da listagem
    if 'pagina' in request.args:
        return redirect(url_for('demandas', **request.args))

    conn = get_db()
    garantir_migracao_db(conn)
    filtros = request.args.to_dict()
    metricas = obter_metricas_analytics(conn, filtros)
    usuarios = listar_usuarios(conn)
    conn.close()

    return render_template(
        'dashboard.html',
        metricas=metricas,
        filtros=filtros,
        usuarios=usuarios,
        status_opcoes=STATUS_OPCOES,
        prioridade_opcoes=PRIORIDADE_OPCOES
    )


@app.route('/api/analytics')
def api_analytics():
    """Endpoint JSON para atualização dinâmica dos gráficos e KPIs via JavaScript."""
    conn = get_db()
    garantir_migracao_db(conn)
    filtros = request.args.to_dict()
    metricas = obter_metricas_analytics(conn, filtros)
    conn.close()
    return jsonify(metricas)


@app.route('/demandas')
def demandas():
    """Listagem detalhada de demandas com filtros combinados, busca e paginação."""
    pagina = request.args.get('pagina', 1, type=int)
    filtros = request.args.to_dict()

    where, parametros = construir_filtro_sql(filtros)

    conn = get_db()
    garantir_migracao_db(conn)

    total = conn.execute(f'SELECT COUNT(*) FROM demandas d {where}', parametros).fetchone()[0]
    total_paginas = max(1, math.ceil(total / POR_PAGINA))
    pagina = min(max(pagina, 1), total_paginas)

    demandas_lista = conn.execute(
        f'{SELECT_DEMANDAS} {where} ORDER BY d.id DESC LIMIT ? OFFSET ?',
        parametros + [POR_PAGINA, (pagina - 1) * POR_PAGINA]
    ).fetchall()

    usuarios = listar_usuarios(conn)

    # Mini-resumo de KPIs para cabeçalho da listagem
    total_geral = conn.execute('SELECT COUNT(*) FROM demandas').fetchone()[0]
    abertas_geral = conn.execute("SELECT COUNT(*) FROM demandas WHERE status = 'Aberta'").fetchone()[0]
    concluidas_geral = conn.execute("SELECT COUNT(*) FROM demandas WHERE status = 'Concluída'").fetchone()[0]
    canceladas_geral = conn.execute("SELECT COUNT(*) FROM demandas WHERE status = 'Cancelada'").fetchone()[0]
    fora_sla_geral = conn.execute(
        "SELECT COUNT(*) FROM demandas WHERE status NOT IN ('Concluída', 'Cancelada') AND (responsavel_id IS NULL OR datetime(data_criacao, '+' || (CASE prioridade WHEN 'Crítica' THEN 2 WHEN 'Alta' THEN 5 WHEN 'Média' THEN 10 WHEN 'Baixa' THEN 20 ELSE 30 END) || ' days') < datetime('now', 'localtime'))"
    ).fetchone()[0]

    conn.close()

    resumo_kpis = {
        'total': total_geral,
        'abertas': abertas_geral,
        'concluidas': concluidas_geral,
        'canceladas': canceladas_geral,
        'atrasadas': fora_sla_geral
    }

    return render_template(
        'index.html',
        demandas=demandas_lista,
        pagina=pagina,
        total_paginas=total_paginas,
        total=total,
        filtros=filtros,
        status_opcoes=STATUS_OPCOES,
        prioridade_opcoes=PRIORIDADE_OPCOES,
        usuarios=usuarios,
        resumo_kpis=resumo_kpis
    )


@app.context_processor
def inject_global_stats():
    """Injeta contagem rápida de demandas críticas/atrasadas para o ribbon de navegação do Obsidian."""
    try:
        conn = get_db()
        count_urgentes = conn.execute(
            "SELECT COUNT(*) FROM demandas WHERE status NOT IN ('Concluída', 'Cancelada') AND (prioridade = 'Crítica' OR responsavel_id IS NULL OR datetime(data_criacao, '+' || (CASE prioridade WHEN 'Crítica' THEN 2 WHEN 'Alta' THEN 5 WHEN 'Média' THEN 10 WHEN 'Baixa' THEN 20 ELSE 30 END) || ' days') < datetime('now', 'localtime'))"
        ).fetchone()[0]
        conn.close()
        return {'total_urgentes_global': count_urgentes}
    except Exception:
        return {'total_urgentes_global': 0}


@app.route('/criticas-atrasadas')
@app.route('/urgentes')
def criticas_atrasadas():
    """Visão dedicada e War Room de Triagem: Demandas Críticas e/ou Fora do SLA (Obsidian Workspace)."""
    aba_filtro = request.args.get('aba', 'todas')
    conn = get_db()
    garantir_migracao_db(conn)

    query_urgentes = f'''
        {SELECT_DEMANDAS}
        WHERE d.status NOT IN ('Concluída', 'Cancelada')
        AND (
            d.prioridade = 'Crítica'
            OR d.responsavel_id IS NULL
            OR datetime(d.data_criacao, '+' || (CASE d.prioridade WHEN 'Crítica' THEN 2 WHEN 'Alta' THEN 5 WHEN 'Média' THEN 10 WHEN 'Baixa' THEN 20 ELSE 30 END) || ' days') < datetime('now', 'localtime')
        )
        ORDER BY 
            (CASE WHEN d.prioridade = 'Crítica' AND (d.responsavel_id IS NULL OR datetime(d.data_criacao, '+2 days') < datetime('now', 'localtime')) THEN 1
                  WHEN d.prioridade = 'Crítica' THEN 2
                  WHEN d.responsavel_id IS NULL THEN 3
                  ELSE 4 END) ASC,
            d.data_criacao ASC
    '''

    todas_urgentes = conn.execute(query_urgentes).fetchall()
    usuarios = listar_usuarios(conn)
    conn.close()

    agora = datetime.now()

    lista_processada = []
    total_criticas_atrasadas = 0
    total_criticas_no_prazo = 0
    total_outras_atrasadas = 0
    total_sem_responsavel = 0

    for row in todas_urgentes:
        d = dict(row)
        pr = d['prioridade']
        st_sla = d['status_sla']
        is_sem_resp = (d['responsavel_id'] is None)
        is_critica = (pr == 'Crítica')
        is_atrasada_ou_fora = (st_sla in ('atrasada', 'sem_responsavel_fora_sla'))

        # Classificação de severidade e emergência
        if is_critica and is_atrasada_ou_fora:
            categoria = 'critica_atrasada'
            categoria_label = '🔥 Crítica Atrasada'
            categoria_classe = 'urgencia-maxima'
            total_criticas_atrasadas += 1
        elif is_critica:
            categoria = 'critica_prazo'
            categoria_label = '⚡ Crítica no Prazo'
            categoria_classe = 'urgencia-alta'
            total_criticas_no_prazo += 1
        elif is_sem_resp:
            categoria = 'sem_responsavel'
            categoria_label = '🚨 Sem Responsável'
            categoria_classe = 'urgencia-alerta'
            total_sem_responsavel += 1
        else:
            categoria = 'outras_atrasadas'
            categoria_label = '⚠️ Atrasada (SLA)'
            categoria_classe = 'urgencia-media'
            total_outras_atrasadas += 1

        if is_sem_resp and categoria != 'sem_responsavel':
            total_sem_responsavel += 1

        dc = parse_data(d['data_criacao'])
        dl = parse_data(d['data_limite'])
        if dl:
            if agora > dl:
                dias_atraso = (agora - dl).total_seconds() / 86400.0
                d['tempo_status_str'] = f"+{round(dias_atraso, 1)} dias de atraso"
                d['dias_diff'] = round(dias_atraso, 1)
                d['em_atraso'] = True
            else:
                dias_restantes = (dl - agora).total_seconds() / 86400.0
                d['tempo_status_str'] = f"Resta {round(dias_restantes, 1)} dias"
                d['dias_diff'] = round(dias_restantes, 1)
                d['em_atraso'] = False
        else:
            d['tempo_status_str'] = '-'
            d['dias_diff'] = 0
            d['em_atraso'] = False

        d['categoria'] = categoria
        d['categoria_label'] = categoria_label
        d['categoria_classe'] = categoria_classe
        d['peso'] = PESO_PRIORIDADE.get(pr, 2)

        # Filtro de aba se selecionado
        if aba_filtro == 'criticas_atrasadas' and categoria != 'critica_atrasada':
            continue
        elif aba_filtro == 'criticas_prazo' and categoria != 'critica_prazo':
            continue
        elif aba_filtro == 'outras_atrasadas' and categoria != 'outras_atrasadas':
            continue
        elif aba_filtro == 'sem_responsavel' and not is_sem_resp:
            continue

        lista_processada.append(d)

    stats_urgentes = {
        'total': len(todas_urgentes),
        'total_exibido': len(lista_processada),
        'criticas_atrasadas': total_criticas_atrasadas,
        'criticas_no_prazo': total_criticas_no_prazo,
        'outras_atrasadas': total_outras_atrasadas,
        'sem_responsavel': total_sem_responsavel,
    }

    return render_template(
        'criticas_atrasadas.html',
        demandas=lista_processada,
        stats=stats_urgentes,
        aba_ativa=aba_filtro,
        usuarios=usuarios
    )


@app.route('/atribuir_responsavel_rapido/<int:id>', methods=['POST'])
def atribuir_responsavel_rapido(id):
    """Atribui responsável diretamente a partir do painel de triagem do War Room."""
    responsavel_id_str = request.form.get('responsavel_id', '').strip()
    origem = request.form.get('origem', '/criticas-atrasadas')

    conn = get_db()
    cursor = conn.cursor()
    demanda = cursor.execute('SELECT id, titulo FROM demandas WHERE id = ?', (id,)).fetchone()
    if not demanda:
        conn.close()
        flash('Demanda não encontrada.', 'danger')
        return redirect(origem)

    responsavel_id = int(responsavel_id_str) if responsavel_id_str.isdigit() else None
    cursor.execute('UPDATE demandas SET responsavel_id = ? WHERE id = ?', (responsavel_id, id))

    # Registra comentário automático no histórico
    agora_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if responsavel_id:
        usr = cursor.execute('SELECT nome FROM usuarios WHERE id = ?', (responsavel_id,)).fetchone()
        nome_resp = usr['nome'] if usr else 'Usuário'
        msg_log = f'⚡ [Triagem Rápida] Responsável atribuído para: {nome_resp}.'
    else:
        msg_log = '⚠️ [Triagem Rápida] Responsável removido.'

    cursor.execute(
        'INSERT INTO comentarios (demanda_id, autor_id, texto, data_criacao) VALUES (?, ?, ?, ?)',
        (id, None, msg_log, agora_str)
    )
    conn.commit()
    conn.close()

    flash(f'Responsável da demanda #{id} atualizado com sucesso!', 'success')
    return redirect(origem)


# =====================================================================
# ROTAS DE EXPORTAÇÃO (CSV, EXCEL, PDF)
# =====================================================================

@app.route('/exportar/csv')
def exportar_csv():
    """Exporta relatório completo de demandas em formato CSV com cabeçalho institucional, dados e rodapé."""
    conn = get_db()
    garantir_migracao_db(conn)
    filtros = request.args.to_dict()
    metricas = obter_metricas_analytics(conn, filtros)
    demandas = metricas['demandas_lista']
    conn.close()

    sio = io.StringIO()
    writer = csv.writer(sio, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    # Cabeçalho institucional
    writer.writerow([f'{NOME_EMPRESA} - {NOME_ORGANIZACAO}'])
    writer.writerow(['RELATÓRIO ANALÍTICO DE DEMANDAS E SLA'])
    writer.writerow([])

    # Resumo de KPIs
    writer.writerow(['--- RESUMO DE MÉTRICAS GERAIS ---'])
    writer.writerow(['Total de Demandas', metricas['total_demandas']])
    writer.writerow(['Abertas', metricas['total_abertas']])
    writer.writerow(['Em Andamento', metricas['total_em_andamento']])
    writer.writerow(['Concluídas', metricas['total_concluidas']])
    writer.writerow(['Canceladas', metricas['total_canceladas']])
    writer.writerow(['Fora do SLA / Atrasadas', metricas['total_fora_sla']])
    writer.writerow(['Tempo Médio de Resolução', metricas['tempo_medio_formatado']])
    writer.writerow(['Índice de Severidade Ponderado', f"{metricas['score_severidade']} ({metricas['severidade_classificacao']})"])
    writer.writerow([])

    # Cabeçalho da tabela de dados
    writer.writerow([
        'ID',
        'Título',
        'Solicitante',
        'Responsável',
        'Status',
        'Prioridade',
        'Situação SLA',
        'Data Criação',
        'Data Limite SLA',
        'Data Conclusão'
    ])

    for d in demandas:
        st_sla = d.get('status_sla', '')
        if st_sla == 'sem_responsavel_fora_sla':
            sit_sla = 'Fora do SLA (Sem Responsável)'
        elif st_sla == 'atrasada':
            sit_sla = 'Atrasada (Fora do SLA)'
        elif st_sla == 'concluida_atrasada':
            sit_sla = 'Concluída com Atraso'
        elif st_sla == 'concluida_no_prazo':
            sit_sla = 'Concluída no Prazo'
        elif st_sla == 'cancelada':
            sit_sla = 'Cancelada'
        else:
            sit_sla = 'No Prazo'

        writer.writerow([
            d.get('id', ''),
            d.get('titulo', ''),
            d.get('solicitante_nome', '') or 'Não informado',
            d.get('responsavel_nome', '') or 'Sem responsável',
            d.get('status', ''),
            d.get('prioridade', ''),
            sit_sla,
            d.get('data_criacao', '') or '',
            d.get('data_limite', '') or '',
            d.get('data_conclusao', '') or '-'
        ])

    # Rodapé com filtros aplicados e timestamp
    writer.writerow([])
    writer.writerow(['------------------------------------------------------------'])
    writer.writerow([f"Filtros aplicados: {metricas['texto_filtros']}"])
    writer.writerow([f"Relatório gerado em: {metricas['timestamp_geracao']}"])

    csv_data = sio.getvalue().encode('utf-8-sig')
    return Response(
        csv_data,
        mimetype='text/csv; charset=utf-8-sig',
        headers={'Content-Disposition': 'attachment; filename=relatorio_demandas_sgdi.csv'}
    )


@app.route('/exportar/excel')
def exportar_excel():
    """Exporta relatório completo em formato Excel (.xlsx) com abas formatadas, cabeçalho e rodapé."""
    conn = get_db()
    garantir_migracao_db(conn)
    filtros = request.args.to_dict()
    metricas = obter_metricas_analytics(conn, filtros)
    demandas = metricas['demandas_lista']
    conn.close()

    wb = openpyxl.Workbook()

    # Estilos de formatação
    fonte_titulo = Font(name='Calibri', size=15, bold=True, color='1E293B')
    fonte_subtitulo = Font(name='Calibri', size=11, italic=True, color='64748B')
    fonte_secao = Font(name='Calibri', size=12, bold=True, color='4F46E5')
    fonte_header = Font(name='Calibri', size=10, bold=True, color='FFFFFF')
    fonte_dados = Font(name='Calibri', size=10)
    fonte_rodape = Font(name='Calibri', size=9, italic=True, color='64748B')

    fill_header = PatternFill(start_color='1E293B', end_color='1E293B', fill_type='solid')
    fill_header_u = PatternFill(start_color='4F46E5', end_color='4F46E5', fill_type='solid')
    borda_fina = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    # 1. ABA RESUMO ANALÍTICO
    ws_resumo = wb.active
    ws_resumo.title = 'Resumo Analítico'

    ws_resumo['A1'] = f'{NOME_EMPRESA} - {NOME_ORGANIZACAO}'
    ws_resumo['A1'].font = fonte_titulo
    ws_resumo['A2'] = 'Painel Executivo de Analytics e SLA'
    ws_resumo['A2'].font = fonte_subtitulo

    ws_resumo['A4'] = 'MÉTRICAS GERAIS CONSOLIDADAS'
    ws_resumo['A4'].font = fonte_secao

    kpi_rows = [
        ('Total de Demandas', metricas['total_demandas']),
        ('Demandas Abertas', metricas['total_abertas']),
        ('Em Andamento', metricas['total_em_andamento']),
        ('Concluídas', metricas['total_concluidas']),
        ('Canceladas', metricas['total_canceladas']),
        ('Fora do SLA / Atrasadas', metricas['total_fora_sla']),
        ('Taxa de Cumprimento de SLA', f"{metricas['taxa_sla_geral']}%"),
        ('Tempo Médio de Resolução (Concluídas)', metricas['tempo_medio_formatado']),
        ('Índice de Severidade Ponderado', f"{metricas['score_severidade']} / 4.0 ({metricas['severidade_classificacao']})"),
    ]

    for idx, (kpi, val) in enumerate(kpi_rows, start=5):
        ws_resumo[f'A{idx}'] = kpi
        ws_resumo[f'B{idx}'] = val
        ws_resumo[f'A{idx}'].font = Font(name='Calibri', bold=True)
        ws_resumo[f'B{idx}'].font = fonte_dados
        ws_resumo[f'A{idx}'].border = borda_fina
        ws_resumo[f'B{idx}'].border = borda_fina

    # Tabela de Responsáveis no Resumo
    linha_u = 16
    ws_resumo[f'A{linha_u}'] = 'DESEMPENHO POR RESPONSÁVEL'
    ws_resumo[f'A{linha_u}'].font = fonte_secao
    linha_u += 1

    headers_resp = ['Responsável', 'Total Atribuído', 'Abertas', 'Em Andamento', 'Concluídas', 'Fora SLA', 'Taxa Conclusão', 'Tempo Médio', 'Carga Ponderada']
    for col_idx, h in enumerate(headers_resp, start=1):
        cell = ws_resumo.cell(row=linha_u, column=col_idx, value=h)
        cell.font = fonte_header
        cell.fill = fill_header_u
        cell.alignment = Alignment(horizontal='center')

    for u in metricas['usuarios_stats']:
        linha_u += 1
        vals = [
            u['nome'], u['total'], u['abertas'], u['em_andamento'], u['concluidas'],
            u['fora_sla'], f"{u['taxa_conclusao']}%", u['tempo_medio_formatado'], f"{u['pontos_criticidade']} pts"
        ]
        for col_idx, val in enumerate(vals, start=1):
            cell = ws_resumo.cell(row=linha_u, column=col_idx, value=val)
            cell.font = fonte_dados
            cell.border = borda_fina
            if col_idx > 1:
                cell.alignment = Alignment(horizontal='center')

    # Rodapé no resumo
    linha_u += 3
    ws_resumo[f'A{linha_u}'] = f"Filtros aplicados: {metricas['texto_filtros']}"
    ws_resumo[f'A{linha_u}'].font = fonte_rodape
    linha_u += 1
    ws_resumo[f'A{linha_u}'] = f"Relatório gerado em: {metricas['timestamp_geracao']}"
    ws_resumo[f'A{linha_u}'].font = fonte_rodape

    # 2. ABA DEMANDAS DETALHADAS
    ws_demandas = wb.create_sheet(title='Lista de Demandas')

    ws_demandas['A1'] = f'{NOME_EMPRESA} - {NOME_ORGANIZACAO}'
    ws_demandas['A1'].font = fonte_titulo
    ws_demandas['A2'] = 'Relatório Detalhado de Demandas e SLA'
    ws_demandas['A2'].font = fonte_subtitulo

    headers_dem = ['ID', 'Título', 'Solicitante', 'Responsável', 'Status', 'Prioridade', 'Situação SLA', 'Criação', 'Prazo Limite SLA', 'Conclusão']
    linha_d = 4
    for col_idx, h in enumerate(headers_dem, start=1):
        cell = ws_demandas.cell(row=linha_d, column=col_idx, value=h)
        cell.font = fonte_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal='center')

    for d in demandas:
        linha_d += 1
        st_sla = d.get('status_sla', '')
        if st_sla == 'sem_responsavel_fora_sla': sit_sla = 'Fora SLA (Sem Resp.)'
        elif st_sla == 'atrasada': sit_sla = 'Atrasada'
        elif st_sla == 'concluida_atrasada': sit_sla = 'Concluída (Atraso)'
        elif st_sla == 'concluida_no_prazo': sit_sla = 'Concluída no Prazo'
        elif st_sla == 'cancelada': sit_sla = 'Cancelada'
        else: sit_sla = 'No Prazo'

        row_vals = [
            d.get('id', ''),
            d.get('titulo', ''),
            d.get('solicitante_nome', '') or 'Não informado',
            d.get('responsavel_nome', '') or 'Sem responsável',
            d.get('status', ''),
            d.get('prioridade', ''),
            sit_sla,
            d.get('data_criacao', '') or '',
            d.get('data_limite', '') or '',
            d.get('data_conclusao', '') or '-'
        ]
        for col_idx, val in enumerate(row_vals, start=1):
            cell = ws_demandas.cell(row=linha_d, column=col_idx, value=val)
            cell.font = fonte_dados
            cell.border = borda_fina
            if col_idx in (1, 5, 6, 7, 8, 9, 10):
                cell.alignment = Alignment(horizontal='center')

    # Rodapé nas demandas
    linha_d += 2
    ws_demandas[f'A{linha_d}'] = f"Filtros aplicados: {metricas['texto_filtros']}"
    ws_demandas[f'A{linha_d}'].font = fonte_rodape
    linha_d += 1
    ws_demandas[f'A{linha_d}'] = f"Relatório gerado em: {metricas['timestamp_geracao']}"
    ws_demandas[f'A{linha_d}'].font = fonte_rodape

    # Auto-ajuste de colunas
    for ws in (ws_resumo, ws_demandas):
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(12, min(max_len + 3, 40))

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)

    return send_file(
        bio,
        as_attachment=True,
        download_name='relatorio_demandas_sgdi.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.route('/exportar/pdf')
def exportar_pdf():
    """Exporta relatório consolidado em PDF com cabeçalho institucional, tabelas, filtros e timestamp no rodapé."""
    conn = get_db()
    garantir_migracao_db(conn)
    filtros = request.args.to_dict()
    metricas = obter_metricas_analytics(conn, filtros)
    demandas = metricas['demandas_lista']
    conn.close()

    md = f"""# {NOME_EMPRESA}
## {NOME_ORGANIZACAO}
### Relatório Executivo de Analytics e Governança de SLA

---

#### 📌 Resumo Geral de Métricas
- **Total de Demandas:** {metricas['total_demandas']}
- **Abertas:** {metricas['total_abertas']} ({metricas['pct_abertas']}%) | **Em Andamento:** {metricas['total_em_andamento']} ({metricas['pct_em_andamento']}%)
- **Concluídas:** {metricas['total_concluidas']} ({metricas['pct_concluidas']}%) | **Canceladas:** {metricas['total_canceladas']} ({metricas['pct_canceladas']}%)
- **Fora do SLA / Atrasadas:** {metricas['total_fora_sla']} (SLA Global: {metricas['taxa_sla_geral']}%)
- **Tempo Médio de Resolução:** {metricas['tempo_medio_formatado']} *(Apenas Concluídas; Canceladas desconsideradas)*
- **Índice de Severidade do Backlog:** {metricas['score_severidade']} / 4.0 ({metricas['severidade_classificacao']})

---

#### 👥 Desempenho por Responsável
| Responsável | Total | Abertas | Em Andamento | Concluídas | Fora SLA | Taxa Conclusão | Tempo Médio |
|---|---|---|---|---|---|---|---|
"""
    for u in metricas['usuarios_stats']:
        md += f"| {u['nome']} | {u['total']} | {u['abertas']} | {u['em_andamento']} | {u['concluidas']} | {u['fora_sla']} | {u['taxa_conclusao']}% | {u['tempo_medio_formatado']} |\n"

    md += """
---

#### 📋 Lista de Demandas
| ID | Título | Solicitante | Responsável | Status | Prioridade | Situação SLA | Criação |
|---|---|---|---|---|---|---|---|
"""
    for d in demandas[:60]:  # Limite de apresentação para PDF limpo
        st_sla = d.get('status_sla', '')
        if st_sla == 'sem_responsavel_fora_sla': sit_sla = 'Fora SLA (Sem Resp)'
        elif st_sla == 'atrasada': sit_sla = 'Atrasada'
        elif st_sla == 'concluida_atrasada': sit_sla = 'Concluída (Atraso)'
        elif st_sla == 'concluida_no_prazo': sit_sla = 'Concluída no Prazo'
        elif st_sla == 'cancelada': sit_sla = 'Cancelada'
        else: sit_sla = 'No Prazo'

        tit = (d.get('titulo', '')[:28] + '...') if len(d.get('titulo', '')) > 28 else d.get('titulo', '')
        solic = d.get('solicitante_nome', '') or '-'
        resp = d.get('responsavel_nome', '') or 'Sem resp.'
        dt_c = (d.get('data_criacao', '')[:10]) if d.get('data_criacao') else '-'
        md += f"| #{d.get('id')} | {tit} | {solic} | {resp} | {d.get('status')} | {d.get('prioridade')} | {sit_sla} | {dt_c} |\n"

    md += f"""
---

**Filtros aplicados:** {metricas['texto_filtros']}  
**Relatório gerado em:** {metricas['timestamp_geracao']}  
*{NOME_EMPRESA} - Confidencial*
"""

    pdf = MarkdownPdf()
    pdf.add_section(Section(md))
    bio = io.BytesIO()
    pdf.save_bytes(bio)
    bio.seek(0)

    return send_file(
        bio,
        as_attachment=True,
        download_name='relatorio_demandas_sgdi.pdf',
        mimetype='application/pdf'
    )


# =====================================================================
# OPERAÇÕES CRUD DE DEMANDAS
# =====================================================================

@app.route('/nova_demanda', methods=['GET', 'POST'])
def nova_demanda():
    conn = get_db()
    garantir_migracao_db(conn)

    if request.method == 'POST':
        titulo = request.form['titulo'].strip()
        descricao = request.form['descricao'].strip()
        solicitante_id = ler_usuario_id(conn, request.form.get('solicitante_id'))
        
        if not titulo:
            flash('Informe um título para a demanda.')
            conn.close()
            return redirect(url_for('nova_demanda'))

        if solicitante_id is None:
            conn.close()
            flash('Selecione um solicitante cadastrado.')
            return redirect(url_for('nova_demanda'))

        prioridade = request.form.get('prioridade')
        if prioridade not in PRIORIDADE_OPCOES:
            prioridade = PRIORIDADE_PADRAO
        responsavel_id = ler_usuario_id(conn, request.form.get('responsavel_id'))

        data_criacao_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        conn.execute(
            '''
            INSERT INTO demandas
            (titulo, descricao, solicitante_id, data_criacao, status, prioridade, responsavel_id, data_conclusao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (titulo, descricao, solicitante_id, data_criacao_str, 'Aberta', prioridade, responsavel_id, None)
        )

        conn.commit()
        conn.close()

        flash('Demanda cadastrada com sucesso!')
        return redirect(url_for('demandas'))

    usuarios = conn.execute('SELECT * FROM usuarios ORDER BY nome').fetchall()
    conn.close()

    return render_template(
        'nova_demanda.html',
        usuarios=usuarios,
        prioridade_opcoes=PRIORIDADE_OPCOES,
        prioridade_padrao=PRIORIDADE_PADRAO
    )


@app.route('/editar/<id>', methods=['GET', 'POST'])
def editar(id):
    conn = get_db()
    garantir_migracao_db(conn)
    cursor = conn.cursor()

    if request.method == 'POST':
        titulo = request.form['titulo'].strip()
        descricao = request.form['descricao'].strip()
        solicitante_id = ler_usuario_id(conn, request.form.get('solicitante_id'))
        if solicitante_id is None:
            conn.close()
            flash('Selecione um solicitante cadastrado.')
            return redirect(url_for('editar', id=id))

        status = request.form.get('status')
        if status not in STATUS_OPCOES:
            status = STATUS_OPCOES[0]

        prioridade = request.form.get('prioridade')
        if prioridade not in PRIORIDADE_OPCOES:
            prioridade = PRIORIDADE_PADRAO
        responsavel_id = ler_usuario_id(conn, request.form.get('responsavel_id'))

        # Lógica de data_conclusao
        demanda_atual = cursor.execute('SELECT status, data_conclusao FROM demandas WHERE id=?', (id,)).fetchone()
        data_conclusao = demanda_atual['data_conclusao'] if demanda_atual else None

        if status == 'Concluída':
            if not data_conclusao:
                data_conclusao = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        else:
            data_conclusao = None

        cursor.execute(
            '''
            UPDATE demandas
            SET titulo=?, descricao=?, solicitante_id=?, status=?, prioridade=?, responsavel_id=?, data_conclusao=?
            WHERE id=?
            ''',
            (titulo, descricao, solicitante_id, status, prioridade, responsavel_id, data_conclusao, id)
        )
        conn.commit()
        conn.close()
        flash('Demanda atualizada com sucesso!')
        return redirect(url_for('demandas'))

    demanda = cursor.execute(f'{SELECT_DEMANDAS} WHERE d.id=?', (id,)).fetchone()
    usuarios = listar_usuarios(conn)
    conn.close()

    if not demanda:
        flash('Demanda não encontrada.')
        return redirect(url_for('demandas'))

    return render_template(
        'editar.html',
        demanda=demanda,
        status_opcoes=STATUS_OPCOES,
        prioridade_opcoes=PRIORIDADE_OPCOES,
        usuarios=usuarios
    )


@app.route('/deletar/<id>')
def deletar(id):
    conn = get_db()
    garantir_migracao_db(conn)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM comentarios WHERE demanda_id = ?', (id,))
    cursor.execute('DELETE FROM demandas WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Demanda removida com sucesso!')
    return redirect(url_for('demandas'))


@app.route('/buscar')
def buscar():
    return redirect(url_for('demandas', q=request.args.get('q', '')))


@app.route('/detalhes/<id>')
def detalhes(id):
    conn = get_db()
    garantir_migracao_db(conn)
    cursor = conn.cursor()
    demanda = cursor.execute(f'{SELECT_DEMANDAS} WHERE d.id = ?', (id,)).fetchone()
    comentarios = cursor.execute('SELECT * FROM comentarios WHERE demanda_id = ? ORDER BY id ASC', (id,)).fetchall()
    
    tempo_resolucao = None
    if demanda and demanda['status'] == 'Concluída' and demanda['data_conclusao']:
        dc = parse_data(demanda['data_criacao'])
        df = parse_data(demanda['data_conclusao'])
        if dc and df:
            dias = max(0.01, (df - dc).total_seconds() / 86400.0)
            tempo_resolucao = formatar_tempo_resolucao(dias)

    conn.close()

    if not demanda:
        flash('Demanda não encontrada.')
        return redirect(url_for('demandas'))

    return render_template('detalhes.html', demanda=demanda, comentarios=comentarios, tempo_resolucao=tempo_resolucao)


@app.route('/adicionar_comentario/<demanda_id>', methods=['POST'])
def adicionar_comentario(demanda_id):
    comentario = request.form.get('comentario', '').strip()
    autor = request.form.get('autor', '').strip() or 'Anônimo'

    if comentario:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO comentarios (demanda_id, comentario, autor, data) VALUES (?, ?, ?, ?)',
            (demanda_id, comentario, autor, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit()
        conn.close()
        flash('Comentário adicionado com sucesso!')

    return redirect(url_for('detalhes', id=demanda_id))


if __name__ == '__main__':
    conn = get_db()
    garantir_migracao_db(conn)
    conn.close()
    app.run(debug=True, host='0.0.0.0')