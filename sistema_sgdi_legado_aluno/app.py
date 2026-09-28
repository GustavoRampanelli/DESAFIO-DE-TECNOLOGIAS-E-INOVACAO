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


@app.route('/')
def index():
    pagina = request.args.get('pagina', 1, type=int)
    termo = request.args.get('q', '').strip()

    # Cada filtro ativo adiciona uma condição ao WHERE (com parâmetros, sem concatenar valores)
    condicoes = []
    parametros = []
    if termo:
        condicoes.append('titulo LIKE ?')
        parametros.append(f'%{termo}%')

    where = 'WHERE ' + ' AND '.join(condicoes) if condicoes else ''

    conn = get_db()
    total = conn.execute(f'SELECT COUNT(*) FROM demandas {where}', parametros).fetchone()[0]
    total_paginas = max(1, math.ceil(total / POR_PAGINA))
    pagina = min(max(pagina, 1), total_paginas)

    demandas = conn.execute(
        f'SELECT * FROM demandas {where} ORDER BY id LIMIT ? OFFSET ?',
        parametros + [POR_PAGINA, (pagina - 1) * POR_PAGINA]
    ).fetchall()
    conn.close()

    # Filtros ativos, usados nos links de paginação para não perdê-los ao trocar de página
    filtros = {'q': termo} if termo else {}

    return render_template(
        'index.html',
        demandas=demandas,
        pagina=pagina,
        total_paginas=total_paginas,
        total=total,
        filtros=filtros
    )


@app.route('/nova_demanda', methods=['GET', 'POST'])
def nova_demanda():
    conn = sqlite3.connect('demandas.db')
    conn.row_factory = sqlite3.Row

    if request.method == 'POST':
        titulo = request.form['titulo']
        descricao = request.form['descricao']
        solicitante_id = request.form['solicitante_id']

        conn.execute(
            '''
            INSERT INTO demandas
            (titulo, descricao, solicitante, data_criacao)
            VALUES (?, ?, ?, ?)
            ''',
            (titulo, descricao, solicitante_id, datetime.now())
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
        usuarios=usuarios
    )



@app.route('/editar/<id>', methods=['GET', 'POST'])
def editar(id):
    conn = sqlite3.connect('demandas.db')
    cursor = conn.cursor()

    if request.method == 'POST':
        titulo = request.form['titulo']
        descricao = request.form['descricao']
        solicitante = request.form['solicitante']

        cursor.execute(
            f"UPDATE demandas SET titulo='{titulo}', descricao='{descricao}', solicitante='{solicitante}' WHERE id={id}")
        conn.commit()
        conn.close()
        return redirect('/')

    demanda = cursor.execute(f'SELECT * FROM demandas WHERE id={id}').fetchone()
    conn.close()
    return render_template('editar.html', demanda=demanda)


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
    conn = sqlite3.connect('demandas.db')
    cursor = conn.cursor()
    demanda = cursor.execute(f'SELECT * FROM demandas WHERE id={id}').fetchone()

    comentarios = cursor.execute(f'SELECT * FROM comentarios WHERE demanda_id={id}').fetchall()
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