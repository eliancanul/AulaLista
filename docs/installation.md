# Instalación local de AulaLista

T01 usa Python 3.13, Django 5.2, Wagtail 7.4, SQLite y recursos estáticos
locales. La base `db.sqlite3` es desechable para desarrollo y no se versiona.

## Instalación limpia reproducible

Ejecuta estos comandos desde la raíz del checkout en una máquina que tenga
Python 3.13:

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --require-hashes -r requirements.lock
```

`requirements.lock` contiene las dependencias directas y transitivas de
`requirements-dev.txt`, con versión y hash para cada distribución. El archivo
es consumible directamente por pip; la herramienta usada para generarlo no es
necesaria en la máquina que instala AulaLista.

La ruta crítica incluye `static/health/font.css`, que se sirve desde el nodo y
declara únicamente fuentes instaladas en el sistema mediante `local(...)`. El
navegador no descarga una fuente remota ni depende de una licencia de fuente
embebida por T01.

## Comprobación del nodo

```sh
python3.13 -m pytest -q
python3.13 manage.py check
python3.13 manage.py migrate --noinput
```

Para abrir la página de salud desde la red local, inicia el servidor en todas
las interfaces de desarrollo:

```sh
python3.13 manage.py runserver 0.0.0.0:8000
```

Desde otro dispositivo de la misma red, abre
`http://DIRECCION_LOCAL_DEL_NODO:8000/health/`. La configuración local acepta
los hosts de la LAN; el endurecimiento para un despliegue real queda fuera de
T01.
