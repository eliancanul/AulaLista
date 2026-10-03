# Controles locales de seguridad y procedencia

Ejecutar desde el checkout integrado, con las dependencias de ambos locks:

```sh
python -m pytest tests/sprint_security tests/test_sprint_auth.py tests/test_night_source_roles.py tests/test_night_integration.py -q
```

Los controles nuevos usan PDFs generados, respuestas de proveedor escritas como fixtures, cuentas efímeras y bases temporales. No llaman a proveedores ni prueban datos de producción. Los tests API comprueban sesiones Django, CSRF, aislamiento por propietario, confirmación explícita y revisiones concurrentes.

El contrato v2 exige evidencia de la sección explícita para proyecto, propósito y finalidad. La proyección conserva `unknown` si esa atribución no está demostrada. El hash de la fuente se verifica antes de detalle, descarga, historial, listado o aprobación. La aprobación docente no publica currículo ni crea sesiones estudiantiles.

Persisten dos hallazgos del flujo legacy en `test_s18_known_findings.py`, marcados `xfail(strict=True)`:

- El verificador legacy puede marcar un valor de otra sección de la misma página como comprobado.
- El adaptador antiguo de temas puede aceptar un título o página inventados en una respuesta estructuralmente válida.

Estos límites no quedan resueltos por aprobar pruebas del adaptador v2. No convertir un xfail, una omisión o un test con transporte sintético en una validación real de proveedores.

La evidencia de cada ejecución debe conservar SHA/tree, comando, entorno, código de salida y hashes de logs fuera del repositorio. La revisión local no sustituye la revisión independiente ni CI del commit exacto que se pretenda compartir.
