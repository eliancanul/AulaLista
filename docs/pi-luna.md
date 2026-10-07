# GPT-6 Luna mediante Pi, ruta opt-in

Estado: `pi_luna` es la selección predeterminada de esta etapa de pruebas locales, con LIVE=0 y
contexto `complete`. Las pruebas de esta integración usan procesos y respuestas
inventados: **no acreditan una consulta real ni habilitan inferencia.** La
selección explícita `luna` conserva la ruta Codex anterior, sin fallback.

AulaLista se construye como SaaS conectado con IA. El launcher y su perfil OFF
pertenecen únicamente a esta ruta local de pruebas; no son requisitos de la
API futura ni una prohibición general de red. La prioridad actual es probar
Luna localmente; la integración API de producción se hará después.

## Contrato fijado

- Node `22.22.3`; `@earendil-works/pi-coding-agent` y `@earendil-works/pi-ai`
  **0.84.4**. Cambiar de versión exige otra revisión y pruebas del contrato.
- Proveedor `openai-codex`, modelo exacto `gpt-6-luna`, esfuerzo `high`, API
  `openai-codex-responses`, endpoint `https://chatgpt.com/backend-api/codex/responses`.
- El modelo tiene que existir en el catálogo local revisado. No se fabrica una
  entrada ni se sustituye por GPT-5.6, GPT-6.1 Sol o un alias «6.1 Luna».
- El helper Node utiliza `ModelRuntime.streamSimple` de Pi. No instancia el
  agente de programación, herramientas, extensiones, descubrimiento de recursos,
  sesiones, configuración global, compactación ni un bucle de reintentos.
- Una solicitud de texto mediante stdin; sin prompt en argumentos. SSE, un solo
  POST local, redirecciones rechazadas, `tools: []`, `toolChoice: none` y
  `maxRetries: 0`. La solicitud verifica modelo y esfuerzo antes del envío.

## Autenticación e aislamiento

Pi administra su autenticación existente dentro del mismo proceso. Su clase
`ReadOnlyAuthStorage` se importa desde un módulo interno fijado a 0.84.4. AulaLista
no abre, exporta, copia ni imprime credenciales. No hay login ni autorización
OAuth nueva. Si Pi necesita renovar su token, el almacenamiento de sólo lectura
rechaza la operación antes del callback de refresh; se requiere intervención de
la persona operadora fuera de AulaLista. Un `auth check` exitoso no prueba que
el token tenga vigencia suficiente ni que el modelo responda. En Pi 0.84.4,
`auth check --no-refresh` sólo comprueba que hay OAuth configurado; puede decir
`ready` con un token caducado. `getAuth`, usado por el helper antes de admitir
texto, exige más de cinco minutos de vigencia y falla cerrado si necesita
renovación. No se reduce ese margen ni se habilita refresh como recuperación.

**Pi no tiene sandbox integrado.** El adaptador exige un lanzador de aislamiento
externo revisado; nunca invoca Node directamente como alternativa. Ese lanzador
debe aceptar `--work RUTA -- COMANDO ARGUMENTOS` y conservar las restricciones
aprobadas del entorno. Este cambio no instala ni proporciona un lanzador, no
concede lecturas nuevas y no modifica permisos o perfiles del sistema.

El lanzador debe conservar explícitamente `PI_OFFLINE=1` y `PI_TELEMETRY=0`
al crear el proceso Node. Un perfil `inherit=none` que sólo conserva `PATH` y
`HOME` elimina estos flags aunque el supervisor los haya enviado. El helper lo
rechaza como `invocation / invalid_invocation` antes de cargar el runtime o la
autenticación. La corrección es permitir esos dos valores restrictivos en el
entorno del hijo, manteniendo intactos los límites de archivos, red y escritura;
no quitar el guard ni heredar todo el entorno. Comprobar el preflight dentro del
mismo lanzador revisado antes de admitir otra consulta.


Cada intento comprueba identidad y canarios sintéticos: `/usr/bin/true`, lectura
permitida de un archivo propio, lectura denegada de otro fuera del directorio y
escritura denegada. Después comprueba Node y hace un preflight de Pi sin inferencia.
Estos canarios no demuestran por sí solos el aislamiento de red, todas las rutas,
todo descendiente o toda la cadena de dependencias. La revisión externa debe
cubrir esas superficies y las rutas mínimas de runtime, catálogo y autenticación
que sean necesarias; no se amplían automáticamente tras un fallo.

## Configuración

Las siguientes variables contienen rutas no secretas, canónicas y absolutas:

- `AULALISTA_TEACHER_REVIEW_PROVIDER=pi_luna`
- `AULALISTA_PI_NODE_EXECUTABLE`: Node real revisado
- `AULALISTA_PI_PACKAGE_DIR`: raíz del paquete Pi instalado
- `AULALISTA_PI_AGENT_DIR`: directorio original de Pi que ya administra su sesión
- `AULALISTA_PI_CATALOG_FILE`: `models-store.json` original revisado, sólo lectura
- `AULALISTA_PI_ISOLATION_LAUNCHER`: lanzador externo revisado
- `AULALISTA_PI_RUNTIME_REVIEW`: manifiesto privado de revisión real
- `AULALISTA_PI_ATTEMPT_DIR`: directorio privado para intentos, fuera de estáticos/media
- `AULALISTA_PI_LIVE_ENABLED=0`
- `AULALISTA_PI_TIMEOUT_SECONDS=30` (entre 1 y 120)

La aplicación rechaza overrides de API key, endpoint, Node y proxy por presencia,
sin leer sus valores ni eliminarlos. El proceso recibe un entorno mínimo explícito
y `PI_OFFLINE=1`, que impide actividad automática de catálogos/actualizaciones.
El helper no carga `models.json`; usa únicamente el catálogo local revisado.

El manifiesto `aulalista.pi-external-review.v1` registra UUID, fecha con zona,
hash de evidencia real, `contract_sha256`, huellas de runtime/catálogo/helper,
`isolation=reviewed_external_boundary_no_unrestricted_fallback` y `limitations`
exactas. Su esquema se comprueba en `PiLunaProvider._identity`. No se incluye un
manifiesto de producción ni un generador de aprobaciones: los fixtures son
inventados y nunca sirven como evidencia de revisión. El hash del manifiesto es
referencia a la revisión, no atestación física del sistema.

Habilitar consultas requiere primero aislamiento compatible verificado, runtime
y credencial utilizables, y autorización para el intento/datos/destino. El primer
ensayo será sintético. Autorizar ese ensayo no autoriza documentos privados ni
datos de menores. Una página GET nunca inicia el proveedor.

## Recibos y límites

Una admisión durable precede al proceso de generación. Tiempo local máximo 120 s,
entrada completa hasta 4 MiB, stdout/stderr combinados hasta 128 KiB, respuesta
final hasta 32 KiB y cuerpo de respuesta HTTP hasta 256 KiB. No se recorta contexto.
El preflight tiene seis procesos de hasta 5 s cada uno, separado de la generación.

El sobre `aulalista.pi-text.v1` es propio: `pi.request`, `pi.start`, `pi.result`,
`pi.completed`. **No es el JSONL de la CLI** y no depende de `agent_end` ni
`agent_settled`. Sólo se acepta `stopReason=stop`, contenido de texto/pensamiento
sin herramientas, un resultado terminal y el JSON exacto de revisión docente.
Toda otra respuesta, error, truncamiento o contabilidad incompleta detiene el
intento. Las respuestas humanas conservan su autoridad y nunca se aprueba o
publica automáticamente la planeación.

Se guardan las métricas Pi originales: `input` excluye caché, `cacheRead` y
`cacheWrite` son cantidades aparte; `output` ya incluye `reasoning`. La ausencia
del desglose de razonamiento queda `null`. Los ceros inicializados por Pi no se
aceptan como prueba de consumo terminal de una solicitud con texto. `cost` no es
un comprobante de cobro y no se presenta como cargo real. `model` identifica el
modelo solicitado; `observed_model` sólo usa `responseModel` cuando Pi lo reporta.
El recibo etiqueta `usage_source=pi_normalized_terminal_usage`: Pi puede normalizar
detalles ausentes de caché/razonamiento a cero, por lo que un cero no acredita
que el backend haya declarado explícitamente esa cantidad.

Esta versión no transmite un tope de tokens a Codex aunque exista una opción
genérica `maxTokens`. Cancelar el proceso no demuestra que terminó el trabajo
remoto ni elimina un posible cargo. `cacheRetention=none` evita la clave local
de sesión, pero no garantiza ausencia de caché del servidor. Los contadores de
POST son locales, no una auditoría del trabajo interno del backend.

Un intento interrumpido, una admisión sin recibo, un lock pendiente o
`STOP_REQUIRED.json` impiden el relanzamiento automático. La recuperación exige
revisión explícita; nunca se borra el bloqueo para «probar otra vez».

## Diagnóstico de preparación

El helper emite fallos únicamente por stderr como un objeto `pi.error` con
`stage` y `code` fijos. No copia mensajes, nombres, stacks, causas, propiedades de
credenciales ni cuerpos del proveedor. Las etapas separan manifiestos, imports,
lectura/restauración de catálogo, contrato de modelo, `auth_check`,
`auth_resolution`, lectura de entrada y `provider_stream`. Si falla el preflight, Python conserva
sólo ese objeto validado contra una lista cerrada en `preflight.json`; no guarda
stderr arbitrario ni admite el prompt. Se mantiene el código exterior
`pi_runtime_preflight_failed`.

- `auth_check` localiza un fallo de detección/lectura de OAuth.
- `auth_resolution` localiza un fallo al obtener autenticación utilizable; por sí
  solo no prueba expiración. Hay que distinguirlo de un error de lectura u otra
  causa mediante una revisión local autorizada, sin imprimir secretos.
- `provider_stream` puede fallar antes de `pi.request`, por ejemplo durante la
  preparación del proveedor. No haber observado ese evento sólo significa que
  no se observó el hook local; no certifica consumo cero ni ausencia remota.
- `pi_catalog_refresh_failed` conserva el bloqueo cuando Pi devuelve errores en
  `refresh()` en vez de lanzarlos. Nunca se continúa con el catálogo incorporado
  como sustituto de una restauración fallida.

El catálogo revisado debe contener una sola entrada con la identidad exacta del
modelo. Sus lecturas entregan copias; una mutación en memoria no cambia la base
revisada. Esta validación y el diagnóstico no amplían permisos ni cambian el
contrato de envío. Cambiar el helper cambia su hash y exige revisar de nuevo el
manifiesto externo antes de cualquier intento real. Los bloqueos de un intento
anterior se conservan.

## Verificación offline

```sh
python -m pytest -q tests/test_teacher_review_pi.py tests/test_teacher_review_luna_cli.py
python -m pytest -q tests/test_teacher_review_pi_http.py tests/test_teacher_review_pi_receipts.py
node --test tests/test_pi_review_driver.mjs
```

Los tests Node sustituyen fetch y Pi con fixtures locales; no usan credenciales
ni red. Son pruebas del helper y el protocolo, no del paquete real del Mac.

La aceptación HTTP sube un PDF generado, recorre el selector de producto, el
adaptador, el supervisor de subproceso, el driver real y el parser de eventos.
Sustituye explícitamente el preflight por una preparación de test y usa un
paquete Pi, autenticación y fetch enteramente inventados. Registra la versión
real de Node del entorno de pruebas; no la hace pasar por Node 22.22.3 ni
modifica ese contrato de producción. La prueba independiente de preflight
sigue rechazando Node 24. Esta costura OFF comprueba una sola ejecución por
envío, recibos, recarga, doble POST, borrador durable y respuesta guardada al
deshabilitar el proveedor, además de rechazo/timeout sin relanzamiento. No
acredita aislamiento del Mac ni calidad de Luna.

Los contadores válidos de un resultado de identidad correcta se conservan
aunque la respuesta sea rechazada antes del final limpio. En tal caso,
`reported_usage` no convierte `accounting_status=unknown` en completo ni retira
el bloqueo. Si falla la grabación posterior al recibo validado, el evento Django
conserva ese recibo y el intento sigue detenido; un fallo de persistencia no se
presenta como éxito de aplicación ni como consumo cero.

## Límite de esta integración local

Esta ruta sirve al operador de una instalación local con una sesión existente
que administra Pi. No configura una API de producto multiusuario ni concede
derechos de reventa de una cuenta CLI. Una futura integración de servicio debe
definir su proveedor API, autenticación, permisos, presupuesto y operación
independientemente; no se deriva de habilitar este adaptador local.

Fuentes oficiales fijadas a la versión:
- [ModelRuntime](https://github.com/earendil-works/pi/blob/v0.84.4/packages/coding-agent/src/core/model-runtime.ts)
- [ReadOnlyAuthStorage](https://github.com/earendil-works/pi/blob/v0.84.4/packages/coding-agent/src/core/auth-storage.ts)
- [Resolución OAuth](https://github.com/earendil-works/pi/blob/v0.84.4/packages/ai/src/auth/resolve.ts)
- [Transporte Codex y límites](https://github.com/earendil-works/pi/blob/v0.84.4/packages/ai/src/api/openai-codex-responses.ts)
- [Normalización de uso](https://github.com/earendil-works/pi/blob/v0.84.4/packages/ai/src/api/openai-responses-shared.ts)

Fuente adicional: [semántica de auth check](https://github.com/earendil-works/pi/blob/v0.84.4/packages/coding-agent/src/cli/auth-check.ts).
