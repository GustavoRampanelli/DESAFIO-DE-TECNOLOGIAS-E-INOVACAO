"""
Aplicação Principal do SGDI - Sistema de Gestão de Demandas Internas.
SSR - Gestão & Governança | Desafio de Tecnologias e Inovação.

Controlador HTTP principal (Flask). Orquestra as rotas de Analytics, War Room,
Gestão de Demandas, Histórico de Comentários e Exportação Corporativa,
delegando regras de negócio e infraestrutura para módulos especializados.
"""

import math
from datetime import datetime
import werkzeug

# Compatibilidade para versões recentes do Werkzeug no Python 3.13
if not hasattr(werkzeug, '__version__'):
    try:
        import importlib.metadata
        werkzeug.__version__ = importlib.metadata.version('werkzeug')
    except Exception:
        werkzeug.__version__ = '3.1.3'

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

# Configurações e Banco de Dados
from config import (
    SECRET_KEY,
    POR_PAGINA,
    STATUS_OPCOES,
    PRIORIDADE_OPCOES,
    PRIORIDADE_PADRAO,
    PESO_PRIORIDADE
)
from database import (
    get_db,
    garantir_migracao_db,
    listar_usuarios,
    ler_usuario_id,
    SELECT_DEMANDAS
)

# Camada de Serviços Especializados
from services.sla_service import parse_data, formatar_tempo_resolucao, calcular_prazo
from services.analytics_service import construir_filtro_sql, obter_metricas_analytics
from services.export_service import gerar_csv_response, gerar_excel_response, gerar_pdf_response

app = Flask(__name__)
app.secret_key = SECRET_KEY


# =====================================================================
# CONTEXT PROCESSORS GLOBAIS
# =====================================================================

@app.context_processor
def inject_global_stats():
    """Injeta contagem rápida de demandas críticas/atrasadas para o ribbon do Obsidian."""
    try:
        conn = get_db()
        count_urgentes = conn.execute(
            """SELECT COUNT(*) FROM demandas WHERE status NOT IN ('Concluída', 'Cancelada')
               AND (prioridade = 'Crítica' OR responsavel_id IS NULL OR datetime(data_criacao, '+' || (CASE prioridade WHEN 'Crítica' THEN 2 WHEN 'Alta' THEN 5 WHEN 'Média' THEN 10 WHEN 'Baixa' THEN 20 ELSE 30 END) || ' days') < datetime('now', 'localtime'))"""
        ).fetchone()[0]
        conn.close()
        return {'total_urgentes_global': count_urgentes}
    except Exception:
        return {'total_urgentes_global': 0}


# =====================================================================
# ROTAS DE ANALYTICS & DASHBOARD
# =====================================================================

@app.route('/')
@app.route('/dashboard')
@app.route('/analytics')
def index():
    """Painel Principal: Dashboard Analítico completo com filtros dinâmicos."""
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
    """Endpoint JSON assíncrono para atualização dinâmica dos gráficos e KPIs via Fetch API."""
    conn = get_db()
    garantir_migracao_db(conn)
    filtros = request.args.to_dict()
    metricas = obter_metricas_analytics(conn, filtros)
    conn.close()
    return jsonify(metricas)


# =====================================================================
# VISÃO DEDICADA: WAR ROOM DE CRÍTICAS & ATRASADAS
# =====================================================================

@app.route('/criticas-atrasadas')
@app.route('/urgentes')
def criticas_atrasadas():
    """War Room de Triagem: Demandas Críticas e/ou Fora do SLA (Obsidian Workspace)."""
    aba_filtro = request.args.get('aba', 'todas')
    conn = get_db()
    garantir_migracao_db(conn)

    query_urgentes = f"""
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
    """

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

        # Classificação de risco e severidade
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

        # Filtro da aba selecionada
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
    """Atribui responsável diretamente no painel de triagem do War Room com log imediato."""
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
# ROTAS DE EXPORTAÇÃO CORPORATIVA (CSV, EXCEL, PDF)
# =====================================================================

@app.route('/exportar/csv')
def exportar_csv():
    """Exporta relatório completo de demandas em formato CSV com cabeçalho, dados e rodapé."""
    conn = get_db()
    garantir_migracao_db(conn)
    filtros = request.args.to_dict()
    metricas = obter_metricas_analytics(conn, filtros)
    conn.close()
    return gerar_csv_response(metricas)


@app.route('/exportar/excel')
def exportar_excel():
    """Exporta relatório completo em formato Excel (.xlsx) com abas analíticas formatadas."""
    conn = get_db()
    garantir_migracao_db(conn)
    filtros = request.args.to_dict()
    metricas = obter_metricas_analytics(conn, filtros)
    conn.close()
    return gerar_excel_response(metricas)


@app.route('/exportar/pdf')
def exportar_pdf():
    """Exporta relatório executivo em PDF com cabeçalho institucional, sumário de KPIs e SLA."""
    conn = get_db()
    garantir_migracao_db(conn)
    filtros = request.args.to_dict()
    metricas = obter_metricas_analytics(conn, filtros)
    conn.close()
    return gerar_pdf_response(metricas)


# =====================================================================
# ROTAS OPERACIONAIS E CRUD DE DEMANDAS
# =====================================================================

@app.route('/demandas')
def demandas():
    """Listagem geral de demandas com filtros combinados, busca e paginação."""
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
        """SELECT COUNT(*) FROM demandas WHERE status NOT IN ('Concluída', 'Cancelada')
           AND (responsavel_id IS NULL OR datetime(data_criacao, '+' || (CASE prioridade WHEN 'Crítica' THEN 2 WHEN 'Alta' THEN 5 WHEN 'Média' THEN 10 WHEN 'Baixa' THEN 20 ELSE 30 END) || ' days') < datetime('now', 'localtime'))"""
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


@app.route('/nova_demanda', methods=['GET', 'POST'])
def nova_demanda():
    """Abertura de nova demanda com cálculo de SLA por prioridade."""
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
    """Edição de demanda e marcação de conclusão com registro de data_conclusao."""
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
    """Exclusão de demanda e comentários associados."""
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
    """Redirecionamento para a listagem com termo de busca."""
    return redirect(url_for('demandas', q=request.args.get('q', '')))


@app.route('/detalhes/<id>')
def detalhes(id):
    """Visão detalhada da demanda com timeline e cálculo de tempo de resolução."""
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
    """Inclusão de apontamento no histórico da demanda."""
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


# =====================================================================
# INICIALIZAÇÃO
# =====================================================================

if __name__ == '__main__':
    conn = get_db()
    garantir_migracao_db(conn)
    conn.close()
    app.run(debug=True, host='0.0.0.0')