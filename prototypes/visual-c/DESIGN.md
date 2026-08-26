# Visual C — Aula directa

## Intención

Visual C reduce la interfaz a la siguiente decisión de aula: **entrar**, **preparar**, **activar** o **cerrar**. El contraste, el tamaño táctil y el camino curricular compacto tienen prioridad sobre decoración, gamificación y métricas.

Este es un prototipo estático aislado. Todo lo que aparece en pantalla está marcado como **Demostración sintética** o `DemoPackage`; no representa una planeación autorizada, contenido curricular validado ni una sesión real.

## Recorrido

1. **Inicio** ofrece dos entradas equivalentes en jerarquía, con una acción grande para estudiante y otra para docente.
2. **Estudiante** presenta un QR dibujado con CSS/DOM y la ruta local `/demo-ciencias`. El camino compacto marca dos temas ya vistos y el siguiente.
3. **Docente** presenta una actividad sintética, sesiones recientes sintéticas y controles separados de preparar y activar.
4. **Actividad activa** mantiene el QR visible, el conteo y los apodos que la persona escribe en memoria. La maestra puede demostrar espera, activo, cerrado y error.

La navegación usa fragmentos (`#home`, `#student`, `#teacher`, `#active`), así que no necesita un servidor de aplicaciones ni cambia rutas de producción.

## Autoridad y datos

- `EditorialReviewer` es la persona humana que revisa, aprueba y publica el paquete.
- La maestra activa la `ClassroomSession` cuando el grupo está listo.
- La IA solo propone: no publica, no evalúa, no declara aprendizaje y no crea evidencia.
- Los apodos son entradas temporales mantenidas únicamente en memoria para esta demostración y limitadas a 20. Al cerrar la sesión se vacían la lista y el conteo; también desaparecen al recargar o cerrar el navegador. No son cuentas, nombres, matrículas ni identidades.
- El prototipo no muestra UUIDs, puntuaciones individuales, fuentes, imágenes, assets remotos ni dependencias WAN.
- El QR es deliberadamente sintético y no codifica una identidad ni un destino remoto. El dato visible `/demo-ciencias` es una ruta de demostración.

## Sistema visual

| Token | Uso | Valor |
| --- | --- | --- |
| `--ink` | Texto y QR | `#17212b` |
| `--blue` | Acción primaria | `#075985` |
| `--paper` | Fondo | `#f6f7f2` |
| `--yellow` | Aviso de autoridad/espera | `#ffd447` |
| `--line` | Divisiones | `#ccd5d9` |
| `--focus` | Foco visible | `#b45309` |

Los botones tienen como mínimo 48 px de alto. La acción principal del inicio y de cada recorrido se distingue por color, borde o tamaño. El foco usa un contorno de 4 px con desplazamiento para teclado y controles táctiles.

## Estados

- **Espera:** la maestra comparte el QR; la entrada todavía no se presenta como actividad disponible.
- **Activo:** el grupo puede entrar y el contador refleja apodos locales.
- **Cerrado:** se detiene la entrada y se limpian los apodos de la demostración.
- **Error:** se comunica una recuperación concreta sin inventar una causa o un resultado.

## Adaptación

- **Teléfono pequeño (280–420 px):** una columna, botones de ancho completo cuando hace falta, QR reducido pero legible, formulario apilado y navegación en segunda línea.
- **Proyección (1000 px o más y altura suficiente):** QR grande, conteo de alto impacto y menos relleno vertical para que la operación quede en una pantalla.
- **Movimiento reducido:** `prefers-reduced-motion: reduce` desactiva el desplazamiento suave y las transiciones. La información de temas ya vistos sigue siendo legible sin animación.

## Decisiones técnicas

Es HTML, CSS y JavaScript sin dependencias. El patrón tipo QR se genera con una matriz fija en DOM, no con imágenes, fuentes remotas o una CDN. El JavaScript usa `textContent` para pintar apodos locales y fragmentos para navegar sin red.
