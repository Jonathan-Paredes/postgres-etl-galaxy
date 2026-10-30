"""Auditoría local separada del PostgreSQL de solo lectura."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from fuente_operacional import utc_iso
from reporte_operacional import evaluar_alertas_2100


class ConflictoInstantanea(ValueError):
    pass


class AuditoriaReportes:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.conectar() as conn:
            conn.executescript('''
            CREATE TABLE IF NOT EXISTS ejecuciones_reporte (
                ejecucion_id TEXT PRIMARY KEY, fuente TEXT NOT NULL, corte TEXT NOT NULL,
                inicio TEXT NOT NULL, fin TEXT, estado TEXT NOT NULL,
                tickets_leidos INTEGER, conteos_json TEXT, tickets_wip_json TEXT,
                hash_instantanea TEXT, resultado_grafico TEXT NOT NULL DEFAULT 'NO_GENERADO',
                resultado_mensaje TEXT NOT NULL DEFAULT 'NO_GENERADO',
                directorio TEXT, error_codigo TEXT
            );
            CREATE TABLE IF NOT EXISTS observaciones_corte (
                fuente TEXT NOT NULL, corte TEXT NOT NULL, hash_instantanea TEXT NOT NULL,
                primera_ejecucion TEXT NOT NULL REFERENCES ejecuciones_reporte(ejecucion_id),
                PRIMARY KEY(fuente,corte)
            );
            CREATE TABLE IF NOT EXISTS evidencias_alerta (
                alerta_id TEXT PRIMARY KEY, fuente TEXT NOT NULL, numero_ticket TEXT NOT NULL,
                codigo_regla TEXT NOT NULL, fecha_corte TEXT NOT NULL,
                estado_observado TEXT NOT NULL, fecha_observacion TEXT NOT NULL,
                primera_ejecucion TEXT NOT NULL REFERENCES ejecuciones_reporte(ejecucion_id),
                UNIQUE(fuente,numero_ticket,codigo_regla,fecha_corte)
            );
            ''')

    @contextmanager
    def conectar(self):
        conn=sqlite3.connect(self.path,timeout=15)
        conn.row_factory=sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            with conn: yield conn
        finally: conn.close()

    def iniciar(self,id,fuente,corte):
        with self.conectar() as conn:
            conn.execute('''INSERT INTO ejecuciones_reporte(ejecucion_id,fuente,corte,inicio,estado)
                            VALUES(?,?,?,?,'INICIADO')''',
                (id,fuente,utc_iso(corte),datetime.now(timezone.utc).isoformat()))

    def observar(self,id,resumen):
        datos=resumen.datos(); snapshot=resumen.instantanea
        corte=utc_iso(snapshot.corte)
        alertas=evaluar_alertas_2100(resumen)
        with self.conectar() as conn:
            conn.execute('BEGIN IMMEDIATE')
            prev=conn.execute('SELECT hash_instantanea FROM observaciones_corte WHERE fuente=? AND corte=?',
                              (snapshot.fuente,corte)).fetchone()
            if prev and prev[0]!=snapshot.hash_contenido:
                raise ConflictoInstantanea('Fuente contradictoria para un corte ya observado')
            conn.execute('INSERT OR IGNORE INTO observaciones_corte VALUES(?,?,?,?)',
                         (snapshot.fuente,corte,snapshot.hash_contenido,id))
            for alert in alertas:
                key=uuid.uuid5(uuid.NAMESPACE_URL,json.dumps([snapshot.fuente,alert['numero_ticket'],alert['codigo_regla'],corte]))
                conn.execute('''INSERT OR IGNORE INTO evidencias_alerta
                    VALUES(?,?,?,?,?,?,?,?)''',(str(key),snapshot.fuente,alert['numero_ticket'],
                    alert['codigo_regla'],corte,alert['estado_observado'],utc_iso(snapshot.observada_en),id))
            conn.execute('''UPDATE ejecuciones_reporte SET tickets_leidos=?,conteos_json=?,
                 tickets_wip_json=?,hash_instantanea=? WHERE ejecucion_id=?''',
                 (datos['leidos'],json.dumps(datos,ensure_ascii=False),json.dumps(datos['tickets_wip'],ensure_ascii=False),snapshot.hash_contenido,id))

    def registrar_lectura(self,id,snapshot):
        with self.conectar() as conn:
            conn.execute('UPDATE ejecuciones_reporte SET tickets_leidos=?,hash_instantanea=? WHERE ejecucion_id=?',
                         (len(snapshot.tickets),snapshot.hash_contenido,id))

    def completar(self,id,directorio):
        with self.conectar() as conn:
            conn.execute('''UPDATE ejecuciones_reporte SET fin=?,estado='COMPLETADO',
                resultado_grafico='OK',resultado_mensaje='OK',directorio=? WHERE ejecucion_id=?''',
                (datetime.now(timezone.utc).isoformat(),str(directorio),id))

    def fallar(self,id,codigo,grafico,mensaje):
        with self.conectar() as conn:
            conn.execute('''UPDATE ejecuciones_reporte SET fin=?,estado='FALLIDO',
                error_codigo=?,resultado_grafico=?,resultado_mensaje=?,directorio=NULL WHERE ejecucion_id=?''',
                (datetime.now(timezone.utc).isoformat(),codigo,grafico,mensaje,id))

    def ejecucion(self,id):
        with self.conectar() as conn:
            return dict(conn.execute('SELECT * FROM ejecuciones_reporte WHERE ejecucion_id=?',(id,)).fetchone())

    def evidencias(self):
        with self.conectar() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM evidencias_alerta ORDER BY fecha_corte,numero_ticket')]
