from datetime import timedelta
from pathlib import Path
import hashlib
import json
import os
import socket
import subprocess
import sys
from unittest.mock import patch
import pytest
from sqlalchemy import text, event
from sqlalchemy.exc import DBAPIError
from test_postgres import pg
from conftest import ROOT
from test_reportabilidad_unit import C
from fuente_operacional import crear_motor_lectura, leer_instantanea
from reporte_operacional import agregar, generar_grafico
from agente_reportabilidad import ejecutar_reporte, ErrorReporte
from auditoria_reportes import AuditoriaReportes

pytestmark=pytest.mark.integration

@pytest.fixture
def fuente_pg(pg):
    with pg.begin() as conn:
        # text() compila el operador % de PostgreSQL para el driver psycopg2.
        conn.execute(text((ROOT/'tests/fixtures/operacional.sql').read_text(encoding='utf-8')))
    reader=crear_motor_lectura(pg.url)
    try: yield pg,reader
    finally: reader.dispose()

def ejecutar(reader,tmp_path,corte=C):
    return ejecutar_reporte(corte=corte,fuente='mesa-sintetica',auditoria=tmp_path/'audit.sqlite3',salida=tmp_path/'salida',engine=reader)

def estado_fuente(writer):
    with writer.connect() as conn:
        return conn.execute(text('SELECT * FROM operacional.ticket_versiones ORDER BY numero_ticket,fecha_modificacion')).all()

def test_conteos_historicos_solo_fixture_y_dos_tipos(fuente_pg,tmp_path):
    writer,reader=fuente_pg
    r=ejecutar(reader,tmp_path)
    assert r['datos']['leidos']==20 and r['datos']['activos']==18
    counts={v['estado']:(v['Incident'],v['Service Request']) for v in r['datos']['por_estado']}
    assert counts=={'Pendiente':(11,2),'Abierto':(2,1),'Work in Progress':(1,1)}
    message=Path(r['directorio'],'mensaje.txt').read_text(encoding='utf-8')
    assert 'Resumen de incidentes:\nPendientes: 11\nAbiertos: 2\nWork in Progress: 1' in message
    assert 'Resumen de requerimientos:\nPendientes: 2\nAbiertos: 1\nWork in Progress: 1' in message

def test_componentes_dinamicos_y_totales_coinciden(fuente_pg,tmp_path):
    writer,reader=fuente_pg
    with writer.begin() as conn:
        conn.execute(text('''INSERT INTO operacional.ticket_versiones VALUES
            ('NUEVO','Incident',:componente,'Abierto','Dato nuevo',:creada,:modificada)'''),
            {'componente':'Componente completamente nuevo','creada':C-timedelta(hours=1),'modificada':C-timedelta(minutes=1)})
    r=ejecutar(reader,tmp_path)
    groups=r['datos']['por_componente']
    assert any(g['componente']=='Componente completamente nuevo' and g['Incident']==1 for g in groups)
    assert sum(g['Incident']+g['Service Request'] for g in groups)==r['datos']['activos']==19

def test_fuente_actualizada_despues_0530_no_dw(fuente_pg,tmp_path):
    writer,reader=fuente_pg
    temprano=agregar(leer_instantanea(reader,C.replace(hour=5,minute=30),'mesa-sintetica'))
    tarde=agregar(leer_instantanea(reader,C,'mesa-sintetica'))
    assert not temprano.wip
    assert {t.numero_ticket for t in tarde.wip}=={'I-014','SR-004'}
    assert next(t.estado for t in temprano.instantanea.tickets if t.numero_ticket=='I-014')=='Pendiente'
    assert next(t.estado for t in tarde.instantanea.tickets if t.numero_ticket=='I-014')=='Work in Progress'
    with writer.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM galaxy_dw.fact_tickets'))==0

def test_preserva_estados_observaciones_y_origen_inmutable(fuente_pg,tmp_path):
    writer,reader=fuente_pg
    antes=estado_fuente(writer)
    snap=leer_instantanea(reader,C,'mesa-sintetica')
    cancelled=next(t for t in snap.tickets if t.numero_ticket=='SR-005')
    assert cancelled.estado=='Cancelado'
    assert cancelled.observaciones=='Duplicado de SR-002. Observación original.'
    ejecutar(reader,tmp_path)
    assert estado_fuente(writer)==antes

def test_conexion_postgres_real_solo_lectura(fuente_pg):
    writer,reader=fuente_pg
    before=estado_fuente(writer)
    with reader.connect() as conn:
        assert conn.scalar(text('SHOW transaction_read_only'))=='on'
        conn.rollback()
        with pytest.raises(DBAPIError):
            conn.execute(text("INSERT INTO operacional.ticket_versiones VALUES ('PROHIBIDO','Incident','X','Abierto','X',now(),now())"))
        conn.rollback()
    assert estado_fuente(writer)==before

def test_una_sola_instantanea_para_imagen_y_mensaje(fuente_pg,tmp_path):
    writer,reader=fuente_pg
    statements=[]
    def record(conn,cursor,statement,parameters,context,executemany): statements.append((statement,parameters))
    event.listen(reader,'before_cursor_execute',record)
    try:
        def render(resumen,path):
            # Cambio concurrente hecho por el test, nunca por el lector del agente.
            with writer.begin() as c:
                c.execute(text("INSERT INTO operacional.ticket_versiones VALUES ('POST-LECTURA','Incident','Nuevo','Abierto','Concurrente',:fecha,:fecha)"),{'fecha':C-timedelta(minutes=1)})
            generar_grafico(resumen,path)
        with patch('agente_reportabilidad.generar_grafico',side_effect=render):
            r=ejecutar(reader,tmp_path)
    finally: event.remove(reader,'before_cursor_execute',record)
    queries=[(sql,p) for sql,p in statements if 'FROM operacional.ticket_versiones' in sql]
    assert len(queries)==1
    assert '%(corte)s' in queries[0][0] and queries[0][1]['corte']==C
    assert not any('galaxy_dw' in sql for sql,p in statements)
    assert r['datos']['leidos']==20  # No 21 a mitad de construir el informe.
    assert json.loads(Path(r['directorio'],'datos_reporte.json').read_text(encoding='utf-8'))==r['datos']
    assert 'Abiertos: 2' in Path(r['directorio'],'mensaje.txt').read_text(encoding='utf-8')

def test_fallo_conexion_auditado_y_recuperacion(fuente_pg,tmp_path):
    writer,reader=fuente_pg
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    broken=crear_motor_lectura(writer.url.set(port=port))
    try:
        with pytest.raises(ErrorReporte) as exc: ejecutar(broken,tmp_path)
    finally: broken.dispose()
    store=AuditoriaReportes(tmp_path/'audit.sqlite3')
    row=store.ejecucion(exc.value.ejecucion_id)
    assert row['estado']=='FALLIDO' and row['tickets_leidos'] is None
    assert row['conteos_json'] is None and not store.evidencias()
    assert not (tmp_path/'salida').exists()
    assert ejecutar(reader,tmp_path)['estado']=='COMPLETADO'

def test_reintento_idempotente_mismos_bytes_y_evidencias(fuente_pg,tmp_path):
    _,reader=fuente_pg
    a=ejecutar(reader,tmp_path)
    b=ejecutar(reader,tmp_path,C.astimezone(__import__('datetime').timezone.utc))
    store=AuditoriaReportes(tmp_path/'audit.sqlite3')
    assert len(store.evidencias())==2
    assert {x['primera_ejecucion'] for x in store.evidencias()}=={a['ejecucion_id']}
    for filename in ['reporte.png','mensaje.txt','datos_reporte.json']:
        assert Path(a['directorio'],filename).read_bytes()==Path(b['directorio'],filename).read_bytes()

def test_cortes_distintos_guardan_historial(fuente_pg,tmp_path):
    _,reader=fuente_pg
    a=ejecutar(reader,tmp_path)
    first=AuditoriaReportes(tmp_path/'audit.sqlite3').evidencias()
    b=ejecutar(reader,tmp_path,C+timedelta(days=1))
    all=AuditoriaReportes(tmp_path/'audit.sqlite3').evidencias()
    assert len(all)==4
    assert all[:2]==first
    assert b['datos']['por_estado'][0]['Incident']==10  # I-001 cerró después del primer corte.

def test_sin_activos_y_sin_falsas_alertas(fuente_pg,tmp_path):
    writer,reader=fuente_pg
    with writer.begin() as conn:
        conn.execute(text('''INSERT INTO operacional.ticket_versiones
          SELECT numero_ticket,tipo_ticket,componente,'Cerrado',observaciones,fecha_creacion,:fecha
          FROM (SELECT DISTINCT ON(numero_ticket) * FROM operacional.ticket_versiones
                WHERE fecha_modificacion<=:corte ORDER BY numero_ticket,fecha_modificacion DESC) AS t'''),
                {'fecha':C-timedelta(seconds=1),'corte':C})
    r=ejecutar(reader,tmp_path)
    assert r['datos']['leidos']==20 and r['datos']['activos']==0
    assert not AuditoriaReportes(tmp_path/'audit.sqlite3').evidencias()
    from PIL import Image
    with Image.open(Path(r['directorio'],'reporte.png')) as image: image.verify()

def test_version_futura_no_cambia_reporte_historico(fuente_pg):
    _,reader=fuente_pg
    snap=leer_instantanea(reader,C,'mesa-sintetica')
    assert next(t.estado for t in snap.tickets if t.numero_ticket=='I-001')=='Pendiente'
    after=leer_instantanea(reader,C+timedelta(days=1),'mesa-sintetica')
    assert next(t.estado for t in after.tickets if t.numero_ticket=='I-001')=='Cerrado'

def test_cli_real_y_ejemplo_exportable(fuente_pg,tmp_path):
    writer,reader=fuente_pg
    env=os.environ.copy()
    for key,val in {'OP_DB_HOST':writer.url.host,'OP_DB_PORT':str(writer.url.port),
                    'OP_DB_NAME':writer.url.database,'OP_DB_USER':writer.url.username,'OP_DB_PASSWORD':writer.url.password}.items():
        env[key]=val
    result=subprocess.run([sys.executable,str(ROOT/'scr/agente_reportabilidad.py'),'--corte',C.isoformat(),
        '--fuente-id','mesa-sintetica','--auditoria',str(tmp_path/'cli.sqlite3'),'--salida',str(tmp_path/'cli')],
        env=env,cwd=ROOT,capture_output=True,text=True,timeout=60)
    assert result.returncode==0, 'CLI no completó; revisar auditoría del test'
    data=json.loads(result.stdout)
    assert data['estado']=='COMPLETADO' and data['datos']['activos']==18
    dest=ROOT/'test-results/iter4-ejemplo'; dest.mkdir(exist_ok=True)
    import shutil
    for filename in ['reporte.png','mensaje.txt','datos_reporte.json']:
        shutil.copy2(Path(data['directorio'],filename),dest/filename)
    store=AuditoriaReportes(tmp_path/'cli.sqlite3')
    audit=store.ejecucion(data['ejecucion_id']); audit['directorio']='artefactos-del-ejemplo'
    (dest/'auditoria.json').write_text(json.dumps({'ejecucion':audit,'alertas':store.evidencias()},ensure_ascii=False,indent=2),encoding='utf-8')
