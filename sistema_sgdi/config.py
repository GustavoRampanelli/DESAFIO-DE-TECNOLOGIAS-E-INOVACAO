"""
Configurações Globais e Regras de Negócio do SGDI.
Define constantes corporativas, parâmetros de SLA, pesos de criticidade e opções de filtro.
"""

import os

# Caminhos e Metadados Corporativos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'demandas.db')
NOME_EMPRESA = 'SGDI - Sistema de Gestão de Demandas Internas'
NOME_ORGANIZACAO = 'SSR - Gestão & Governança'
# Em produção defina a variável de ambiente SGDI_SECRET_KEY (assina o cookie de sessão do login)
SECRET_KEY = os.environ.get('SGDI_SECRET_KEY', '123456')

# Configurações de Paginação
POR_PAGINA = 10

# Ciclo de Vida e Prioridades
STATUS_OPCOES = ['Aberta', 'Em andamento', 'Concluída', 'Cancelada']
PRIORIDADE_OPCOES = ['Baixa', 'Média', 'Alta', 'Crítica']
PRIORIDADE_PADRAO = 'Média'

# Pesos de Criticidade: Críticos pesam mais que Médio
PESO_PRIORIDADE = {
    'Crítica': 4,
    'Alta': 3,
    'Média': 2,
    'Baixa': 1,
}

# SLA Inteligente por Prioridade (em dias corridos/úteis conforme regimento)
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

# =====================================================================
# Sprint 5 - Controle de Acesso, Auditoria e Rastreabilidade
# =====================================================================

# Perfis de acesso: administradores consultam a auditoria e excluem demandas
PERFIL_ADMIN = 'admin'
PERFIL_COLABORADOR = 'colaborador'
PERFIS_LABEL = {
    PERFIL_ADMIN: 'Administrador',
    PERFIL_COLABORADOR: 'Colaborador',
}

# Senha inicial atribuída aos usuários existentes na migração (troque após o primeiro acesso)
SENHA_PADRAO = 'sgdi@123'
ADMIN_PADRAO = ('Administrador SGDI', 'admin@email.com')

# Sessão e proteção contra força bruta no login
SESSAO_DURACAO_HORAS = 8
MAX_TENTATIVAS_LOGIN = 5
BLOQUEIO_LOGIN_MINUTOS = 15

# Log técnico em arquivo (erros e eventos operacionais), com rotação
LOG_DIR = os.path.join(BASE_DIR, 'logs')
LOG_ARQUIVO = os.path.join(LOG_DIR, 'sgdi.log')
LOG_TAMANHO_MAX_BYTES = 1_000_000
LOG_QTD_BACKUPS = 5

# Trilha de auditoria: ação registrada -> rótulo exibido nas telas e relatórios
POR_PAGINA_AUDITORIA = 20
ACOES_AUDITORIA = {
    'LOGIN': 'Login',
    'LOGOUT': 'Logout',
    'LOGIN_FALHA': 'Falha de login',
    'LOGIN_BLOQUEADO': 'Login bloqueado',
    'ACESSO_NEGADO': 'Acesso negado',
    'CRIAR': 'Criação',
    'EDITAR': 'Edição',
    'EXCLUIR': 'Exclusão',
    'COMENTAR': 'Comentário',
    'ATRIBUIR_RESPONSAVEL': 'Atribuição de responsável',
    'EXPORTAR': 'Exportação',
}
# Ações de segurança (FEAT 3): destacadas na tela de auditoria
ACOES_SEGURANCA = {'LOGIN_FALHA', 'LOGIN_BLOQUEADO', 'ACESSO_NEGADO'}
