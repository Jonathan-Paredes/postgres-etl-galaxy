"""Integración real; cada test crea y elimina SOLO su propia base UUID."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from conftest import ROOT
import etl_original as etl

pytestmark = pytest.mark.integration

@pytest.fixture
def pg(monkeypatch):
    raw=os.environ.get('TEST_PG_URL')
    if not raw:
        pytest.skip('PostgreSQL descartable no configurado: ejecutar scripts/run_tests.py')
    url=make_url(raw)
    if url.database != 'etl_test_control' or url.host not in ('127.0.0.1','localhost'):
        pytest.fail('Guardia de seguridad: TEST_PG_URL debe apuntar al control descartable local')
    name='etl_test_'+uuid.uuid4().hex
    admin=create_engine(url,isolation_level='AUTOCOMMIT')
    engine=None
    try:
        with admin.connect() as c: c.execute(text(f'CREATE DATABASE {name}'))
        engine=create_engine(url.set(database=name))
        with engine.begin() as c:
            for sql in ['sql/baseline/01_schema_estrella.sql','sql/baseline/02_tablas_ml.sql']:
                c.exec_driver_sql((ROOT/sql).read_text(encoding='utf-8-sig'))
        for k,v in dict(DB_HOST=url.host,DB_PORT=str(url.port),DB_NAME=name,DB_USER=url.username,DB_PASSWORD=url.password).items():
            monkeypatch.setenv(k,v)
        yield engine
    finally:
        if engine is not None: engine.dispose()
        # name es generado aquí, no procede de un usuario o configuración Galaxy.
        assert name.startswith('etl_test_') and len(name)==41
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'))
        admin.dispose()

def migrate(engine):
    # El fichero tiene su propia transacción explícita.
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as c:
        c.exec_driver_sql((ROOT/'sql/03_open_tickets.sql').read_text(encoding='utf-8'))

@pytest.fixture
def compatible_pg(pg):
    migrate(pg)
    return pg

def load(df):
    etl.cargar({},df)

def rows(pg):
    with pg.connect() as c:
        return c.execute(text('SELECT * FROM galaxy_dw.fact_tickets ORDER BY numero_ticket')).mappings().all()

def test_ddl_original_rechazado_sin_escrituras(pg,fuente):
    with pytest.raises(ValueError,match='DDL incompatible'): load(fuente)
    with pg.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM galaxy_dw.dim_equipo'))==0
    assert len(rows(pg))==0

def test_fixture_nulos_y_datos_de_cierre(compatible_pg,fuente):
    load(fuente)
    r={x['numero_ticket']:x for x in rows(compatible_pg)}
    assert len(r)==4
    for ticket in ['OPEN-001','OPEN-002','OPEN-003']:
        for col in ['ts_cierre','fecha_cierre_key','falla_cierre_key','operador_cierre_key','solucion','nota_cierre','duracion_min']:
            assert r[ticket][col] is None
    assert r['OPEN-001']['ts_respuesta'] is None
    assert r['OPEN-003']['fecha_respuesta_key'] is None
    assert r['OPEN-002']['ts_respuesta']==pd.Timestamp('2025-03-04 10:20')
    assert r['CLOSED-001']['ts_cierre']==pd.Timestamp('2025-03-02 09:00')
    assert r['CLOSED-001']['duracion_min']==60
    assert all(x['tiempo_abierto_min'] is None for x in r.values())

def test_repetir_fixture_preserva_pk_y_conteos(compatible_pg,fuente):
    load(fuente)
    before=[dict(r) for r in rows(compatible_pg)]
    load(fuente)
    assert [dict(r) for r in rows(compatible_pg)]==before

def test_cambio_de_estado_preserva_pk_y_fk_ml(compatible_pg,fuente):
    load(fuente)
    before={r['numero_ticket']:r['ticket_key'] for r in rows(compatible_pg)}
    with compatible_pg.begin() as c:
        model=c.scalar(text("INSERT INTO galaxy_dw.ml_modelos(nombre_modelo,version) VALUES ('demo','1') RETURNING modelo_key"))
        c.execute(text('INSERT INTO galaxy_dw.ml_xgboost_falla_pred(ticket_key,modelo_key,prob_falla,es_incidente_predicho) VALUES (:t,:m,0.5,true)'),{'t':before['OPEN-001'],'m':model})
    closed=fuente.iloc[[0]].copy()
    closed.loc[0,'Estado']='Cerrado'
    closed.loc[0,'Fecha_respuesta']=pd.Timestamp('2025-03-04 08:15')
    closed.loc[0,'Fecha_cierre']=pd.Timestamp('2025-03-04 10:00')
    closed.loc[0,'Tipo_falla_cierre']='Resuelta'
    closed.loc[0,'Operador_cierre']='Operador Demo B'
    closed.loc[0,'Solucion']='Solución sintética'
    closed.loc[0,'Duración (minutos)']=120
    load(closed)
    r={x['numero_ticket']:x for x in rows(compatible_pg)}
    assert len(r)==4 and r['OPEN-001']['ticket_key']==before['OPEN-001']
    assert r['OPEN-001']['duracion_min']==120
    with compatible_pg.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM galaxy_dw.ml_xgboost_falla_pred'))==1
    # Snapshot de reapertura: los NULL explícitos se conservan, no se arrastra cierre.
    load(fuente.iloc[[0]])
    r={x['numero_ticket']:x for x in rows(compatible_pg)}
    assert r['OPEN-001']['ts_cierre'] is None
    assert r['OPEN-001']['solucion'] is None
    assert r['OPEN-001']['ticket_key']==before['OPEN-001']

def test_incremental_parcial_no_borra_otros(compatible_pg,fuente):
    load(fuente)
    etl.cargar({},fuente.iloc[[0]],desde='2025-03-01',hasta='2025-03-31')
    assert len(rows(compatible_pg))==4

def test_ultimo_dia_con_hora_real(compatible_pg,fuente):
    df=fuente.iloc[[0]].copy()
    df.loc[0,'Fecha_creacion_ticket']=pd.Timestamp('2025-03-31 23:59:59.999999')
    etl.cargar({},df,desde='2025-03-01',hasta='2025-03-31')
    assert rows(compatible_pg)[0]['ts_creacion']==pd.Timestamp('2025-03-31 23:59:59.999999')

def test_rollback_fallo_post_dimensiones(compatible_pg,fuente):
    with patch.object(etl,'_upsert_fact',side_effect=RuntimeError('fallo inducido')):
        with pytest.raises(RuntimeError): load(fuente)
    assert len(rows(compatible_pg))==0
    with compatible_pg.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM galaxy_dw.dim_estado'))==0
        assert c.scalar(text("SELECT count(*) FROM pg_class WHERE relname LIKE 'stg_%'"))==0

def test_dos_cargas_concurrentes_sin_colision(compatible_pg,fuente):
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(load,fuente.copy()) for _ in range(2)]
        for future in futures: future.result(timeout=60)
    assert len(rows(compatible_pg))==4
    with compatible_pg.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM galaxy_dw.dim_equipo'))==1
        assert c.scalar(text("SELECT count(*) FROM pg_class WHERE relname LIKE 'stg_%'"))==0

def test_cargas_concurrentes_distintas_no_mezclan_filas(compatible_pg,fuente):
    second=fuente.iloc[[0]].copy()
    second.loc[0,'Numero_ticket']='OPEN-004'
    second.loc[0,'Equipo']='CAMION DEMO 2'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(load,df) for df in (fuente,second)]
        for future in futures: future.result(timeout=60)
    assert len(rows(compatible_pg))==5
    with compatible_pg.connect() as c:
        assert c.scalar(text("SELECT e.equipo_codigo FROM galaxy_dw.fact_tickets f JOIN galaxy_dw.dim_equipo e USING(equipo_key) WHERE numero_ticket='OPEN-004'"))=='CAMION DEMO 2'

def test_abierto_sin_clasificacion_equipo_ni_sitio(compatible_pg,fuente):
    df=fuente.iloc[[0]].copy()
    for col in ('Clasificación','Equipo','Sitio'): df.loc[0,col]=None
    load(df)
    r=rows(compatible_pg)[0]
    assert r['clasificacion_key'] is None
    assert r['equipo_key'] is None
    assert r['sitio_key'] is None

def test_migracion_preserva_ticket_numerico(pg):
    # Usa el ETL solamente después de migrar: la compatibilidad histórica se
    # demuestra insertando una fila con el DDL original y conservando su PK.
    with pg.begin() as c:
        c.exec_driver_sql("""
            INSERT INTO galaxy_dw.dim_fecha VALUES(20250302,'2025-03-02',2025,3,'Marzo',2,1,7,'Domingo',true);
            INSERT INTO galaxy_dw.dim_prioridad(prioridad) VALUES ('Media');
            INSERT INTO galaxy_dw.dim_estado(estado) VALUES ('Cerrado');
            INSERT INTO galaxy_dw.dim_categoria_ticket(tipo_ticket,tipo_requerimiento) VALUES ('Incidente','Demo');
            INSERT INTO galaxy_dw.dim_solicitud_falla(tipo_solicitud,tipo_falla) VALUES ('Demo','Demo');
            INSERT INTO galaxy_dw.dim_falla_cierre(tipo_falla_cierre) VALUES ('Demo');
            INSERT INTO galaxy_dw.dim_apertura(modo_apertura,origen) VALUES ('Manual','Demo');
            INSERT INTO galaxy_dw.dim_clasificacion(clasificacion) VALUES ('Demo');
            INSERT INTO galaxy_dw.dim_operador(operador_nombre) VALUES ('Demo');
            INSERT INTO galaxy_dw.fact_tickets(numero_ticket,fecha_creacion_key,fecha_respuesta_key,fecha_cierre_key,
              ts_creacion,ts_respuesta,ts_cierre,prioridad_key,estado_key,categoria_ticket_key,solicitud_falla_key,
              falla_cierre_key,apertura_key,clasificacion_key,operador_apertura_key,operador_cierre_key,tiempo_abierto_min,es_incidente)
            VALUES(123,20250302,20250302,20250302,'2025-03-02','2025-03-02','2025-03-02',1,1,1,1,1,1,1,1,1,60,true);
        """)
    before=rows(pg)[0]['ticket_key']
    migrate(pg)
    assert rows(pg)[0]['numero_ticket']=='123'
    assert rows(pg)[0]['ticket_key']==before
