import os
from unittest.mock import patch
import pandas as pd
import pytest
from sqlalchemy.engine import make_url
import etl_original as etl
import db
from conftest import FIXTURE

def test_fixture_conserva_los_cuatro_escenarios(fuente):
    assert list(fuente.Numero_ticket) == ['OPEN-001','OPEN-002','OPEN-003','CLOSED-001']
    assert list(fuente.Estado) == ['Abierto','En progreso','Pendiente','Cerrado']
    assert fuente.Fecha_cierre.isna().sum() == 3
    assert fuente.Fecha_respuesta.isna().sum() == 2
    assert fuente.Solucion.isna().sum() == 3
    assert fuente['Duración (minutos)'].isna().sum() == 3
    assert fuente.Tiempo_abierto.isna().all()

def test_columnas_se_validan_antes_de_fechas(fuente):
    fuente['Fecha_cierre'] = fuente['Fecha_cierre'].astype(object)
    fuente.loc[0,'Fecha_cierre'] = 'no es fecha'
    with pytest.raises(ValueError, match='Faltan columnas.*Fecha_creacion_ticket'):
        etl.validar_entrada(fuente.drop(columns='Fecha_creacion_ticket'))

@pytest.mark.parametrize('col',etl.FECHAS)
def test_fechas_invalidas_no_se_convierten_en_nulos(fuente,col):
    fuente[col] = fuente[col].astype(object)
    fuente.loc[0,col] = 'no-es-fecha'
    with pytest.raises(ValueError,match='Fecha inválida'):
        etl.validar_entrada(fuente)

def test_iso_no_intercambia_mes_dia(fuente):
    assert fuente.loc[0,'Fecha_creacion_ticket'] == pd.Timestamp('2025-03-04 08:00')

@pytest.mark.parametrize('col',['Numero_ticket','Estado','Fecha_creacion_ticket','Prioridad'])
def test_campos_obligatorios(fuente,col):
    fuente.loc[0,col] = None
    with pytest.raises(ValueError):
        etl.validar_entrada(fuente)

def test_duplicados_rechazados(fuente):
    with pytest.raises(ValueError,match='único'):
        etl.validar_entrada(pd.concat([fuente,fuente.iloc[:1]],ignore_index=True))

def test_claves_fecha_no_se_inventan(fuente):
    dims=etl.construir_dimensiones(fuente)
    assert dims['dim_fecha'].fecha_key.isna().sum()==0
    assert len(dims['dim_falla_cierre'])==1
    assert not any(dims['dim_operador'].operador_nombre.str.contains('DESCONOCIDO|SIN CIERRE'))

@pytest.mark.parametrize('estado',['Abierto','Pendiente','En progreso','En proceso','Escalado'])
def test_estados_no_terminales(fuente,estado):
    fuente.loc[0,'Estado']=estado
    assert pd.isna(etl.validar_entrada(fuente).loc[0,'Fecha_cierre'])

@pytest.mark.parametrize('estado',['Cerrado','Resuelto'])
def test_terminal_requiere_cierre(fuente,estado):
    fuente.loc[0,'Estado']=estado
    with pytest.raises(ValueError,match='inconsistentes'):
        etl.validar_entrada(fuente)

def test_cerrado_sin_respuesta_no_inventa_evento(fuente):
    fuente.loc[3,'Fecha_respuesta']=None
    assert pd.isna(etl.validar_entrada(fuente).loc[3,'Fecha_respuesta'])

@pytest.mark.parametrize('col',['Nota_cierre','Solucion','Tipo_falla_cierre','Operador_cierre','Duración (minutos)'])
def test_no_cierre_fabricado(fuente,col):
    fuente[col]=fuente[col].astype(object)
    fuente.loc[0,col]=20 if col=='Duración (minutos)' else 'informado'
    with pytest.raises(ValueError,match='sin Fecha_cierre'):
        etl.validar_entrada(fuente)

def test_rango_incluye_ultimo_dia_hasta_ultima_fraccion(fuente):
    fuente.loc[0,'Fecha_creacion_ticket']=pd.Timestamp('2025-03-31 23:59:59.999999')
    fuente.loc[2,'Fecha_creacion_ticket']=pd.Timestamp('2025-04-01 00:00')
    result=etl.filtrar_rango(fuente,'2025-03-01','2025-03-31')
    assert 'OPEN-001' in set(result.Numero_ticket)
    assert 'OPEN-003' not in set(result.Numero_ticket)

@pytest.mark.parametrize('desde,hasta',[('2025-03-31','2025-03-01'),('2025-03-01',None)])
def test_rango_invalido(fuente,desde,hasta):
    with pytest.raises(ValueError): etl.filtrar_rango(fuente,desde,hasta)

def test_dry_run_no_abre_conexion(fuente):
    with patch.object(etl,'get_engine',side_effect=AssertionError('No debe conectar')):
        etl.cargar({},fuente,dry_run=True)

def test_no_se_permite_truncate(fuente):
    with patch.object(etl,'get_engine',side_effect=AssertionError('No debe conectar')):
        with pytest.raises(ValueError,match='deshabilitado'):
            etl.cargar({},fuente,truncate=True)

def test_no_credenciales_por_defecto(monkeypatch):
    for name in ('DB_HOST','DB_PORT','DB_NAME','DB_USER','DB_PASSWORD'):
        monkeypatch.delenv(name,raising=False)
    with pytest.raises(ValueError,match='DB_PASSWORD'): db.get_engine()

def test_password_con_caracteres_especiales(monkeypatch):
    for k,v in dict(DB_HOST='127.0.0.1',DB_PORT='5432',DB_NAME='etl_test_demo',DB_USER='demo',DB_PASSWORD='x:@/#?%').items():
        monkeypatch.setenv(k,v)
    engine=db.get_engine()
    try: assert engine.url.password=='x:@/#?%'
    finally: engine.dispose()

def test_estado_desconocido_rechazado(fuente):
    fuente.loc[0,'Estado']='Desconocido'
    with pytest.raises(ValueError,match='Estado ausente'): etl.validar_entrada(fuente)

def test_sin_datos_no_conecta(fuente):
    with patch.object(etl,'get_engine',side_effect=AssertionError('No debe conectar')):
        etl.cargar({},fuente.iloc[:0])

@pytest.mark.parametrize('col',['Fecha_respuesta','Fecha_cierre'])
def test_texto_nat_no_es_ausencia_legitima(fuente,col):
    fuente[col]=fuente[col].astype(object)
    fuente.loc[0,col]='NaT'
    with pytest.raises(ValueError,match='Fecha inválida'): etl.validar_entrada(fuente)

def test_solo_abiertos_conservan_claves_naturales_texto(fuente):
    df=etl.validar_entrada(fuente.iloc[[0]])
    assert str(df['Operador_cierre'].dtype)=='string'
    assert str(df['Tipo_falla_cierre'].dtype)=='string'

@pytest.mark.parametrize('col',['Fecha_respuesta','Fecha_cierre'])
def test_fecha_anterior_a_creacion_rechazada(fuente,col):
    fuente.loc[3,col]=pd.Timestamp('2020-01-01')
    with pytest.raises(ValueError,match='no puede preceder'): etl.validar_entrada(fuente)

@pytest.mark.parametrize('col',['Tiempo_abierto','Duración (minutos)'])
def test_duracion_negativa_rechazada(fuente,col):
    fuente.loc[3,col]=-1
    with pytest.raises(ValueError,match='negativa'): etl.validar_entrada(fuente)
