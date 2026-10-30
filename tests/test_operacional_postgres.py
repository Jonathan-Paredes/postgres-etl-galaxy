from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch
import hashlib
import json
import uuid
import pandas as pd
import pytest
from sqlalchemy import text
from test_postgres import pg, migrate, rows
from conftest import ROOT
from carga_operacional import cargar_lote, ConflictoVersion
import carga_operacional as op
import etl_original as etl

pytestmark=pytest.mark.integration
C=datetime(2025,3,6,5,30,tzinfo=ZoneInfo('America/Santiago'))

@pytest.fixture
def operacional_pg(pg):
    migrate(pg)
    with pg.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
        conn.exec_driver_sql((ROOT/'sql/04_lotes_alertas.sql').read_text(encoding='utf-8'))
    return pg

def cargar(engine,df,corte=C,confirmado=False,**kw):
    h=hashlib.sha256(df.to_json(date_format='iso').encode()).hexdigest()
    return cargar_lote(df,fecha_corte=corte,archivo_origen='fixture_sintetico.xlsx',
                      hash_archivo=h,snapshot_confirmado=confirmado,engine=engine,**kw)

def count(pg,table):
    assert table in ['fact_tickets','etl_lotes','alertas_operacionales','etl_ticket_version']
    with pg.connect() as c: return c.scalar(text('SELECT count(*) FROM galaxy_dw.'+table))

def estados(pg):
    with pg.connect() as c:
        return dict(c.execute(text('SELECT f.numero_ticket,e.estado FROM galaxy_dw.fact_tickets f JOIN galaxy_dw.dim_estado e USING(estado_key)')).all())

def wip(fuente, minutos=5):
    df=fuente.iloc[[0]].copy()
    df.loc[0,'Estado']='Work in Progress'
    df['Minutos_WIP_solo_escenario']=minutos
    # Dato sintético que NO se usa como entrada al estado WIP.
    df.loc[0,'Fecha_creacion_ticket']=pd.Timestamp('2025-03-06 05:30')-pd.Timedelta(minutes=minutos)
    return df

@pytest.mark.parametrize('idx',[2,3])
def test_pendiente_y_cerrado_sin_alerta(operacional_pg,fuente,idx):
    r=cargar(operacional_pg,fuente.iloc[[idx]])
    assert r['alertas_detectadas']==0
    assert count(operacional_pg,'fact_tickets')==1

@pytest.mark.parametrize('minutos',[5,180])
def test_wip_cinco_minutos_o_tres_horas_misma_regla(operacional_pg,fuente,minutos):
    df=wip(fuente,minutos)
    r=cargar(operacional_pg,df)
    assert r['alertas_detectadas']==1 and r['alertas_nuevas']==1
    assert estados(operacional_pg)['OPEN-001']=='Work in Progress'
    with operacional_pg.connect() as c:
        assert c.scalar(text('SELECT codigo_regla FROM galaxy_dw.alertas_operacionales'))=='WIP_EN_CORTE_0530'

def test_wip_no_bloquea_resto(operacional_pg,fuente):
    fuente.loc[0,'Estado']='Work in Progress'
    r=cargar(operacional_pg,fuente)
    assert r['filas_insertadas']==4
    # En progreso también normaliza a WORK_IN_PROGRESS, sin alterar estado.
    assert r['alertas_detectadas']==2
    assert estados(operacional_pg)['OPEN-002']=='En progreso'
    with operacional_pg.connect() as c:
        alertas=[dict(x) for x in c.execute(text('SELECT * FROM galaxy_dw.alertas_operacionales ORDER BY numero_ticket')).mappings()]
    (ROOT/'test-results').mkdir(exist_ok=True)
    (ROOT/'test-results/iter2-ejemplo.json').write_text(json.dumps(
        {'origen':'Ejecución real de prueba sintética en PostgreSQL descartable',
         'lote':r,'alertas':alertas},default=str,ensure_ascii=False,indent=2),encoding='utf-8')

def test_reprocesar_mismo_corte_sin_duplicados(operacional_pg,fuente):
    a=cargar(operacional_pg,wip(fuente))
    b=cargar(operacional_pg,wip(fuente))
    assert b['filas_sin_cambios']==1 and b['filas_actualizadas']==0
    assert b['alertas_detectadas']==1 and b['alertas_nuevas']==0
    assert count(operacional_pg,'alertas_operacionales')==1
    with operacional_pg.connect() as c:
        assert str(c.scalar(text('SELECT lote_id FROM galaxy_dw.alertas_operacionales')))==str(a['lote_id'])

def test_dias_distintos_evidencia_historica(operacional_pg,fuente):
    cargar(operacional_pg,wip(fuente))
    cargar(operacional_pg,wip(fuente),C+timedelta(days=1))
    assert count(operacional_pg,'alertas_operacionales')==2

def test_wip_luego_cerrado_conserva_evidencia(operacional_pg,fuente):
    a=cargar(operacional_pg,wip(fuente))
    closed=fuente.iloc[[3]].copy()
    closed.loc[3,'Numero_ticket']='OPEN-001'
    closed.loc[3,'Fecha_creacion_ticket']=pd.Timestamp('2025-03-06 05:25')
    closed.loc[3,'Fecha_respuesta']=pd.Timestamp('2025-03-06 05:26')
    closed.loc[3,'Fecha_cierre']=pd.Timestamp('2025-03-06 06:00')
    r=cargar(operacional_pg,closed,C+timedelta(days=1),confirmado=True)
    assert r['filas_actualizadas']==1 and r['alertas_detectadas']==0
    assert estados(operacional_pg)['OPEN-001']=='Cerrado'
    with operacional_pg.connect() as c:
        alert=c.execute(text('SELECT * FROM galaxy_dw.alertas_operacionales')).mappings().one()
        assert alert['estado_observado']=='Work in Progress'
        assert str(alert['lote_id'])==str(a['lote_id'])

def test_siete_dias_borde_y_ticket_antiguo_recibido(operacional_pg,fuente):
    df=fuente.iloc[[0,2]].copy()
    df.loc[0,'Fecha_creacion_ticket']=pd.Timestamp('2025-02-27 05:30')
    df.loc[2,'Fecha_creacion_ticket']=pd.Timestamp('2020-01-01')
    r=cargar(operacional_pg,df)
    assert r['filas_insertadas']==2
    assert r['ventana_desde'].astimezone(ZoneInfo('America/Santiago')).isoformat()=='2025-02-27T05:30:00-03:00'

def test_carga_parcial_preserva_otros(operacional_pg,fuente):
    cargar(operacional_pg,fuente)
    r=cargar(operacional_pg,fuente.iloc[[0]],C+timedelta(days=1))
    assert count(operacional_pg,'fact_tickets')==4 and r['filas_sin_cambios']==1

def test_archivo_antiguo_no_sobrescribe(operacional_pg,fuente):
    old=fuente.iloc[[0]].copy()
    cargar(operacional_pg,old)
    newer=old.copy(); newer.loc[0,'Estado']='Pendiente'
    cargar(operacional_pg,newer,C+timedelta(days=1),confirmado=True)
    with pytest.raises(ConflictoVersion): cargar(operacional_pg,old,C,confirmado=True)
    assert estados(operacional_pg)['OPEN-001']=='Pendiente'
    with operacional_pg.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM galaxy_dw.etl_lotes WHERE estado_ejecucion='FALLIDO' AND error_codigo='CONFLICTO_VERSION'"))==1

def test_sin_marca_ni_confirmacion_no_sobrescribe(operacional_pg,fuente):
    df=fuente.iloc[[0]].copy(); cargar(operacional_pg,df)
    df.loc[0,'Estado']='Pendiente'
    with pytest.raises(ConflictoVersion): cargar(operacional_pg,df,C+timedelta(days=1))
    assert estados(operacional_pg)['OPEN-001']=='Abierto'

def test_modificacion_real_actualiza_y_rechaza_atraso(operacional_pg,fuente):
    df=fuente.iloc[[0]].copy(); df['Modificado']='2025-03-06T04:00:00-03:00'
    cargar(operacional_pg,df,columna_modificacion='Modificado')
    df.loc[0,'Estado']='Pendiente'; df['Modificado']='2025-03-07T04:00:00-03:00'
    r=cargar(operacional_pg,df,C+timedelta(days=1),columna_modificacion='Modificado')
    assert r['filas_actualizadas']==1
    df.loc[0,'Estado']='Abierto'; df['Modificado']='2025-03-06T04:00:00-03:00'
    with pytest.raises(ConflictoVersion): cargar(operacional_pg,df,C+timedelta(days=2),columna_modificacion='Modificado')
    assert estados(operacional_pg)['OPEN-001']=='Pendiente'

def test_rollback_integral_ante_fallo_alertas(operacional_pg,fuente):
    with patch.object(op,'evaluar_corte',side_effect=RuntimeError('fallo inducido')):
        with pytest.raises(RuntimeError): cargar(operacional_pg,wip(fuente))
    assert count(operacional_pg,'fact_tickets')==0
    assert count(operacional_pg,'etl_ticket_version')==0
    assert count(operacional_pg,'alertas_operacionales')==0
    with operacional_pg.connect() as c:
        r=c.execute(text('SELECT * FROM galaxy_dw.etl_lotes')).mappings().one()
        assert r['estado_ejecucion']=='FALLIDO' and r['fecha_fin'] is not None
        assert r['filas_insertadas']==r['filas_actualizadas']==r['alertas_detectadas']==0

def test_lote_uuid_repetido_idempotente(operacional_pg,fuente):
    id=str(uuid.uuid4())
    a=cargar(operacional_pg,wip(fuente),lote_id=id)
    b=cargar(operacional_pg,wip(fuente),lote_id=id)
    assert str(a['lote_id'])==str(b['lote_id'])
    assert count(operacional_pg,'etl_lotes')==1
    with pytest.raises(ConflictoVersion): cargar(operacional_pg,fuente,lote_id=id)

def test_evento_futuro_rechazado_con_auditoria(operacional_pg,fuente):
    with pytest.raises(ValueError,match='posterior'): cargar(operacional_pg,fuente,C.replace(year=2024))
    assert count(operacional_pg,'fact_tickets')==0
    with operacional_pg.connect() as c:
        assert c.scalar(text('SELECT estado_ejecucion FROM galaxy_dw.etl_lotes'))=='FALLIDO'

def test_no_bypass_por_api_historica(operacional_pg,fuente):
    with pytest.raises(ValueError,match='auditoría'): etl.cargar({},fuente)
    assert count(operacional_pg,'fact_tickets')==0

def test_incremental_modificacion_y_reconciliacion(operacional_pg,fuente):
    df=fuente.iloc[[0,2]].copy()
    df.loc[0,'Fecha_creacion_ticket']=pd.Timestamp('2025-02-27 05:30')
    df.loc[2,'Fecha_creacion_ticket']=pd.Timestamp('2025-02-10 00:00')
    df['Modificado']=['2025-02-27T05:30:00-03:00','2025-02-20T00:00:00-03:00']
    a=cargar(operacional_pg,df,columna_modificacion='Modificado')
    assert a['filas_recibidas']==2 and a['filas_insertadas']==1
    b=cargar(operacional_pg,df,columna_modificacion='Modificado',completo=True)
    assert b['filas_insertadas']==1 and b['filas_sin_cambios']==1
    assert count(operacional_pg,'fact_tickets')==2

def test_reproceso_identico_no_regresa_version(operacional_pg,fuente):
    df=fuente.iloc[[0]]
    cargar(operacional_pg,df,C+timedelta(days=1))
    cargar(operacional_pg,df,C)
    with operacional_pg.connect() as c:
        assert c.scalar(text('SELECT ultimo_corte FROM galaxy_dw.etl_ticket_version'))==C+timedelta(days=1)

def test_no_acepta_modificacion_anterior_a_creacion(operacional_pg,fuente):
    df=fuente.iloc[[0]].copy()
    df['Modificado']='2025-03-03T00:00:00-03:00'
    with pytest.raises(ValueError,match='anterior a la creación'):
        cargar(operacional_pg,df,columna_modificacion='Modificado')
    assert count(operacional_pg,'fact_tickets')==0
