# Revisión docente: prueba y operación

## Estado de esta entrega

La entrada activa usa Django: **Currícula y autoría → Importar planeación → Revisar planeación**. `/sprint/` redirige a Currícula y autoría. La presentación visual definitiva se revisará por separado.

GPT-6 Luna mediante Pi (`pi_luna`) es la selección de esta etapa de pruebas locales. El adaptador local está integrado, con LIVE=0 y contexto `complete`; este candidato requiere aceptación real separada. El objetivo es un SaaS conectado con IA, cuya conexión API se hará después. La aplicación informa el estado de configuración y conserva respuestas y borradores. Las pruebas OFF no llaman al modelo ni habilitan fallback automático.

La ruta histórica Gemini high tampoco está validada. Su primer intento sintético autorizado terminó sin respuesta aceptada ni recibo terminal de consumo. **STOP_UNKNOWN: transmisión y consumo desconocidos, no cero.** No se debe reintentar, borrar el bloqueo, cambiar el directorio de recibos para eludirlo ni sustituir silenciosamente el modelo para eludir el bloqueo. La nueva selección Luna no borra ni reetiqueta ese intento. Una nueva autorización puede admitir otro ensayo acotado con una ruta efectivamente sin herramientas y datos concretos permitidos; nunca reescribe ni concilia automáticamente el intento anterior. El ensayo empieza con un smoke sintético y sólo después puede usar una planeación de desarrollo revisada para excluir datos sensibles. FINAL queda fuera.

El navegador de nube bloqueó el acceso local. Las pruebas HTTP y de plantillas no acreditan QA visual ni aceptación con un PDF real. Las pruebas con respuestas simuladas tampoco acreditan calidad del modelo real o validación pedagógica.

## Lista de aceptación con tu PDF real

Primero, en un entorno autorizado y con las llamadas reales deshabilitadas:

1. Importar una planeación elegida por ti. Llegar a la revisión Django sin entrar a Vue ni a la antigua pantalla de edición masiva.
2. Abrir «Planeación completa y procedencia». Comparar el número de sesiones, todas las actividades, anexos y sus páginas con el PDF. Registrar cualquier omisión; una página candidata nunca equivale a un anexo confirmado.
3. Comprobar que los campos desconocidos y la falta de conexión real se muestran con claridad, sin inventar respuestas ni afirmar aprobación.

Sólo cuando se resuelva el bloqueo y se autorice el envío del PDF/dossier y las respuestas al proveedor específico de la ruta Luna verificada:

4. Ver una sola pregunta y una sola caja. Comprobar que la siguiente pregunta usa lo que ya respondiste y contempla sesiones posteriores/anexos; no basta con que la API devuelva JSON válido.
5. Escribir, esperar la confirmación de borrador guardado, recargar y volver a abrir. Enviar una respuesta literal, comprobarla en «Respuestas guardadas» y corregirla. No debe desaparecer, duplicarse ni reaplicarse a otra sesión.
6. Comprobar doble clic, volver/avanzar, otra pestaña y pérdida de conexión al guardar. El texto debe conservarse o mostrar un conflicto explícito. Ante resultado/consumo desconocido, detener la prueba; recuperar la interfaz no autoriza otra llamada.
7. Usar «No tengo ese dato» o una respuesta de incertidumbre. Debe seguir pendiente, sin convertir «no sé» en contenido respaldado. El contador nunca supera seis ni vuelve a cero al corregir; puede terminar antes.
8. Revisar la distinción entre evidencia del PDF y aportes humanos, los originales y el historial. Verificar pendientes honestos al cerrar y aprobación humana explícita sólo cuando corresponde. Guardar respuestas nunca debe aprobar ni publicar.

Guardar los resultados de aceptación sin adjuntar el PDF ni respuestas privadas a issues, capturas públicas o logs compartidos. La aceptación exige el recorrido observado; una suite verde no sustituye el juicio de usabilidad.

## Arranque del desarrollador

Trabajar con la revisión exacta acordada y Python 3.13. Antes de aplicar migraciones a una instalación con datos, hacer una copia privada coherente de SQLite, archivos subidos y recibos de intentos, con el servicio detenido. Nunca incluir esa copia en el paquete de distribución.

```sh
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock -r requirements-service.lock
export AULALISTA_TEACHER_REVIEW_PROVIDER=pi_luna
export AULALISTA_PI_LIVE_ENABLED=0
export AULALISTA_LUNA_LIVE_ENABLED=0
export AULALISTA_TEACHER_REVIEW_CONTEXT_MODE=complete
export AULALISTA_GEMINI_LIVE_ENABLED=0
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python manage.py runserver
```

La revisión Django no requiere construir Vue. La comprobación local de navegador se realiza únicamente donde el acceso esté permitido; no se elude el bloqueo de la nube.

La selección `pi_luna` requiere la preparación de [Pi local](pi-luna.md); la habilitación no sustituye el preflight ni una consulta real. La ruta anterior `luna` sigue requiriendo [Luna CLI](luna-cli.md) cuando se selecciona expresamente. La configuración histórica siguiente pertenece a Gemini y no configura Pi:

- `AULALISTA_GEMINI_AGY_LAUNCHER`: launcher oficial validado de la instalación existente.
- `AULALISTA_GEMINI_AGY_AGENT_FILE`: perfil cuya ausencia efectiva de herramientas esté demostrada; que el archivo diga `tools: []` no basta.
- `AULALISTA_GEMINI_ATTEMPT_DIR`: directorio privado persistente, fuera de estáticos y del paquete distribuible. Conservar su ledger y cualquier STOP_UNKNOWN entre reinicios y cambios de versión.
- `AULALISTA_GEMINI_MODEL`: conservar el identificador exacto comprobado por el código, sin fallback.
- `AULALISTA_GEMINI_TIMEOUT_SECONDS`: 90 por defecto, hasta 120. No representa un límite monetario ni de tokens.
- Mantener `AULALISTA_GEMINI_LIVE_ENABLED=0` en el estado actual. La habilitación no sustituye una autorización de datos/ejecución pendiente.

## Reversión conservadora

1. Detener la aplicación y deshabilitar llamadas reales. Preservar la base, archivos y ledger privados.
2. Volver al código de la versión anterior acordada. Las migraciones 0044 y 0045 son aditivas; no ejecutar automáticamente una migración inversa, porque eliminaría respuestas o borradores.
3. Mantener las tablas adicionales y el ledger mientras se valida compatibilidad. Restaurar una copia antigua de la base descartaría cambios posteriores; sólo hacerlo como una recuperación explícita y consciente de esa pérdida.
4. Comprobar salud, inicio de sesión, propiedad de planeaciones y acceso a fuentes. No borrar STOP_UNKNOWN ni reactivar Gemini para comprobar la reversión.

## Distribución y pruebas

El paquete debe contener código, plantillas, CSS/JS y migraciones. Debe excluir entradas privadas, media, bases, `.runtime`, `.env*`, artefactos y corpus. La configuración de rutas privadas personalizadas requiere excluirlas también. Revisar el inventario del tarball antes de compartirlo; `.gitignore` no protege un archivo tar.

Distinguir siempre: pruebas enfocadas del nuevo flujo, agregado offline permitido, suites no ejecutadas/excluidas, CI del commit exacto, QA visual y prueba real de Luna/PDF. Ninguna de esas etiquetas sustituye a las demás. Publicar, hacer push, modificar el PR, fusionar o desplegar requiere la autorización correspondiente.

## CI del recorrido activo

El gate `test_teacher_review_browser.py` usa Chrome, autenticación Django real, bases temporales, un PDF generado y un proveedor adaptativo simulado instalado exclusivamente por la prueba. Las llamadas reales permanecen deshabilitadas. Verifica la caja única, guardado y reapertura, corrección, fuentes, aprobación humana y ausencia de publicación. La prueba no instala un proveedor ficticio en producción ni mide calidad del modelo real.

Las regresiones de navegador de Vue y edición masiva siguen separadas como contratos inactivos. Los eventos DOM sintéticos se comprueban además con `node --test tests/test_teacher_review_dom.mjs`. El navegador local debe estar permitido; estas pruebas no autorizan eludir una denegación de acceso.
