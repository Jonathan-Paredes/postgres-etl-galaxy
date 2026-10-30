"""Reglas puras, deterministas, sin escritura ni dependencia del ETL."""
from dataclasses import dataclass
from datetime import datetime
from corte_operacional import ConfiguracionCorte


def normalizar_estado(estado: str) -> str:
    key = ' '.join(estado.strip().casefold().replace('_', ' ').split())
    return {
        'work in progress': 'WORK_IN_PROGRESS', 'wip': 'WORK_IN_PROGRESS',
        'en progreso': 'WORK_IN_PROGRESS', 'en proceso': 'WORK_IN_PROGRESS',
        'pendiente': 'PENDIENTE', 'cerrado': 'CERRADO',
        'abierto': 'ABIERTO', 'resuelto': 'RESUELTO', 'escalado': 'ESCALADO',
    }.get(key, 'NO_CONFIRMADO')


@dataclass(frozen=True)
class Incumplimiento:
    numero_ticket: str
    codigo_regla: str
    fecha_corte: datetime
    estado_observado: str
    lote_id: str


def evaluar_corte(tickets, fecha_corte: datetime, lote_id: str):
    corte = ConfiguracionCorte().validar(fecha_corte)
    return [Incumplimiento(str(t['Numero_ticket']), 'WIP_EN_CORTE_0530', corte,
                          str(t['Estado']), lote_id)
            for t in tickets if normalizar_estado(str(t['Estado'])) == 'WORK_IN_PROGRESS']
