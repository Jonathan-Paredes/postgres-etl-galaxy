import pandas as pd
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
import etl_original as etl
from alertas_operacionales import normalizar_estado, evaluar_corte

ESTADOS=('Cerrado','Abierto','Pendiente','Cancelado','Work in Progress')
C=datetime(2025,3,6,5,30,tzinfo=ZoneInfo('America/Santiago'))
NOTA='Cancelación por duplicidad; relacionado con ticket CLOSED-001.  Conservar referencia y acentos: revisión.\nObservación original.'

@pytest.mark.parametrize('estado',ESTADOS)
def test_acepta_cada_estado_confirmado(fuente,estado):
    df=fuente.iloc[[3 if estado=='Cerrado' else 0]].copy()
    df['Estado']=estado
    result=etl.validar_entrada(df)
    assert result.iloc[0]['Estado']==estado

@pytest.mark.parametrize('estado',ESTADOS)
def test_solo_wip_genera_infraccion(estado):
    row={'Numero_ticket':'IT3','Estado':estado,'Nota_cierre':'Referido a Work in Progress, ticket 555'}
    result=evaluar_corte([row],C,'lote')
    assert len(result)==(1 if estado=='Work in Progress' else 0)
    if result: assert result[0].codigo_regla=='WIP_EN_CORTE_0530'

@pytest.mark.parametrize('con_cierre',[False,True])
def test_cancelado_conserva_textos_sin_imputacion(fuente,con_cierre):
    df=fuente.iloc[[3 if con_cierre else 0]].copy()
    df['Estado']='Cancelado'
    for col in ('Asunto','Nota_cierre','Solucion'): df[col]=NOTA
    result=etl.validar_entrada(df)
    for col in ('Asunto','Nota_cierre','Solucion'): assert result.iloc[0][col]==NOTA
    if not con_cierre:
        for col in ('Fecha_respuesta','Fecha_cierre','Duración (minutos)','Tipo_falla_cierre','Operador_cierre'):
            assert pd.isna(result.iloc[0][col])

def test_estado_cancelado_literal_con_espacios_y_mayusculas(fuente):
    df=fuente.iloc[[0]].copy(); df['Estado']='  cAnCeLaDo  '
    assert etl.validar_entrada(df).iloc[0]['Estado']=='  cAnCeLaDo  '
    assert normalizar_estado('  cAnCeLaDo  ')=='CANCELADO'

@pytest.mark.parametrize('estado',['Suspendido','Reabierto','En revisión'])
def test_no_agrega_estados_no_autorizados(fuente,estado):
    df=fuente.iloc[[0]].copy(); df['Estado']=estado
    assert normalizar_estado(estado)=='NO_CONFIRMADO'
    with pytest.raises(ValueError,match='Estado ausente o no reconocido'):
        etl.validar_entrada(df)

@pytest.mark.parametrize('estado',['Resuelto','Escalado','En progreso','En proceso','WIP','WORK_IN_PROGRESS'])
def test_compatibilidad_preexistente_analizada_y_conservada(fuente,estado):
    df=fuente.iloc[[3 if estado=='Resuelto' else 0]].copy(); df['Estado']=estado
    assert etl.validar_entrada(df).iloc[0]['Estado']==estado
