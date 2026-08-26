# Prototipo visual C

Prototipo estático navegable de **Aula directa** para Issue #72. Es una opción aislada: no comparte rutas, modelos, plantillas ni assets con producción.

## Ejecutar localmente

Desde la raíz del repositorio:

```bash
python -m http.server 8000 --directory prototypes/visual-c
```

Abre la dirección local del servidor (puerto 8000) en el navegador. La interfaz no hace peticiones a servicios de red ni requiere instalación. También puede abrirse `index.html` directamente, aunque el servidor local permite verificar mejor el recorrido por fragmentos.

Recorrido rápido:

1. En **Inicio**, elige **Entrar** o **Preparar sesión**.
2. En **Estudiante**, revisa el QR sintético, la ruta y el camino compacto; pulsa **Continuar**.
3. En **Docente**, pulsa **Preparar sesión** y después **Activar**.
4. En **Actividad activa**, observa el QR persistente, cambia los cuatro estados y añade un apodo local sintético.

## Alcance y límites

- Cada texto de sesión, tema, participante y apodo es una demostración sintética; no describe alumnado real ni contenido curricular aprobado.
- El QR se dibuja localmente y no es un código de acceso real.
- Los apodos viven solo en la memoria de esta demostración: desaparecen al cerrar la sesión y al recargar o cerrar el navegador. No son cuentas estudiantiles y no se muestran puntuaciones individuales.
- `EditorialReviewer` conserva la revisión, aprobación y publicación. La maestra activa la `ClassroomSession`. La IA solo propone y no tiene autoridad editorial, de evaluación o de activación.
- No se usan identidades reales, UUIDs visibles, cuentas, imágenes, fuentes, assets remotos, CDN o servicios externos.

## Archivos

- `index.html`: cuatro vistas de inicio, estudiante, docente y actividad.
- `styles.css`: tokens, alto contraste, foco, móvil pequeño, proyección y movimiento reducido.
- `app.js`: navegación por fragmentos, QR sintético, estados y apodos locales en memoria.
- `DESIGN.md`: decisiones visuales, autoridad, datos y adaptación.
