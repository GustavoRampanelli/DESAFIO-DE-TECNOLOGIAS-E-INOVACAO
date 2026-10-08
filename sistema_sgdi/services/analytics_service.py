"""
Serviço de Inteligência Analítica e Métricas do SGDI.
Processa queries filtradas, agregações de telemetria, cálculos de SLA,
séries temporais para o Chart.js e score de severidade ponderada do backlog.
"""

from datetime import datetime, timedelta
from config import (
    STATUS_OPCOES,
    PRIORIDADE_OPCOES,
    PESO_PRIORIDADE,
    SLA_DIAS_POR_PRIORIDADE,
    SLA_PADRAO_DIAS
)
from database import SELECT_DEMANDAS, listar_usuarios
from services.sla_service import parse_data, formatar_tempo_resolucao


def construir_filtro_sql(filtros_req):
    """Monta cláusula WHERE e parâmetros SQL a partir dos filtros recebidos via query params."""
    filtros_req = filtros_req or {}
    condicoes = []
    parametros = []
    agora = datetime.now()

    # Filtro de Busca por termo (título)
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
