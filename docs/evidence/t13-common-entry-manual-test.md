# T13 · Entrada común y prueba manual con dos teléfonos

## Qué cubre esta prueba

Verificar que el tutor comparte **un único enlace** (o QR) de la sesión activa
y que dos navegadores independientes se incorporan por esa misma entrada,
manteniendo turnos y capacidades aislados, con la WAN desconectada.

## Alcance de escrituras concurrentes en SQLite

La incorporación automatizada usa clientes secuenciales deterministas
(`tests/test_t13_common_entry.py`). SQLite soporta **un escritor a la vez**;
el despliegue vigente es un solo proceso WSGI con WAL y `busy_timeout=5000`.
Una sonda de 30 escritores simultáneos ya se evaluó en T10 y reportó
`database table is locked` de forma intermitente: es una limitación
documentada, no una política de reintento oculta. No ampliar el despliegue
a múltiples procesos escritores sin cambiar este límite.

## Preparación

1. MacBook con AulaLista corriendo en LAN (`scripts/run_wsgi.py`).
2. `AULALISTA_LAN_URL` configurado con la dirección local explícita.
3. Dos teléfonos conectados a la misma red Wi-Fi local.
4. WAN desconectada (apagar la salida a Internet del router o desenchufar
   el módem; los teléfonos no deben tener datos móviles activos).

## Pasos

1. Publicar un snapshot desde Wagtail con una persona del grupo
   `EditorialReviewer` y preparar una sesión (p. ej. 4 estudiantes,
   2 dispositivos). Confirmarla.
2. En `/tutor/sessions/<id>/review/`, verificar que aparece la sección
   "Acceso común de dispositivos" con un enlace y un código QR.
3. Con el teléfono A, escanear el QR (o abrir el enlace). Debe llegar a la
   pantalla "Unirse a la actividad" sin escribir ningún identificador.
4. Pulsar "Incorporar este dispositivo" e iniciar un turno con un apodo.
5. Repetir con el teléfono B sobre el mismo QR. Ambos deben terminar en la
   misma interfaz de incorporación, cada uno con su fila local distinta.
6. Responder la actividad en ambos teléfonos y pulsar Listo.
7. Volver a abrir el enlace en el teléfono A: debe reincorporarse a **su**
   asignación anterior, no reclamar otra.
8. Cerrar la sesión desde la revisión del tutor y exportar resultados.

## Resultado esperado

- Un solo enlace sirve para todos los dispositivos; el tutor no copia UUIDs.
- Cada navegador conserva su propia cookie de capacidad y su turno.
- Nada depende de DNS público ni de la WAN.
- Si todos los dispositivos están ocupados, la entrada muestra
  "No hay dispositivos disponibles" en lugar de mezclar filas.

## Registro

- [ ] Fecha de ejecución:
- [ ] Ejecutada por:
- [ ] Resultado (enlace compartido OK / incorporación A / incorporación B /
      reincorporación A / cierre y exporte):
