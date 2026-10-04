# AulaLista — estado de implementación

**Actualización:** 4 de octubre de 2026
**Alcance:** recorrido docente Django de PR159, todavía en borrador.

El checkpoint publicado `b610309d` tiene [CI del árbol exacto aprobada](https://github.com/eliancanul/AulaLista/actions/runs/37165066828): pruebas sintéticas declaradas, el recorrido actual en Chrome y regresiones conservadas de la interfaz anterior. No es una corrida del corpus privado ni una prueba del proveedor real.

- La entrada activa es Currícula y autoría → Importar planeación → Revisar planeación. `/sprint/` redirige a Django; Vue se conserva como implementación experimental fuera de ese recorrido.
- La revisión presenta una caja, conserva respuestas y borradores por turno, permite correcciones y limita a seis las preguntas generadas por un proveedor. La aprobación/publicación sigue siendo humana.
- El contexto conserva el dossier y el texto digital de cada página del PDF, con SHA y páginas físicas. No realiza OCR ni acredita comprensión semántica completa.
- Luna es la selección actual. Su ruta CLI aún no está integrada/validada; el aviso lo indica y no hay fallback automático. No se ha establecido el recorrido PDF real → Luna → preguntas útiles → guardado.
- El intento histórico de Gemini sigue con resultado y consumo desconocidos. Elegir Luna no lo borra, reetiqueta ni concilia.

Los detalles vigentes están en [revisión docente](teacher-review.md), [aceptación y operación](teacher-review-acceptance.md) e [instalación](installation.md). Una CI verde con proveedor simulado no hace que el algoritmo con Luna esté listo ni autoriza merge o despliegue.

## Registro histórico del 22 de agosto de 2026

Lo siguiente conserva el estado y las mediciones documentados entonces. Sus
conteos, afirmaciones de preparación y descripción sin LLM no describen el
checkpoint actual ni reemplazan las comprobaciones del recorrido docente.

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
- Recursos estáticos servidos desde `static/`, sin dependencias remotas; el
  QR se codifica localmente con Segno y se renderiza como SVG inline.
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

## Estado en vivo del asistente de autoría

La causa reproducida de la recarga aparente era un `meta refresh` cada dos
segundos en la página de espera, no una reconexión del modelo. La espera usa
ahora polling JSON incremental y JavaScript local: actualiza sólo estado y
contador, conserva resultados parciales y reintenta la consulta tras una
desconexión sin iniciar otra generación.

Los estados visibles son esperando, trabajando, parcial, terminado y error.
Cada etapa persiste `progress_started_at` y `progress_finished_at`; las pruebas
de generación exitosa e interrumpida verifican ambos extremos de la medición.
Un timeout libera el trabajo como error recuperable y deja la revisión humana
como autoridad: el asistente no aprueba ni publica.

## Flujo de aula

- El tutor prepara una `ClassroomSession` con distribución determinista entre
  dispositivos.
- Una confirmación explícita activa la sesión.
- `/student/` lista las sesiones activas y el tutor comparte un único
  enlace o QR (`/student/sessions/<id>/join/`); cada navegador reclama
  automáticamente su propia asignación de dispositivo mediante una cookie
  firmada, sin copiar identificadores manualmente.
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

La ruta `/access/` muestra una URL textual y un QR generado localmente. En una
sesión activa, revisión, modo activo y proyección muestran el mismo enlace
completo `/student/sessions/<id>/join/`. Segno codifica directamente esa URL
con corrección de errores M y una zona blanca de cuatro módulos; no hay CDN,
WAN ni servicio externo.

La base se configura explícitamente con `AULALISTA_LAN_URL` (origen o base
`/student/`); la aplicación no inventa una IP ni detecta interfaces
automáticamente. La URL textual siempre queda visible como alternativa. Si
falta o es inválida la configuración, se muestra el host actual sólo como
enlace manual y un aviso; no se genera un QR que pudiera apuntar a
`localhost`.

Ejemplo:

```sh
AULALISTA_LAN_URL=http://192.168.1.20:8000/student/ \
  python3.13 manage.py runserver 0.0.0.0:8000
```

La verificación automatizada bloquea DNS, sockets externos y `urlopen` durante
la demostración sintética. La prueba física con dos teléfonos y WAN
desconectada aún debe realizarse en la LAN real; la guía está en
`docs/qr-lan-test.md`.

## Robustez y evidencia

- Suite actual: 238 pruebas.
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
