from datetime import datetime, timedelta, timezone
from dataclasses import replace
from zoneinfo import ZoneInfo
from pathlib import Path
import json
from unittest.mock import patch
import pytest
from fuente_operacional import TicketOperacional, crear_instantanea, motor_desde_entorno
from reporte_operacional import agregar, generar_mensaje, construir_figura, generar_grafico, evaluar_alertas_2100, validar_corte_2100
from auditoria_reportes import AuditoriaReportes, ConflictoInstantanea
from agente_reportabilidad import ejecutar_reporte, ErrorReporte

C=datetime(2025,3,6,21,tzinfo=ZoneInfo('America/Santiago'))

def make_snapshot(tickets=(),corte=C):
    return crear_instantanea('fuente-test',corte,C+timedelta(minutes=1),tickets)

def ticket(id='X',tipo='Incident',componente='Componente dinámico',estado='Work in Progress'):
    return TicketOperacional(id,tipo,componente,estado,'Original; referencia Y.  Texto sin modificar.',C-timedelta(days=1),C-timedelta(minutes=5))

@pytest.mark.parametrize('estado',['Cerrado','Abierto','Pendiente','Cancelado','Work in Progress'])
def test_regla_2100_solo_wip(estado):
    snap=make_snapshot([ticket(estado=estado)])
    resumen=agregar(snap)
    alerts=evaluar_alertas_2100(resumen)
    assert len(alerts)==(estado=='Work in Progress')
    assert snap.tickets[0].estado==estado
    if alerts: assert alerts[0]['codigo_regla']=='WIP_EN_RESUMEN_2100'

def test_conteos_por_componente_y_tipo_sin_lista_fija():
    r=agregar(make_snapshot([ticket('1'),ticket('2',tipo='Service Request'),ticket('3',componente='Nuevo componente no codificado',estado='Pendiente'),ticket('4',estado='Cancelado')]))
    assert r.componentes==( ('Componente dinámico',1,1),('Nuevo componente no codificado',1,0))
    assert r.activos==3
    assert dict((e,(i,s)) for e,i,s in r.estados)['Work in Progress']==(1,1)

def test_mensaje_se_calcula_no_tiene_cifras_historicas_fijas():
    r=agregar(make_snapshot([ticket('1',estado='Pendiente'),ticket('2',tipo='Service Request',estado='Abierto')]))
    msg=generar_mensaje(r)
    assert 'Resumen de incidentes:\nPendientes: 1\nAbiertos: 0\nWork in Progress: 0' in msg
    assert 'Resumen de requerimientos:\nPendientes: 0\nAbiertos: 1\nWork in Progress: 0' in msg
    assert 'No se detectan tickets Work in Progress' in msg

@pytest.mark.parametrize('estado',['En progreso','En proceso','WIP','WORK_IN_PROGRESS'])
def test_alias_historicos_sin_cambiar_literal(estado):
    r=agregar(make_snapshot([ticket(estado=estado)]))
    assert evaluar_alertas_2100(r)[0]['estado_observado']==estado

@pytest.mark.parametrize('estado',['Resuelto','Escalado'])
def test_compatibilidad_historica_no_inventa_activos(estado):
    r=agregar(make_snapshot([ticket(estado=estado)]))
    assert r.activos==0 and not r.wip

def test_datos_desconocidos_no_generan_ceros_falsos():
    with pytest.raises(ValueError): agregar(make_snapshot([ticket(estado='Inexistente')]))
    with pytest.raises(ValueError): agregar(make_snapshot([ticket(tipo='Otro')]))

def test_sin_tickets_activos_grafico_valido(tmp_path):
    from PIL import Image
    r=agregar(make_snapshot([ticket(estado='Cerrado'),ticket('2',estado='Cancelado')]))
    p=tmp_path/'vacio.png'; generar_grafico(r,p)
    with Image.open(p) as im:
        im.verify()
    assert p.stat().st_size>1000 and r.activos==0

def test_figura_y_mensaje_comparten_matriz_exacta():
    import matplotlib.pyplot as plt
    r=agregar(make_snapshot([ticket(),ticket('2',tipo='Service Request',estado='Pendiente')]))
    fig=construir_figura(r)
    try:
        assert len(fig.axes)==2
        assert list(fig.axes[0].containers[0].datavalues)==[v[1] for v in r.componentes]
        assert list(fig.axes[0].containers[1].datavalues)==[v[2] for v in r.componentes]
        assert list(fig.axes[1].containers[0].datavalues)==[v[1] for v in r.estados]
        assert list(fig.axes[1].containers[1].datavalues)==[v[2] for v in r.estados]
        assert fig.axes[1].get_xticklabels()[2].get_color()=='#bd1f2d'
        assert 'Work in Progress: 1' in generar_mensaje(r)
    finally: plt.close(fig)

@pytest.mark.parametrize('fecha',[datetime(2025,3,6,21),C.replace(hour=5,minute=30),C.replace(second=1)])
def test_rechaza_corte_incorrecto(fecha):
    with pytest.raises(ValueError): validar_corte_2100(fecha)

@pytest.mark.parametrize('local',[C,datetime(2025,6,6,21,tzinfo=ZoneInfo('America/Santiago'))])
def test_zona_y_offsets_equivalentes(local):
    assert validar_corte_2100(local.astimezone(timezone.utc))==local

def test_no_usa_db_etl_ni_credenciales_por_defecto(monkeypatch):
    for key in ('OP_DB_HOST','OP_DB_PORT','OP_DB_NAME','OP_DB_USER','OP_DB_PASSWORD'): monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv('DB_NAME','Galaxy_mina')
    with pytest.raises(ValueError,match='OP_DB_PASSWORD'): motor_desde_entorno()

def test_hash_no_depende_hora_observacion():
    a=make_snapshot([ticket()])
    b=crear_instantanea(a.fuente,a.corte,a.observada_en+timedelta(hours=1),a.tickets)
    assert a.hash_contenido==b.hash_contenido

def test_evidencia_local_idempotente_y_cortes_independientes(tmp_path):
    store=AuditoriaReportes(tmp_path/'audit.sqlite3')
    r=agregar(make_snapshot([ticket()]))
    for id in ('uno','dos'):
        store.iniciar(id,r.instantanea.fuente,C); store.observar(id,r)
    assert len(store.evidencias())==1
    assert store.evidencias()[0]['primera_ejecucion']=='uno'
    r2=agregar(make_snapshot([ticket()],C+timedelta(days=1)))
    store.iniciar('tres',r2.instantanea.fuente,r2.instantanea.corte); store.observar('tres',r2)
    assert len(store.evidencias())==2

def test_corte_contradictorio_no_reemplaza_evidencia(tmp_path):
    store=AuditoriaReportes(tmp_path/'audit.sqlite3')
    a=agregar(make_snapshot([ticket()])); b=agregar(make_snapshot([ticket(estado='Cerrado')]))
    store.iniciar('a','fuente-test',C); store.observar('a',a)
    store.iniciar('b','fuente-test',C)
    with pytest.raises(ConflictoInstantanea): store.observar('b',b)
    assert store.evidencias()[0]['estado_observado']=='Work in Progress'

def test_consulta_fallida_no_publica_informe_y_luego_recupera(tmp_path):
    audit=tmp_path/'audit.sqlite3'; output=tmp_path/'out'
    with patch('agente_reportabilidad.leer_instantanea',side_effect=RuntimeError('password=NO_PUBLICAR')):
        with pytest.raises(ErrorReporte) as e: ejecutar_reporte(corte=C,fuente='fuente-test',auditoria=audit,salida=output,engine=object())
    row=AuditoriaReportes(audit).ejecucion(e.value.ejecucion_id)
    assert row['estado']=='FALLIDO' and row['tickets_leidos'] is None and row['conteos_json'] is None
    assert 'NO_PUBLICAR' not in json.dumps(row)
    assert not output.exists()
    with patch('agente_reportabilidad.leer_instantanea',return_value=make_snapshot([ticket()])):
        good=ejecutar_reporte(corte=C,fuente='fuente-test',auditoria=audit,salida=output,engine=object())
    assert good['estado']=='COMPLETADO'

@pytest.mark.parametrize('funcion,codigo',[('generar_grafico','GRAFICO_FALLIDA'),('generar_mensaje','MENSAJE_FALLIDA')])
def test_error_generacion_auditable_no_publica_parciales(tmp_path,funcion,codigo):
    audit=tmp_path/'audit.sqlite3'; output=tmp_path/'out'
    with patch('agente_reportabilidad.leer_instantanea',return_value=make_snapshot([ticket()])),patch('agente_reportabilidad.'+funcion,side_effect=RuntimeError('fallo simulado')):
        with pytest.raises(ErrorReporte) as e: ejecutar_reporte(corte=C,fuente='fuente-test',auditoria=audit,salida=output,engine=object())
    store=AuditoriaReportes(audit); row=store.ejecucion(e.value.ejecucion_id)
    assert row['estado']=='FALLIDO' and row['error_codigo']==codigo
    assert row['tickets_leidos']==1 and row['directorio'] is None
    assert len(store.evidencias())==1  # La observación real no se borra por fallo de render.
    assert list(output.iterdir())==[]
