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

## SQLite y límites medidos

La configuración de producción local activa explícitamente SQLite WAL,
`synchronous=NORMAL` y un `busy_timeout` finito de 5 segundos. WAL permite que
los lectores continúen mientras SQLite serializa las escrituras; no convierte
SQLite en una base de datos multi-nodo ni elimina la contención entre
escritores. El caché de AulaLista sigue siendo `LocMemCache`, por lo que el
MVP se mantiene en un solo proceso WSGI.

La prueba T10 usa 30 clientes Django en una secuencia controlada, registra
latencia por operación, errores y pérdida de datos, y exige estos objetivos
locales:

- 30 inicios, 30 lecturas de actividad y 30 cierres de turno sin errores HTTP o
  `database is locked`.
- cero resultados perdidos después de cerrar la sesión.
- transición `active` → turnos completados → `closed`, con 30 resultados
  seudónimos.
- percentil 95 de cada operación menor o igual a 2,000 ms en la máquina donde
  se ejecuta la prueba.

Una medición exploratoria separada con 30 escritores Django simultáneos en este
checkout produjo `database table is locked`; no se reintenta ni se presenta
como concurrencia soportada. La secuencia controlada es el alcance reproducible
aceptado para este MVP y el límite de escritores concurrentes queda abierto
para una futura medición o cambio de base de datos.

La prueba no es una medición física de teléfonos, Wi-Fi o WAN. Si el entorno
de prueba usa una base SQLite en memoria, SQLite reporta `journal_mode=memory`
porque WAL requiere un archivo; la prueba lo deja visible y comprueba que el
`busy_timeout` sigue siendo 5,000 ms. Una base de archivo sí debe reportar
`journal_mode=wal`. No se cambia de base de datos sin una medición que incumpla
estos objetivos.

Ejecuta la medición reproducible con:

```sh
.venv/bin/python -m pytest -q tests/test_t10_robustness.py
```

## Comprobación del nodo

```sh
python3.13 -m pytest -q
python3.13 manage.py check
python3.13 manage.py migrate --noinput
python3.13 scripts/verify_local_package.py
```

`verify_local_package.py` ejecuta `collectstatic --noinput` y sirve `/student/`
mediante un socket WSGI de loopback. Su resultado JSON indica el estado de
ambos pasos y termina con código distinto de cero si alguno falla.

## Empaquetado reproducible para MacBook Air

Desde la raíz del checkout, crea un paquete sin la base de desarrollo, sus
sidecars WAL/SHM, el entorno virtual, Git ni los estáticos generados:

```sh
sh scripts/package_macos.sh
```

El archivo queda en `dist/aulalista-local.tar.gz`. En una MacBook Air limpia:

```sh
tar -xzf aulalista-local.tar.gz
cd AulaLista
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --require-hashes -r requirements.lock
python manage.py migrate --noinput
python scripts/verify_local_package.py
```

Para abrir la página de salud desde la red local, inicia el servidor en todas
las interfaces de desarrollo:

```sh
python3.13 manage.py runserver 0.0.0.0:8000
```

Para comprobar la misma aplicación mediante el servidor WSGI local de la
biblioteca estándar:

```sh
python3.13 scripts/run_wsgi.py --host 0.0.0.0 --port 8000
```

Este servidor WSGI reproducible es para el nodo local y la demostración; no
se presenta como un despliegue multi-worker medido ni como sustituto de un
servidor de producción endurecido.

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
