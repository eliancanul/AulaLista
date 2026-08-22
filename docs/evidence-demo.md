# T12 — Guion reproducible y evidencia técnica

Este documento describe una demostración técnica local de AulaLista. El
guion usa contenido sintético (`DemoPackage`) y una base SQLite temporal; no
crea ni conserva datos personales reales.

## Ejecutar la demostración

Desde la raíz del checkout:

```sh
.venv/bin/python scripts/run_evidence_demo.py
```

El script reutiliza `manage.py migrate`, Django Test Client y el mismo flujo
de cierre de T08. Produce:

- `evidence/t12/t12-evidence.json`, estados y métricas legibles por máquina.
- `evidence/t12/t12-evidence.html`, una vista equivalente a capturas.

La base de demostración se elimina al terminar. El script no usa ni modifica
`db.sqlite3`. El diagrama local está en
`docs/evidence/t12-network.mmd`.

## Secuencia que se demuestra

1. Instalación lógica: migración limpia sobre SQLite temporal.
2. Una persona con el rol `EditorialReviewer` aprueba el paquete sintético.
3. La aprobación publica el snapshot inmutable v1.
4. Se prepara y confirma una sesión fijada al snapshot v1.
5. Un cliente sintético responde y solicita una pista autorizada; la respuesta
   y la ayuda permanecen efímeras antes del cierre.
6. Se corrige el paquete y una nueva aprobación publica el snapshot v2.
7. La sesión existente conserva v1; v2 sólo queda disponible para sesiones
   nuevas.
8. Se completa el turno, se cierra explícitamente la sesión y se verifica que
   quedan resultados seudónimos, sin turnos ni asignaciones temporales.
9. Se verifica que la exportación de resultados sólo se ofrece después del
   cierre.
10. Se registra el acceso LAN con URL explícita, QR local y cero solicitudes
    WAN. La dirección `192.0.2.10` pertenece a TEST-NET y no se presenta como
    una prueba física.
11. Se repite la medición T10 con 30 clientes en secuencia controlada y se
    calcula p95 por operación (`start`, `activity`, `ready`).

## Evidencia, supuestos y límites

El reporte marca como `false` la prueba física con dos teléfonos y WAN
desconectada. Para una demostración en la LAN real, el operador debe configurar
`AULALISTA_LAN_URL`, iniciar `runserver 0.0.0.0:8000` o `scripts/run_wsgi.py`,
y completar el checklist manual de `docs/installation.md` con dos dispositivos.

T10 demuestra 30 clientes en una secuencia controlada, con cero pérdida de
resultados y p95 objetivo de 2,000 ms por operación. No demuestra 30 escritores
simultáneos: el límite conocido de SQLite en este MVP es la contención
`database table is locked`. `LocMemCache` también mantiene el alcance en un
solo proceso WSGI; no se afirma soporte multi-worker o multi-nodo.

## Qué está implementado y qué no

### Infraestructura implementada

- Wagtail con revisión humana, snapshots publicados inmutables y sesiones
  fijadas a un snapshot.
- Práctica determinista, ayuda autorizada y estado efímero antes del cierre.
- Cierre explícito con resultados seudónimos eliminables.
- Acceso LAN explícito, QR generado localmente, recursos estáticos locales,
  empaquetado y prueba WSGI de T10.

### Contenido de demostración

El paquete de fracciones, las respuestas, las pistas, el revisor y los
participantes usados por el script son sintéticos. No son una planeación
autorizada, un piloto ni una evaluación de estudiantes.

### Trabajo futuro

- Medición física con la MacBook, dos teléfonos, Wi-Fi real y WAN desconectada.
- Resolver o medir de nuevo la contención de escritores concurrentes antes de
  ampliar el despliegue o cambiar SQLite.
- Validación curricular por una docente real y cualquier estudio pedagógico
  posterior bajo su autorización.
- Endurecimiento operativo del nodo para un despliegue real.

No afirma impacto pedagógico, no constituye pilotaje con menores y no demuestra continuidad real durante emergencias.
