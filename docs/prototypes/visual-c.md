# Nota de entrega — prototipo visual C

## Qué se entrega

`prototypes/visual-c/` contiene una experiencia estática navegable de Aula directa para Issue #72. Incluye landing general, entrada estudiante con ruta/QR sintético y camino de temas ya vistos, landing docente y actividad activa con QR persistente, conteo y apodos locales en memoria.

## Garantías del prototipo

Es una demostración aislada y explícitamente sintética. No modifica producción ni representa contenido curricular autorizado. `EditorialReviewer` revisa, aprueba y publica; la maestra activa la `ClassroomSession`; la IA solo propone. No hay cuentas estudiantiles, identidades reales, UUIDs visibles, puntuaciones individuales, imágenes, fuentes ni assets remotos. El estado de los apodos vive solo en memoria y se borra al cerrar la sesión o recargar el navegador.

La interfaz cubre los estados `espera`, `activo`, `cerrado` y `error`, con foco visible, comportamiento para teléfono pequeño, disposición para proyección y alternativa estática mediante `prefers-reduced-motion`.

## Verificación

Servidor local:

```bash
python -m http.server 8000 --directory prototypes/visual-c
```

Prueba específica:

```bash
/Users/dojo/Documents/ChatGPT/AulaLista-repo/.venv/bin/python -m pytest -q tests/test_prototype_visual_c.py
```
