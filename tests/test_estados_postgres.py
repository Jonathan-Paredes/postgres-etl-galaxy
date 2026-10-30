import json
from datetime import timedelta
import pandas as pd
import pytest
from sqlalchemy import text
from test_postgres import pg, rows
from test_operacional_postgres import operacional_pg, cargar, estados, count, wip, C
from test_estados_unit import ESTADOS, NOTA
from carga_operacional import ConflictoVersion
from conftest import ROOT

pytestmark=pytest.mark.integration

def ticket(fuente,estado):
    df=fuente.iloc[[3 if estado=='Cerrado' else 0]].copy().reset_index(drop=True)
    df.loc[0,'Estado']=estado
    df.loc[0,'Numero_ticket']='IT3-001'
    df.loc[0,'Asunto']='Observación original; referencia al ticket REL-0007.'
    if estado=='Cancelado':
        df.loc[0,'Nota_cierre']=NOTA
        df.loc[0,'Solucion']='Duplicado del ticket REL-0007; conservar exactamente.'
    return df

@pytest.mark.parametrize('estado',ESTADOS)
def test_inserta_cinco_estados_en_postgres(operacional_pg,fuente,estado):
    df=ticket(fuente,estado)
    result=cargar(operacional_pg,df)
    assert result['filas_insertadas']==1
    assert estados(operacional_pg)['IT3-001']==estado
    assert result['alertas_detectadas']==(1 if estado=='Work in Progress' else 0)
    assert rows(operacional_pg)[0]['asunto']==df.loc[0,'Asunto']

@pytest.mark.parametrize('estado',ESTADOS)
def test_actualiza_a_cada_estado_sin_perder_pk(operacional_pg,fuente,estado):
    before=ticket(fuente,'Pendiente')
    cargar(operacional_pg,before)
    key=rows(operacional_pg)[0]['ticket_key']
    after=ticket(fuente,estado)
    after.loc[0,'Fecha_creacion_ticket']=before.loc[0,'Fecha_creacion_ticket']
    if estado=='Cerrado':
        after.loc[0,'Fecha_respuesta']=pd.Timestamp('2025-03-06 05:40')
        after.loc[0,'Fecha_cierre']=pd.Timestamp('2025-03-06 06:00')
    result=cargar(operacional_pg,after,C+timedelta(days=1),confirmado=True)
    assert estados(operacional_pg)['IT3-001']==estado
    assert rows(operacional_pg)[0]['ticket_key']==key
    assert result['filas_actualizadas']==(0 if estado=='Pendiente' else 1)
    assert result['alertas_detectadas']==(1 if estado=='Work in Progress' else 0)

@pytest.mark.parametrize('con_cierre',[False,True])
def test_cancelado_observaciones_fechas_y_referencias(operacional_pg,fuente,con_cierre):
    df=ticket(fuente,'Cancelado')
    if con_cierre:
        df.loc[0,'Fecha_cierre']=pd.Timestamp('2025-03-05 10:00')
    r=cargar(operacional_pg,df)
    stored=rows(operacional_pg)[0]
    assert stored['nota_cierre']==NOTA
    assert stored['solucion']==df.loc[0,'Solucion']
    assert stored['asunto']==df.loc[0,'Asunto']
    assert stored['duracion_min'] is None
    assert stored['operador_cierre_key'] is None
    assert r['alertas_detectadas']==0
    assert (stored['ts_cierre'] is not None)==con_cierre

def test_mixto_cinco_estados_no_bloquea_wip(operacional_pg,fuente):
    frames=[]
    for i,estado in enumerate(ESTADOS):
        df=ticket(fuente,estado); df['Numero_ticket']=f'IT3-{i+1:03}'
        frames.append(df)
    df=pd.concat(frames,ignore_index=True)
    r=cargar(operacional_pg,df)
    assert r['filas_recibidas']==r['filas_seleccionadas']==r['filas_insertadas']==5
    assert r['alertas_detectadas']==r['alertas_nuevas']==1
    assert set(estados(operacional_pg).values())==set(ESTADOS)
    with operacional_pg.connect() as conn:
        alertas=[dict(a) for a in conn.execute(text('SELECT * FROM galaxy_dw.alertas_operacionales')).mappings()]
        assert alertas[0]['estado_observado']=='Work in Progress'
        assert alertas[0]['numero_ticket']=='IT3-005'
        # La dimensión conserva VARCHAR(30) y su regla UNIQUE original.
        assert conn.scalar(text("SELECT character_maximum_length FROM information_schema.columns WHERE table_schema='galaxy_dw' AND table_name='dim_estado' AND column_name='estado'"))==30
    ROOT.joinpath('test-results/iter3-ejemplo.json').write_text(json.dumps(
        {'origen':'PostgreSQL descartable, estados confirmados y datos sintéticos',
         'lote':r,'estados':estados(operacional_pg),'alertas':alertas},default=str,ensure_ascii=False,indent=2),encoding='utf-8')

def test_historial_idempotencia_y_proteccion_al_cancelar(operacional_pg,fuente):
    original=ticket(fuente,'Work in Progress')
    first=cargar(operacional_pg,original)
    key=rows(operacional_pg)[0]['ticket_key']
    cancelled=ticket(fuente,'Cancelado')
    segundo=C+timedelta(days=1)
    update=cargar(operacional_pg,cancelled,segundo,confirmado=True)
    assert update['filas_actualizadas']==1 and update['alertas_detectadas']==0
    repeat=cargar(operacional_pg,cancelled,segundo)
    assert repeat['filas_sin_cambios']==1 and repeat['alertas_nuevas']==0
    with pytest.raises(ConflictoVersion): cargar(operacional_pg,original,C,confirmado=True)
    assert estados(operacional_pg)['IT3-001']=='Cancelado'
    assert rows(operacional_pg)[0]['nota_cierre']==NOTA
    assert rows(operacional_pg)[0]['ticket_key']==key
    with operacional_pg.connect() as conn:
        alert=conn.execute(text('SELECT * FROM galaxy_dw.alertas_operacionales')).mappings().one()
        assert alert['estado_observado']=='Work in Progress'
        assert str(alert['lote_id'])==str(first['lote_id'])
        assert alert['fecha_corte']==C

def test_actualizacion_cancelado_sin_evidencia_sigue_rechazada(operacional_pg,fuente):
    cargar(operacional_pg,ticket(fuente,'Abierto'))
    with pytest.raises(ConflictoVersion):
        cargar(operacional_pg,ticket(fuente,'Cancelado'),C+timedelta(days=1))
    assert estados(operacional_pg)['IT3-001']=='Abierto'

def test_cancelado_literal_en_dimension_y_sin_alerta(operacional_pg,fuente):
    df=ticket(fuente,'Cancelado'); df['Estado']='  cAnCeLaDo  '
    r=cargar(operacional_pg,df)
    assert estados(operacional_pg)['IT3-001']=='  cAnCeLaDo  '
    assert r['alertas_detectadas']==0
