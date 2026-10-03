# Registro histórico del sprint experimental

**Recorrido retirado:** esta nota conserva el contrato experimental Vue anterior. La entrada pública `/sprint/` ahora redirige a Currícula y autoría; no se usa para el MVP docente. Para ejecutar y probar el recorrido activo, seguir [Revisión docente](teacher-review.md) y [Aceptación y operación](teacher-review-acceptance.md). Las cuatro regresiones históricas de navegador se conservan sólo con URLconfs optativos de tests.

Integración local desde `c787068014c9ebbe1c7eb1ead341e1182b667c0a`.
No representa veinte módulos terminados ni validación pedagógica. El frontend
compilado comparte origen con el login Django y la API; no requiere proveedor.

## Arranque

Reutilizar un entorno Python 3.13 con `requirements.lock` y
`requirements-service.lock`, y Node 24 con el `package-lock.json` de frontend.
La integración local se comprobó reutilizando instalaciones existentes, sin
instalar paquetes. Para un entorno nuevo autorizado, los comandos son:

```sh
python -m pip install --require-hashes -r requirements.lock -r requirements-service.lock
npm --prefix frontend ci --ignore-scripts
npm --prefix frontend run build
```

Seleccionar una base Django de desarrollo ya migrada y con una cuenta docente
local autorizada. El comando no crea cuentas, permisos ni migra bases existentes.
Elegir otro archivo para los borradores. No usar una base de producción.

```sh
python scripts/serve_sprint.py --django-db /ruta/dev-django.sqlite3 --drafts-db /ruta/privada/sprint.sqlite3
```

Abrir `http://127.0.0.1:8000/sprint/`, iniciar sesión, preparar un PDF sintético,
contrastar campos y fuentes, abrir Actividad, editar y guardar. Reabrir desde
Mis borradores. Marcar la revisión explícita y aprobar la versión actual;
cualquier edición posterior vuelve a pendiente. Historial conserva las
revisiones anteriores y el PDF fuente se descarga con su hash verificado.
Cerrar sesión usa POST con CSRF y revoca la sesión Django.

## Pruebas

Todas las pruebas de integración usan bases temporales separadas y datos
sintéticos. Las pruebas nuevas generan sus PDFs; la suite heredada conserva sus fixtures y omisiones. El navegador genera su
PDF sintético y cuenta efímera dentro de la base de pruebas.

```sh
npm --prefix frontend run build
npm --prefix frontend test
node --test frontend/tests/*.test.mjs
python -m pytest -q
python -m scripts.sprint_eval.offline_v2
python scripts/sprint_smoke.py --service-deps --output /tmp/sprint-smoke.json
```

`tests/test_night_browser.py` ejecuta Chrome real con perfil temporal y el conjunto
Django/FastAPI/Vue/SQLite. En Linux se detecta Chrome/Chromium instalado; `NIGHT_CHROME` permite fijar el binario.
La CI exige ese binario antes de pytest y falla si falta; no omite la aceptación
con `NIGHT_BROWSER_REQUIRED=1`.
En entornos con sandbox se requiere permiso para escuchar sólo en loopback.
`NIGHT_EVIDENCE_DIR` permite guardar capturas/log fuera del repositorio.

La CI ahora instala ambos locks, verifica imports obligatorios, compila Vue y
corre Vitest, controladores Node y pytest. Un workflow editado no constituye CI
verde: el SHA exacto requiere verificación independiente antes de publicar.

## Integración y límites

- S02/S06 proporcionan extracción física y contrato v2 con incertidumbre y
  procedencia; S07/S08/S09 proporcionan transporte, sesión/CSRF y SQLite.
- S11/S12/S13/S14/S15/S17 aportan shell, revisión, editor, exportación, landing y
  consulta. La consulta activa es búsqueda local de fragmentos; las propuestas
  de edición S16/S17 no están conectadas para aplicación automática.
- S20 aporta locks, smoke y conciliación de la plantilla Django S13/S15. Se
  conservó la allowlist de aprobación y se separó el formulario que la envía.
- S04/S05 están conectados a fixtures v2 comunes y controlan JSON duplicado,
  métricas inválidas y errores. Cero respuestas reales, ninguna comparación de
  modelos, ninguna inferencia de ganador. La rúbrica literal S01 y la aceptación
  de esquema tienen denominadores distintos. El runner legacy Gemini exige
  explícitamente su contrato v1; no se convierte en un falso PASS v2.
- S03 se mantiene en su rama: su captura está congelada al árbol original y no
  debe etiquetar esta integración como medición de aquella base. S10/S19 son
  documentación/evidencia histórica y no se incorporan como resultados nuevos.
- La UI conserva edición durante guardados, conflictos y desconexión; no promete
  sincronización offline ni recuperación tras cerrar la pestaña. Las aclaraciones
  de revisión son temporales hasta incorporarlas explícitamente al borrador.
- Persisten dos hallazgos legacy S18 fuera del nuevo adaptador: verificación de
  un valor contra una sección incorrecta y propuestas antiguas de temas sin
  validar la fuente. Sus pruebas xfail permanecen visibles. El recorrido v2
  rechaza esos títulos y referencias mediante el contrato S06.
- Aprobar una revisión no publica currículo ni activa una sesión estudiantil.
  No se midió uso real con docentes ni carga productiva. No hay despliegue.

Los SHA fuente completos y los registros de pruebas se entregan por separado;
los reportes históricos no sustituyen pruebas del candidato exacto.

## Correcciones tras la revisión independiente

La prueba de trazabilidad usa los módulos del propio checkout. Sus controles
sintéticos adaptan el título a la regla de procedencia actual, sin cambiar el
corpus congelado ni la rúbrica. Los selectores de pruebas distinguen el botón
de cierre de sesión de las acciones dentro de `main`; los eventos sintéticos
incluyen el propietario real del control HTML.

Si un guardado guiado avanza la versión mientras el formulario completo conserva
ediciones, se bloquea su envío antiguo. La versión esperada no se incrementa:
se conserva el texto, se explica el conflicto y se ofrece descargar una copia
sin token CSRF antes de reabrir y comparar la versión guardada. No hay fusión
ni sobrescritura automática.

El contrato y la proyección v2 comprueban la sección explícita de proyecto,
propósito y finalidad: una cita de materiales no puede completar esos campos,
aunque contenga literalmente el valor. Si no se demuestra el rol, la proyección
conserva `unknown`. Esta comprobación estructural no es validación semántica.
El listado aplica el mismo control de hash de fuente que detalle e historial;
una fuente dañada produce `409/source_changed` antes de mostrar aprobaciones.

En este Mac, cuatro pruebas heredadas del benchmark fallan al solicitar
`RLIMIT_AS=1073741824`. Las mismas cuatro pruebas se reprodujeron sobre un snapshot exacto de la base
con datos sintéticos. Todos los blobs del harness son idénticos a la base. No
se ha demostrado que el fallo sea exclusivo de macOS ni que pase en Linux. No se quitó el límite ni se
convirtieron fallos en skips. Esta limitación no acredita medición del benchmark;
la suite general local conserva esos cuatro fallos hasta verificarlos en un
entorno compatible. Los logs completos se entregan fuera del repositorio.
