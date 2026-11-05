"""Arranca Cuenta Clara y abre su interfaz en el navegador predeterminado."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler
import webbrowser

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8000'
HTTP = build_opener(ProxyHandler({}))


def running():
    try:
        with HTTP.open(URL + '/api/health', timeout=1) as response:
            return json.load(response).get('app') == 'cuenta-clara'
    except Exception:
        return False


def main():
    (ROOT / 'data').mkdir(exist_ok=True)
    if running():
        webbrowser.open(URL)
        print('Cuenta Clara ya está funcionando. Abriendo el navegador.')
        return
    env = os.environ.copy()
    env['PORT'] = '8000'
    log = open(ROOT / 'data' / 'servidor.log', 'a', encoding='utf-8')
    process = subprocess.Popen([sys.executable, '-u', str(ROOT / 'server.py')], cwd=ROOT, env=env, stdout=log, stderr=log)
    try:
        for _ in range(40):
            if process.poll() is not None:
                raise RuntimeError('No se pudo iniciar el servidor. Consulta data/servidor.log; el puerto 8000 puede estar ocupado.')
            if running():
                webbrowser.open(URL)
                print('Cuenta Clara abierta en ' + URL)
                print('Mantén esta ventana abierta. Pulsa Ctrl+C para detener el servidor.')
                process.wait()
                return
            time.sleep(0.25)
        raise RuntimeError('El servidor no respondió. Consulta data/servidor.log y comprueba el acceso a 127.0.0.1:8000.')
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()
        log.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nServidor detenido.')
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
