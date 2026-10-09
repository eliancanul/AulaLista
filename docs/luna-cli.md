# Luna mediante la CLI local

El adaptador `LunaCodexCliProvider` ejecuta la consola oficial Codex como proceso
local. No usa la API de OpenAI, no pide una API key y no lee ni copia archivos de
credenciales. Usa la sesión ChatGPT que el cliente oficial ya administra. La
interfaz del proveedor mantiene separado un posible adaptador API futuro.

## Estado y límites

El contrato implementado está fijado a Codex CLI **0.159.2**, modelo solicitado
`gpt-6-luna`, esfuerzo `high`. La versión 0.158 no se considera compatible por
suposición. Las pruebas del adaptador ejecutan una CLI inventada y comprueban
entrada, salida, errores y persistencia; no acreditan inferencia de Luna.
Los canarios reales observados en nube y Mac fallaron antes del modelo. La
comprobación real queda pendiente y no se elude cambiando trust, sockets,
permisos, entorno o modo de sandbox.

- `--ephemeral --json --output-schema` y stdin; nunca el prompt en argumentos.
- Una ejecución por llamada, sin resume, fallback ni relanzamientos automáticos.
- Plazo local de 30 segundos por defecto, configurable entre 1 y 120; preflight
  separado acotado a 30 segundos. Límite combinado stdout/stderr de 128 KiB y
  respuesta final de 32 KiB. La solicitud completa admite 4 MiB, sin recorte.
- Estos límites no son topes de tokens/costo ni prueban que el servidor dejó de
  generar al terminar el proceso. Reintentos internos, peticiones backend y
  costo quedan desconocidos. No se deducen tokens de caracteres.
- El JSONL documentado no atestigua necesariamente el modelo devuelto:
  `requested_model` se fija y `observed_model` queda `null`. Se rechaza un
  reroute observado. Los tokens se conservan tal como se reportaron;
  `reasoning_output_tokens` puede quedar `null`, sin inferir cero ni totales.
- Sólo se admiten items `reasoning` y `agent_message`, un turno completado y una
  salida final regular que concuerde con el último mensaje. Herramientas,
  permisos, eventos desconocidos, truncamiento, errores o contabilidad terminal
  incompleta detienen la captura. Detectar un evento puede ocurrir después de
  iniciar una acción: **no es prevención de herramientas ni garantía de cero
  herramientas**. Se termina el grupo local propio; no se acredita la muerte
  de todo descendiente que escapó del grupo ni de un trabajo remoto.

## Preparación de la instalación

1. Verificar una instalación oficial existente con `codex --version` y
   `codex login status`. Una sesión ChatGPT no demuestra todavía una consulta
   satisfactoria. Si necesita iniciar sesión, la persona operadora lo hace en
   el cliente oficial, fuera de AulaLista. No copiar tokens ni auth.json.
2. Elegir el ejecutable absoluto real (resolver un enlace simbólico) y un
   directorio privado de intentos de la misma cuenta que ejecuta Django. No
   apuntar a fuentes públicas, estáticos ni un directorio con escritura de
   otras personas. El adaptador crea sus carpetas privadas y rechaza permisos
   inseguros; no modifica permisos de directorios existentes.
3. Revisar las restricciones de esa versión/instalación con datos sintéticos.
   El perfil exige raíz denegada, runtime mínimo y sólo la carpeta nueva de
   trabajo legible; no concede escritura. La red de operaciones sandboxed está
   deshabilitada. El entorno de comandos hereda únicamente PATH y HOME de
   trabajo, sin login shell. Se solicitan los flags de reducción de herramientas
   del contrato. `unified_exec` y otras capacidades pueden seguir expuestas:
   los flags no acreditan por sí solos su ausencia efectiva.
4. Registrar una revisión humana real de las superficies externas/managed MCP,
   apps y configuración efectiva. No volcar configuración que pueda contener
   secretos. Las consultas de diagnóstico y los flags pueden tener capas de
   configuración distintas; si no se puede establecer el alcance, dejarlo
   pendiente y no habilitar llamadas. No se agrega una ruta alternativa.

El manifiesto privado de revisión tiene esta forma (los marcadores no son un
manifiesto válido):

```json
{
  "schema": "aulalista.codex-local-review.v1",
  "cli_version": "0.159.2",
  "launcher_sha256": "SHA256_DEL_EJECUTABLE_REVISADO",
  "profile_contract_sha256": "SHA256_DE_LA_RECETA_DE_RESTRICCIONES",
  "review_id": "UUID_DE_LA_REVISION",
  "reviewed_at": "FECHA_ISO_CON_ZONA",
  "evidence_sha256": "SHA256_DEL_REGISTRO_DE_REVISION_REAL",
  "external_surface_review": "reviewed_no_external_surfaces",
  "limitations_acknowledged": [
    "event_detection_is_not_prevention", "no_server_token_cap",
    "returned_model_not_attested", "internal_retries_not_observed"
  ]
}
```

La receta completa está en `PROFILE_CONTRACT`; su huella se obtiene con
`python -c "from curriculum.luna_review_provider import PROFILE_SHA256; print(PROFILE_SHA256)"`.
El manifiesto debe pertenecer a la cuenta operadora y no ser escribible por
grupo/otros. Su hash de evidencia es una referencia a la revisión humana:
AulaLista no verifica automáticamente el informe externo ni atestigua el
estado actual de managed MCP. No tiene caducidad automática ni sustituye una
revisión después de cambiar configuración, permisos, herramientas o runtime.
No rellenar este registro con un booleano o una prueba simulada para aparentar
una instalación segura. Un cambio del ejecutable, versión o receta invalida
su coincidencia automáticamente.

Configurar sólo rutas no secretas; mantener las llamadas deshabilitadas durante
la preparación:

```sh
export AULALISTA_TEACHER_REVIEW_PROVIDER=luna
export AULALISTA_LUNA_CLI_EXECUTABLE=/ruta/absoluta/al/codex-real
export AULALISTA_LUNA_RUNTIME_REVIEW=/ruta/privada/revision-runtime.json
export AULALISTA_LUNA_ATTEMPT_DIR=/ruta/privada/intentos-luna
export AULALISTA_LUNA_LIVE_ENABLED=0
export AULALISTA_LUNA_TIMEOUT_SECONDS=30
python manage.py check
```

No definir `CODEX_API_KEY`, `OPENAI_API_KEY` ni `OPENAI_BASE_URL` para esta ruta.
El adaptador rechaza su presencia, incluso vacía, sin leer ni registrar valores;
no las elimina ni cambia autenticación silenciosamente.

Sólo después de resolver los bloqueos y autorizar el intento/datos/destino,
la persona operadora puede habilitar `AULALISTA_LUNA_LIVE_ENABLED=1` y reiniciar
su proceso Django. El primer ensayo debe ser sintético. Habilitar no garantiza
éxito: antes de transmitir cada prompt, la aplicación comprueba identidad,
opciones y login, después `/bin/true`, lectura permitida de un canario propio,
lectura denegada de otro canario propio y escritura denegada. Cada fallo corta
inmediatamente; no se inicia el modelo. Esos canarios cubren esas operaciones,
no todas las capacidades ni una prueba física de bloqueo de red.

El PDF/dossier completo y las respuestas se transmitirían a OpenAI mediante la
CLI al continuar. Eso requiere autorización específica de los datos; elegir
Luna o aprobar un smoke no autoriza automáticamente documentos privados.

## Recibos y recuperación

Cada intento admitido usa un UUID nuevo, solicitud por archivo privado/stdin,
esquema y hashes, streams acotados y recibo. Los logs de CLI también pueden
contener texto privado; ephemeral no significa ausencia de logs. No copiarlos
a GitHub, distribuciones, capturas públicas o directorios estáticos.

Un fallo previo al modelo deja sólo un registro seguro de preflight. Después
de la admisión, un resultado incierto o rechazado crea `STOP_REQUIRED.json`;
un proceso interrumpido también puede dejar el lock o una admisión sin recibo.
No reintentar, borrar el bloqueo, cambiar de carpeta para eludirlo ni atribuir
consumo cero. Revisar el intento y su autorización antes de cualquier
reconciliación manual. Guardar/corregir una respuesta o cambiar la fuente no
borra estos estados. El antiguo UNKNOWN de Gemini conserva su identidad.

El backend vuelve a verificar esquema, destinos, citas humanas literales,
versión/SHA y límite de seis preguntas. Un resultado de consola no concede
aprobación ni publicación. La evidencia de transporte se conserva aunque una
respuesta sea rechazada por incumplir esas reglas.
