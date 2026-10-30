from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd
import pytest
from corte_operacional import ConfiguracionCorte
from alertas_operacionales import evaluar_corte, normalizar_estado
from carga_operacional import seleccionar_incremental, _decidir, ConflictoVersion, huella, leer_archivo
import etl_original as etl
from conftest import FIXTURE

C=datetime(2025,3,6,5,30,tzinfo=ZoneInfo('America/Santiago'))

@pytest.mark.parametrize('estado',['Pendiente','Cerrado','Abierto','Resuelto','Cancelado'])
def test_no_alerta_wip_para_otro_estado(estado):
    assert evaluar_corte([{'Numero_ticket':'X','Estado':estado}],C,'lote')==[]

@pytest.mark.parametrize('estado',['Work in Progress',' work   in progress ','En progreso','En proceso','WIP','WORK_IN_PROGRESS'])
def test_motor_puro_conserva_original(estado):
    row={'Numero_ticket':'X','Estado':estado,'Tiempo_abierto':99999}
    before=dict(row)
    alert=evaluar_corte([row],C,'lote')[0]
    assert alert.estado_observado==estado
    assert row==before
    assert alert.codigo_regla=='WIP_EN_CORTE_0530'

def test_cancelado_con_correspondencia_confirmada():
    assert normalizar_estado('Cancelado')=='CANCELADO'

@pytest.mark.parametrize('hora,esperado',[(5,5),(4,5),(6,6)])
def test_ultimo_corte_efectivo(hora,esperado):
    cfg=ConfiguracionCorte()
    ref=datetime(2025,3,6,hora,0,tzinfo=ZoneInfo('America/Santiago'))
    assert cfg.efectivo(ref).day==esperado
    assert cfg.efectivo(ref).hour==5 and cfg.efectivo(ref).minute==30

def test_corte_invalido_o_ingenuo():
    with pytest.raises(ValueError): ConfiguracionCorte().validar(datetime(2025,3,6,5,30))
    with pytest.raises(ValueError): ConfiguracionCorte().validar(C.replace(minute=31))

def test_ventana_siete_dias_civiles_con_dst():
    cfg=ConfiguracionCorte()
    corte=datetime(2025,4,7,5,30,tzinfo=ZoneInfo('America/Santiago'))
    desde,_=cfg.ventana(corte)
    assert desde.isoformat()=='2025-03-31T05:30:00-03:00'
    assert corte.isoformat()=='2025-04-07T05:30:00-04:00'
    assert (corte.astimezone(timezone.utc)-desde.astimezone(timezone.utc)).total_seconds()==169*3600

def test_ventana_configurable():
    assert (C-ConfiguracionCorte(3).ventana(C)[0]).days==3
    with pytest.raises(ValueError): ConfiguracionCorte(0)

def test_sin_marca_no_filtra_creacion(fuente):
    fuente.loc[0,'Fecha_creacion_ticket']=pd.Timestamp('2010-01-01')
    selected,marcas=seleccionar_incremental(fuente,C,ConfiguracionCorte())
    assert len(selected)==4 and marcas=={}

def test_modificacion_y_borde_inclusivo(fuente):
    fuente['Modificado']=['2025-02-27T05:30:00-03:00','2025-02-27T05:29:59-03:00','2025-03-06T05:30:00-03:00','2025-02-20T01:00:00-03:00']
    selected,_=seleccionar_incremental(fuente,C,ConfiguracionCorte(),'Modificado')
    assert list(selected.Numero_ticket)==['OPEN-001','OPEN-003']
    selected,_=seleccionar_incremental(fuente,C,ConfiguracionCorte(),'Modificado',True)
    assert len(selected)==4

def test_no_permite_modificacion_futura(fuente):
    fuente['Modificado']='2030-01-01T00:00:00-03:00'
    with pytest.raises(ValueError,match='posterior'): seleccionar_incremental(fuente,C,ConfiguracionCorte(),'Modificado')

@pytest.mark.parametrize('columna',etl.FECHAS)
def test_no_reutiliza_fecha_de_creacion_respuesta_o_cierre(fuente,columna):
    with pytest.raises(ValueError,match='no es la marca'):
        seleccionar_incremental(fuente,C,ConfiguracionCorte(),columna)

def test_huella_no_inventa_modificacion(fuente):
    a=fuente.iloc[0].to_dict()
    b=dict(a,Modificacion='2030-01-01')
    assert huella(a)==huella(b)

def test_archivo_y_hash_mismos_bytes():
    import hashlib
    data,h=leer_archivo(FIXTURE)
    assert h==hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert len(data)==4

def test_wip_valido_y_no_se_reescribe(fuente):
    fuente.loc[0,'Estado']='Work in Progress'
    assert etl.validar_entrada(fuente).loc[0,'Estado']=='Work in Progress'

def test_conflicto_sin_fecha_origen_no_ultimo_archivo_gana():
    anterior={'hash_contenido':'a','ultimo_corte':C,'modificacion_origen':None}
    with pytest.raises(ConflictoVersion): _decidir(anterior,'b',C.replace(day=7),None,False,True)
    assert _decidir(anterior,'b',C.replace(day=7),None,True,True)
    with pytest.raises(ConflictoVersion): _decidir(anterior,'b',C,None,True,True)
