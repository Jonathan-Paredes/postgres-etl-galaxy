"""Origen PostgreSQL operacional versionado, exclusivamente de lectura."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

SQL_INSTANTANEA = text('''
    SELECT DISTINCT ON (numero_ticket)
           numero_ticket, tipo_ticket, componente, estado, observaciones,
           fecha_creacion, fecha_modificacion
    FROM operacional.ticket_versiones
    WHERE fecha_creacion <= :corte AND fecha_modificacion <= :corte
    ORDER BY numero_ticket, fecha_modificacion DESC
''')


@dataclass(frozen=True)
class TicketOperacional:
    numero_ticket: str
    tipo_ticket: str
    componente: str
    estado: str
    observaciones: str | None
    fecha_creacion: datetime
    fecha_modificacion: datetime


@dataclass(frozen=True)
class Instantanea:
    fuente: str
    corte: datetime
    observada_en: datetime
    tickets: tuple[TicketOperacional, ...]
    hash_contenido: str


def utc_iso(fecha):
    if fecha.tzinfo is None or fecha.utcoffset() is None:
        raise ValueError('Fecha sin zona horaria')
    return fecha.astimezone(timezone.utc).isoformat()


def crear_instantanea(fuente, corte, observada_en, tickets):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',fuente):
        raise ValueError('Usar un identificador de fuente opaco, no una URL o credenciales')
    tickets=tuple(sorted(tickets,key=lambda t:t.numero_ticket))
    if len({t.numero_ticket for t in tickets}) != len(tickets):
        raise ValueError('Snapshot con tickets duplicados')
    contenido=[]
    for ticket in tickets:
        d=asdict(ticket)
        for k in ('fecha_creacion','fecha_modificacion'): d[k]=utc_iso(d[k])
        contenido.append(d)
    raw=json.dumps({'fuente':fuente,'corte':utc_iso(corte),'tickets':contenido},
                   ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    return Instantanea(fuente,corte,observada_en,tickets,hashlib.sha256(raw).hexdigest())


def crear_motor_lectura(url):
    return create_engine(url,hide_parameters=True,pool_pre_ping=True,
        isolation_level='REPEATABLE READ',execution_options={'postgresql_readonly':True},
        connect_args={'connect_timeout':5,'options':'-c default_transaction_read_only=on -c statement_timeout=10000 -c lock_timeout=3000'})


def motor_desde_entorno():
    names=('OP_DB_HOST','OP_DB_PORT','OP_DB_NAME','OP_DB_USER','OP_DB_PASSWORD')
    missing=[n for n in names if not os.environ.get(n,'').strip()]
    if missing: raise ValueError('Configurar origen operacional: '+', '.join(missing))
    try:
        port=int(os.environ['OP_DB_PORT'])
        if not 1<=port<=65535: raise ValueError()
    except ValueError as exc: raise ValueError('OP_DB_PORT inválido') from exc
    url=URL.create('postgresql+psycopg2',username=os.environ['OP_DB_USER'],
        password=os.environ['OP_DB_PASSWORD'],host=os.environ['OP_DB_HOST'],port=port,
        database=os.environ['OP_DB_NAME'])
    return crear_motor_lectura(url)


def leer_instantanea(engine, corte, fuente):
    utc_iso(corte)
    with engine.connect().execution_options(isolation_level='REPEATABLE READ',postgresql_readonly=True) as conn:
        with conn.begin():
            if conn.scalar(text('SHOW transaction_read_only'))!='on':
                raise RuntimeError('El origen exige transacción de solo lectura')
            observada=conn.scalar(text('SELECT transaction_timestamp()'))
            rows=conn.execute(SQL_INSTANTANEA,{'corte':corte}).mappings().all()
            tickets=tuple(TicketOperacional(**dict(row)) for row in rows)
    return crear_instantanea(fuente,corte,observada,tickets)
