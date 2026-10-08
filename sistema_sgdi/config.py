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
SECRET_KEY = '123456'

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
