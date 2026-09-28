from flask import Flask, render_template, request, redirect, url_for, flash
import math
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = '123456'


def get_db():
    conn = sqlite3.connect('demandas.db')
    conn.row_factory = sqlite3.Row
    return conn


POR_PAGINA = 10
STATUS_OPCOES = ['Aberta', 'Em andamento', 'Concluída']
PRIORIDADE_OPCOES = ['Baixa', 'Média', 'Alta', 'Crítica']
PRIORIDADE_PADRAO = 'Média'

# Filtros de lista fixa: coluna da tabela -> opções válidas
FILTROS_OPCOES = {
    'status': STATUS_OPCOES,
    'prioridade': PRIORIDADE_OPCOES,
}


def listar_usuarios(conn):
    return conn.execute('SELECT id, nome FROM usuarios ORDER BY nome').fetchall()


def ler_usuario_id(conn, valor):
    """Retorna o id do usuário se ele existir; caso contrário None."""
    if not valor or not str(valor).isdigit():
        return None
    usuario = conn.execute('SELECT id FROM usuarios WHERE id = ?', (int(valor),)).fetchone()
    return usuario[0] if usuario else None


# Demandas com o nome do solicitante e do responsável (LEFT JOIN mantém as demandas sem responsável)
SELECT_DEMANDAS = '''
    SELECT d.*, s.nome AS solicitante_nome, r.nome AS responsavel_nome
    FROM demandas d
    LEFT JOIN usuarios s ON s.id = d.solicitante_id
    LEFT JOIN usuarios r ON r.id = d.responsavel_id
'''


@app.route('/')
def index():
    pagina = request.args.get('pagina', 1, type=int)
    termo = request.args.get('q', '').strip()

    # Cada filtro ativo adiciona uma condição ao WHERE (com parâmetros, sem concatenar valores)
    condicoes = []
    parametros = []
    filtros = {}
    if termo:
        condicoes.append('titulo LIKE ?')
        parametros.append(f'%{termo}%')
        filtros['q'] = termo

    # Valores fora da lista de opções são ignorados (equivale a "Todas")
    for coluna, opcoes in FILTROS_OPCOES.items():
        valor = request.args.get(coluna, '')
        if valor in opcoes:
            condicoes.append(f'{coluna} = ?')
            parametros.append(valor)
            filtros[coluna] = valor

    responsavel = request.args.get('responsavel', type=int)
    if responsavel:
        condicoes.append('responsavel_id = ?')
        parametros.append(responsavel)
        filtros['responsavel'] = responsavel

    where = 'WHERE ' + ' AND '.join(condicoes) if condicoes else ''

    conn = get_db()
    total = conn.execute(f'SELECT COUNT(*) FROM demandas {where}', parametros).fetchone()[0]
    total_paginas = max(1, math.ceil(total / POR_PAGINA))
    pagina = min(max(pagina, 1), total_paginas)

    demandas = conn.execute(
        f'{SELECT_DEMANDAS} {where} ORDER BY d.id LIMIT ? OFFSET ?',
        parametros + [POR_PAGINA, (pagina - 1) * POR_PAGINA]
    ).fetchall()
    usuarios = listar_usuarios(conn)
    conn.close()

    # "filtros" vai nos links de paginação para os filtros não se perderem ao trocar de página
    return render_template(
        'index.html',
        demandas=demandas,
        pagina=pagina,
        total_paginas=total_paginas,
        total=total,
        filtros=filtros,
        status_opcoes=STATUS_OPCOES,
        prioridade_opcoes=PRIORIDADE_OPCOES,
        usuarios=usuarios
    )


@app.route('/nova_demanda', methods=['GET', 'POST'])
def nova_demanda():
    conn = sqlite3.connect('demandas.db')
    conn.row_factory = sqlite3.Row

    if request.method == 'POST':
        titulo = request.form['titulo']
        descricao = request.form['descricao']
        solicitante_id = ler_usuario_id(conn, request.form.get('solicitante_id'))
        if solicitante_id is None:
            conn.close()
            flash('Selecione um solicitante cadastrado.')
            return redirect(url_for('nova_demanda'))
        prioridade = request.form.get('prioridade')
        if prioridade not in PRIORIDADE_OPCOES:
            prioridade = PRIORIDADE_PADRAO
        responsavel_id = ler_usuario_id(conn, request.form.get('responsavel_id'))

        conn.execute(
            '''
            INSERT INTO demandas
            (titulo, descricao, solicitante_id, data_criacao, prioridade, responsavel_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (titulo, descricao, solicitante_id, datetime.now(), prioridade, responsavel_id)
        )

        conn.commit()
        conn.close()

        flash('Salvo!')
        return redirect('/')

    # Busca os usuários que JÁ estão no banco
    usuarios = conn.execute(
        'SELECT * FROM usuarios ORDER BY nome'
    ).fetchall()

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
    cursor = conn.cursor()

    if request.method == 'POST':
        titulo = request.form['titulo']
        descricao = request.form['descricao']
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

        cursor.execute(
            '''
            UPDATE demandas
            SET titulo=?, descricao=?, solicitante_id=?, status=?, prioridade=?, responsavel_id=?
            WHERE id=?
            ''',
            (titulo, descricao, solicitante_id, status, prioridade, responsavel_id, id)
        )
        conn.commit()
        conn.close()
        return redirect('/')

    demanda = cursor.execute('SELECT * FROM demandas WHERE id=?', (id,)).fetchone()
    usuarios = listar_usuarios(conn)
    conn.close()
    return render_template(
        'editar.html',
        demanda=demanda,
        status_opcoes=STATUS_OPCOES,
        prioridade_opcoes=PRIORIDADE_OPCOES,
        usuarios=usuarios
    )


@app.route('/deletar/<id>')
def deletar(id):
    conn = sqlite3.connect('demandas.db')
    cursor = conn.cursor()
    cursor.execute(f'DELETE FROM demandas WHERE id={id}')
    conn.commit()
    conn.close()
    flash('Deletado!')
    return redirect('/')


@app.route('/buscar')
def buscar():
    # A busca agora é um filtro da listagem principal (com paginação)
    return redirect(url_for('index', q=request.args.get('q', '')))


# @app.route('/admin')
# def admin():
#     return 'Área administrativa'

@app.route('/detalhes/<id>')
def detalhes(id):
    conn = get_db()
    cursor = conn.cursor()
    demanda = cursor.execute(f'{SELECT_DEMANDAS} WHERE d.id = ?', (id,)).fetchone()

    comentarios = cursor.execute('SELECT * FROM comentarios WHERE demanda_id = ?', (id,)).fetchall()
    conn.close()

    return render_template('detalhes.html', demanda=demanda, comentarios=comentarios)


@app.route('/adicionar_comentario/<demanda_id>', methods=['POST'])
def adicionar_comentario(demanda_id):
    comentario = request.form['comentario']
    autor = request.form['autor']

    conn = sqlite3.connect('demandas.db')
    cursor = conn.cursor()
    cursor.execute(
        f"INSERT INTO comentarios (demanda_id, comentario, autor, data) VALUES ({demanda_id}, '{comentario}', '{autor}', '{datetime.now()}')")
    conn.commit()
    conn.close()

    return redirect(f'/detalhes/{demanda_id}')


def calcular_prazo(data_inicio):
    return "30 dias"


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')