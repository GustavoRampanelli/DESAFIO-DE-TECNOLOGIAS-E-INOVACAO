"""
Serviço de Autenticação e Controle de Acesso do SGDI (Sprint 5).
Valida credenciais com senha em hash, aplica bloqueio temporário contra força bruta
(apoiado na própria trilha de auditoria) e restringe rotas por perfil de acesso.
"""

from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlparse
from flask import session, request, redirect, url_for, flash
from werkzeug.security import check_password_hash
from config import MAX_TENTATIVAS_LOGIN, BLOQUEIO_LOGIN_MINUTOS, PERFIS_LABEL
from database import get_db
from services.audit_service import registrar_log


def buscar_usuario_por_email(conn, email):
    return conn.execute(
        'SELECT id, nome, email, senha_hash, perfil FROM usuarios WHERE lower(email) = lower(?)',
        (email,)
    ).fetchone()


def login_bloqueado(conn, usuario_id):
    """True se o usuário acumulou falhas demais desde o último login bem-sucedido, dentro da janela de bloqueio."""
    inicio_janela = (datetime.now() - timedelta(minutes=BLOQUEIO_LOGIN_MINUTOS)).strftime('%Y-%m-%d %H:%M:%S')
    ultimo_login = conn.execute(
        "SELECT MAX(data_hora) FROM logs_auditoria WHERE acao = 'LOGIN' AND usuario_id = ?",
        (usuario_id,)
    ).fetchone()[0] or ''
    falhas = conn.execute(
        """SELECT COUNT(*) FROM logs_auditoria
           WHERE acao = 'LOGIN_FALHA' AND entidade = 'usuario' AND entidade_id = ?
           AND data_hora >= ? AND data_hora > ?""",
        (usuario_id, inicio_janela, ultimo_login)
    ).fetchone()[0]
    return falhas >= MAX_TENTATIVAS_LOGIN


def autenticar(conn, email, senha):
    """
    Valida as credenciais e registra o resultado na trilha de auditoria.
    Retorna (usuario, mensagem_erro). A mensagem de erro é genérica para não revelar
    se o e-mail existe no sistema.
    """
    usuario = buscar_usuario_por_email(conn, email)
    erro_generico = 'E-mail ou senha inválidos.'

    if usuario and login_bloqueado(conn, usuario['id']):
        registrar_log(
            conn, 'LOGIN_BLOQUEADO',
            f'Login bloqueado para {usuario["email"]} após {MAX_TENTATIVAS_LOGIN} tentativas inválidas',
            entidade='usuario', entidade_id=usuario['id'],
            usuario={'id': None, 'nome': usuario['email']}
        )
        conn.commit()
        return None, f'Acesso temporariamente bloqueado por excesso de tentativas. Aguarde {BLOQUEIO_LOGIN_MINUTOS} minutos.'

    if not usuario or not usuario['senha_hash'] or not check_password_hash(usuario['senha_hash'], senha):
        registrar_log(
            conn, 'LOGIN_FALHA',
            f'Tentativa de login inválida para {email or "(e-mail vazio)"}',
            entidade='usuario', entidade_id=usuario['id'] if usuario else None,
            usuario={'id': None, 'nome': email}
        )
        conn.commit()
        return None, erro_generico

    return usuario, None


def iniciar_sessao(usuario):
    """Grava a identidade do usuário na sessão assinada (expira conforme SESSAO_DURACAO_HORAS)."""
    session.clear()
    session.permanent = True
    session['usuario_id'] = usuario['id']
    session['usuario_nome'] = usuario['nome']
    session['perfil'] = usuario['perfil']


def usuario_atual():
    """Usuário logado (ou None) para uso nos templates."""
    if not session.get('usuario_id'):
        return None
    return {
        'id': session['usuario_id'],
        'nome': session.get('usuario_nome'),
        'perfil': session.get('perfil'),
        'perfil_label': PERFIS_LABEL.get(session.get('perfil'), session.get('perfil')),
    }


def destino_seguro(url, padrao='/'):
    """Aceita apenas caminhos internos (evita open redirect via ?proximo= ou campo origem)."""
    if not url:
        return padrao
    partes = urlparse(url)
    if partes.scheme or partes.netloc or not url.startswith('/') or url.startswith('//'):
        return padrao
    return url


def requer_perfil(*perfis):
    """Decorator: restringe a rota aos perfis informados e audita tentativas de acesso negado."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if session.get('perfil') not in perfis:
                conn = get_db()
                registrar_log(
                    conn, 'ACESSO_NEGADO',
                    f'Acesso negado a {request.method} {request.path} (perfil: {session.get("perfil") or "anônimo"})',
                    detalhes={'Rota': request.path, 'Método': request.method, 'Perfil': session.get('perfil')}
                )
                conn.commit()
                conn.close()
                flash('Acesso restrito ao perfil Administrador. A tentativa foi registrada na auditoria.')
                return redirect(url_for('index'))
            return view(*args, **kwargs)
        return wrapper
    return decorator
