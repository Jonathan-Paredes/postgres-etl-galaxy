"""Levanta PostgreSQL descartable y ejecuta pytest. Nunca lee .env ni usa Galaxy.

Predeterminado: Docker. Alternativa: --postgres-bin /ruta/a/bin (ZIP oficial).
"""
import argparse
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def run(args,**kw):
    return subprocess.run([str(a) for a in args],check=True,**kw)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--postgres-bin',type=Path)
    options=parser.parse_args()
    password=secrets.token_hex(24)
    name='etl-test-'+uuid.uuid4().hex
    env=os.environ.copy()
    # Credenciales de negocio heredadas no intervienen en las pruebas.
    for key in list(env):
        if key.startswith('DB_') or key in ('PGHOST','PGPORT','PGDATABASE','PGUSER','PGPASSWORD','TEST_PG_URL'):
            env.pop(key,None)
    env['LOG_TO_FILE']='0'
    env['PYTHONDONTWRITEBYTECODE']='1'
    started=False
    with tempfile.TemporaryDirectory(prefix='etl-pg-') as tmp:
        data=Path(tmp)/'data'
        try:
            if options.postgres_bin:
                bin=options.postgres_bin.resolve()
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
                pwfile=Path(tmp)/'password'
                pwfile.write_text(password,encoding='utf-8')
                hidden={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
                run([bin/'initdb','-D',data,'-U','etl_test','--pwfile',pwfile,'-A','scram-sha-256','--encoding=UTF8','--locale=C'],env=env,**hidden)
                run([bin/'pg_ctl','-D',data,'-l',Path(tmp)/'postgres.log','-o',f'-h 127.0.0.1 -p {port}','-w','start'],env=env,**hidden)
                started=True
                env['PGPASSWORD']=password
                run([bin/'createdb','-h','127.0.0.1','-p',str(port),'-U','etl_test','etl_test_control'],env=env,**hidden)
            else:
                env['POSTGRES_PASSWORD']=password
                run(['docker','run','--rm','-d','--name',name,'--label','purpose=etl-disposable-test','-e','POSTGRES_PASSWORD','-e','POSTGRES_USER=etl_test','-e','POSTGRES_DB=etl_test_control','-p','127.0.0.1::5432','postgres:17'],env=env,stdout=subprocess.DEVNULL)
                started=True
                port=int(subprocess.check_output(['docker','inspect','-f','{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}',name],text=True).strip())
            import psycopg2
            for attempt in range(60):
                try:
                    c=psycopg2.connect(host='127.0.0.1',port=port,dbname='etl_test_control',user='etl_test',password=password,connect_timeout=1)
                    c.close(); break
                except psycopg2.OperationalError:
                    if attempt==59: raise
                    time.sleep(0.5)
            env['TEST_PG_URL']=f'postgresql+psycopg2://etl_test:{password}@127.0.0.1:{port}/etl_test_control'
            results=ROOT/'test-results'
            results.mkdir(exist_ok=True)
            return subprocess.run([sys.executable,'-m','pytest','-v','--junitxml',str(results/'junit.xml')],cwd=ROOT,env=env).returncode
        finally:
            if started:
                if options.postgres_bin:
                    run([bin/'pg_ctl','-D',data,'-m','fast','-w','stop'],env=env,**hidden)
                else:
                    run(['docker','stop',name],stdout=subprocess.DEVNULL)

if __name__=='__main__':
    raise SystemExit(main())
