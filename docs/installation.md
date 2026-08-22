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

## Acceso LAN para una demostración

La dirección que se compartirá con teléfonos o computadoras se configura de
forma explícita antes de iniciar el nodo. Por ejemplo:

```sh
AULALISTA_LAN_URL=http://192.168.1.20:8000/student/ \
  python3.13 manage.py runserver 0.0.0.0:8000
```

Después, abre `http://192.168.1.20:8000/access/` en la MacBook para mostrar la
dirección en texto y su código QR. El QR se genera dentro de AulaLista y el CSS
se sirve desde `static/`; no hay CDN, servicio externo, DNS público ni consulta
WAN. Si no se configura `AULALISTA_LAN_URL`, la página muestra la instrucción
en lugar de inventar una IP. El operador debe verificar que la dirección
pertenezca a la LAN actual; AulaLista no detecta automáticamente interfaces ni
garantiza que una IP siga siendo la misma después de cambiar de red.

### Comprobación manual antes de una clase

Con la MacBook y al menos dos teléfonos conectados a la misma LAN, y con la
WAN desconectada, abre `/access/` en la MacBook. Comprueba que un teléfono
puede entrar mediante QR y que el otro puede entrar escribiendo la dirección
textual. Ambos deben llegar a AulaLista sin instalar una aplicación ni crear
una cuenta. Esta comprobación física complementa las pruebas automatizadas;
no se simula como una prueba de Internet.
