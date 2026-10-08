"""
Serviço de SLA e Manipulação de Datas do SGDI.
Responsável pelo parsing resiliente de datas, formatação de tempo de resolução
e cálculo de prazos regimentais por prioridade.
"""

from datetime import datetime
from config import SLA_DIAS_POR_PRIORIDADE, SLA_PADRAO_DIAS


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
