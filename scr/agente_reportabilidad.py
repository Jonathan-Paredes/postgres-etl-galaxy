"""Agente determinista de reportabilidad 21:00. Sin LLM ni envíos."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import tempfile
import uuid
from fuente_operacional import leer_instantanea, motor_desde_entorno
from reporte_operacional import validar_corte_2100, agregar, generar_grafico, generar_mensaje
from auditoria_reportes import AuditoriaReportes, ConflictoInstantanea


class ErrorReporte(RuntimeError):
    def __init__(self,ejecucion_id,codigo):
        self.ejecucion_id=ejecucion_id; self.codigo=codigo
        super().__init__(f'Ejecución {ejecucion_id}: {codigo}')


def ejecutar_reporte(*,corte,fuente,auditoria,salida,engine=None):
    corte=validar_corte_2100(corte)
    # Etiqueta opaca: no persistir una URL/contraseña como nombre de fuente.
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',fuente): raise ValueError('Identificador de fuente inválido')
    id=str(uuid.uuid4())
    store=AuditoriaReportes(auditoria)
    store.iniciar(id,fuente,corte)
    root=Path(salida).resolve()
    final=root/id
    fase='CONSULTA'; grafico='NO_GENERADO'; mensaje='NO_GENERADO'
    propio=engine is None
    publicado=False
    try:
        if engine is None: engine=motor_desde_entorno()
        snapshot=leer_instantanea(engine,corte,fuente)
        store.registrar_lectura(id,snapshot)
        fase='DATOS'
        resumen=agregar(snapshot)
        fase='EVIDENCIA'
        store.observar(id,resumen)
        root.mkdir(parents=True,exist_ok=True)
        if final.exists(): raise FileExistsError('Directorio de ejecución ya existe')
        with tempfile.TemporaryDirectory(prefix='.tmp-reporte-',dir=root) as temp:
            work=Path(temp)
            fase='GRAFICO'; grafico='ERROR'
            generar_grafico(resumen,work/'reporte.png')
            grafico='OK'; fase='MENSAJE'; mensaje='ERROR'
            (work/'mensaje.txt').write_text(generar_mensaje(resumen),encoding='utf-8')
            mensaje='OK'; fase='PUBLICACION'
            (work/'datos_reporte.json').write_text(json.dumps(resumen.datos(),ensure_ascii=False,indent=2),encoding='utf-8')
            # Solo se publica el conjunto cuando están listos todos los artefactos.
            work.rename(final)
            publicado=True
        fase='AUDITORIA'
        store.completar(id,final)
        return {'ejecucion_id':id,'estado':'COMPLETADO','directorio':str(final),
                'datos':resumen.datos()}
    except Exception as exc:
        if publicado:
            # Eliminar solo el directorio UUID creado por esta ejecución.
            if final.resolve().parent!=root or final.name!=id or final.is_symlink():
                raise RuntimeError('Directorio de ejecución fuera del límite seguro') from None
            shutil.rmtree(final)
        codigo='CONFLICTO_INSTANTANEA' if isinstance(exc,ConflictoInstantanea) else fase+'_FALLIDA'
        store.fallar(id,codigo,grafico,mensaje)
        raise ErrorReporte(id,codigo) from None
    finally:
        if propio and engine is not None: engine.dispose()


def main():
    parser=argparse.ArgumentParser(description='Reporte operacional determinista al corte de 21:00 Santiago')
    parser.add_argument('--corte',required=True,help='ISO con offset, correspondiente a las 21:00 Santiago')
    parser.add_argument('--fuente-id',required=True,help='Etiqueta opaca sin URL ni credenciales')
    parser.add_argument('--auditoria',required=True,help='SQLite local separada del origen')
    parser.add_argument('--salida',required=True,help='Directorio para imagen, mensaje y datos')
    args=parser.parse_args()
    try:
        result=ejecutar_reporte(corte=datetime.fromisoformat(args.corte),fuente=args.fuente_id,
                               auditoria=args.auditoria,salida=args.salida)
    except ErrorReporte as exc:
        print(json.dumps({'ejecucion_id':exc.ejecucion_id,'estado':'FALLIDO','error_codigo':exc.codigo}))
        raise SystemExit(1)
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__': main()
