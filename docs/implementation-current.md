# AulaLista — implementación actual

**Estado:** MVP técnico local listo para revisión con una docente
**Fecha:** 22 de agosto de 2026
**Rama:** `main`
**Último commit:** `d4fcb99`

## Propósito y límites

AulaLista es un nodo educativo local para ejecutar una actividad sin depender
de la WAN. La implementación actual es server-rendered con Django y Wagtail;
no usa SPA, LLM, embeddings, RAG, CDN, DNS público ni cuentas estudiantiles.

El contenido usado en las pruebas es `DemoPackage` sintético. No representa
una planeación aprobada, un piloto con menores, impacto pedagógico ni
continuidad real durante una emergencia.

## Stack y despliegue

- Python 3.13, Django 5.2, Wagtail 7.4 y SQLite.
- SQLite usa WAL, `synchronous=NORMAL` y `busy_timeout=5000`.
- Caché local `LocMemCache`; el alcance actual es un solo proceso WSGI.
- Recursos estáticos servidos desde `static/`, sin dependencias remotas.
- WSGI reproducible en `scripts/run_wsgi.py`.
- Verificación de paquete en `scripts/verify_local_package.py`.
- Empaquetado para MacBook Air en `scripts/package_macos.sh`.
- Instalación fijada con hashes en `requirements.lock`.

## Flujo editorial

1. Una persona del grupo `EditorialReviewer` crea un `CurriculumPackage` en
   Wagtail.
2. La validación estructural informa faltantes, pero no autoriza publicación.
3. La revisión aprobada por una persona publica un
   `PublishedPackageSnapshot` inmutable y versionado.
4. El snapshot normaliza el `StreamField` de Wagtail a la estructura que usa
   la actividad: microlección, reactivos, opciones, respuestas esperadas,
   retroalimentación, pistas y explicación final.
5. Una corrección genera otro snapshot; no modifica los snapshots anteriores.

## Flujo de aula

- El tutor prepara una `ClassroomSession` con distribución determinista entre
  dispositivos.
- Una confirmación explícita activa la sesión.
- Cada dispositivo recibe un identificador local opaco.
- Un `StudentTurn` temporal reserva capacidad y usa un apodo local.
- La respuesta se evalúa con reglas deterministas; la ayuda autorizada no
  modifica por sí misma la puntuación.
- Las respuestas, ayudas y errores técnicos permanecen efímeros hasta el
  cierre.
- Al cerrar, se eliminan turnos, asignaciones y cachés temporales.
- Se conservan `PseudonymousResult` eliminables, sin relaciones con nombre,
  dispositivo o intento.

## Acceso LAN

La ruta `/access/` muestra una URL textual y un QR generado localmente. La URL
se configura explícitamente con `AULALISTA_LAN_URL`; la aplicación no inventa
una IP ni detecta interfaces automáticamente. Si el QR falla, la dirección
textual sigue disponible.

Ejemplo:

```sh
AULALISTA_LAN_URL=http://192.168.1.20:8000/student/ \
  python3.13 manage.py runserver 0.0.0.0:8000
```

La verificación automatizada bloquea DNS, sockets externos y `urlopen` durante
la demostración sintética. La prueba física con dos teléfonos y WAN
desconectada aún debe realizarse en la LAN real.

## Robustez y evidencia

- Suite actual: 98 pruebas.
- T10: 30 clientes simulados en secuencia controlada, 90 operaciones, cero
  errores, cero pérdida de datos y p95 por operación menor a 2 segundos en la
  máquina de prueba.
- La medición exploratoria de escritores simultáneos encontró
  `database table is locked`; no se oculta ni se presenta como concurrencia
  soportada.
- T12 genera JSON y HTML con el flujo aprobación → snapshot 1 → sesión →
  respuesta/ayuda → snapshot 2 → cierre, además de métricas y límites.
- El diagrama de red está en `docs/evidence/t12-network.mmd`.

Para repetir la demostración:

```sh
.venv/bin/python scripts/run_evidence_demo.py
```

## Verificación local

```sh
.venv/bin/pytest -q
.venv/bin/python manage.py check
.venv/bin/python manage.py migrate --check
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python scripts/verify_local_package.py
```

## Pendientes antes de una validación real

- Encontrar una docente y sustituir el `DemoPackage` por contenido revisado.
- Ejecutar la demostración física con la MacBook Air, dos teléfonos, LAN real
  y WAN desconectada.
- Medir nuevamente la concurrencia de escritores antes de ampliar el número
  de procesos o nodos.
- Revisar operación, seguridad y endurecimiento antes de cualquier despliegue
  institucional.
