# AulaLista — contrato de diseño canónico

## Decisión y límites

La dirección canónica es **C — Aula directa**: C manda en móvil, proyección, contraste, tamaño táctil y la decisión siguiente. B aporta únicamente el roadmap esencial **unidades → lecciones → actividades**, sus estados y el progreso. A aporta únicamente la jerarquía editorial tranquila, el contenido primero, las superficies sobrias y la explicación visible de la autoridad humana.

Este documento es un contrato de diseño para las futuras superficies de producción; no cambia rutas, modelos ni plantillas. Describe una interfaz para el nodo educativo local y sus límites, no una afirmación de eficacia: **No afirma validación pedagógica**. Un `DemoPackage` siempre se rotula como **Demostración sintética** y no es una planeación autorizada, contenido curricular validado ni evidencia de aprendizaje.

La frontera de autoridad es invariable: una IA solo propone. Una persona **EditorialReviewer** revisa, aprueba y publica el `CurriculumPackage`; la **maestra activa** la `ClassroomSession`. La IA no publica, no activa, no califica, no declara aprendizaje y no crea evidencia. Los resultados de práctica, cuando existan, son deterministas y se basan en el `PublishedPackageSnapshot`.

## Principios de composición

- **Aula directa:** mostrar primero la situación, el contenido y la siguiente decisión; evitar marketing, gamificación, adornos y tableros de métricas.
- **Contenido primero:** el título, la consigna, el estado y la acción preceden a metadatos secundarios.
- **Una acción principal por pantalla:** `PrimaryAction` es única, tiene verbo docente/estudiantil y nunca se confunde con navegación o una acción destructiva.
- La jerarquía editorial usa aire, reglas finas y tarjetas sobrias; el color comunica estado y siempre va acompañado por texto o símbolo.
- El progreso es legible (porcentaje, texto y posición del camino), pero **no es puntuación** ni prueba de aprendizaje.

## Sistema de tokens

Los valores son la fuente de verdad para implementaciones locales. Deben expresarse como variables CSS o equivalentes del sistema visual.

| Token | Valor | Uso |
| --- | --- | --- |
| `--color-ink` | `#17212b` | Texto principal y QR sintético |
| `--color-action` | `#075985` | Acción primaria y enlaces |
| `--color-paper` | `#f6f7f2` | Fondo de página |
| `--color-surface` | `#fffdfa` | Superficies de contenido |
| `--color-review` | `#b45309` | Revisión humana y foco |
| `--color-error` | `#9f1239` | Error, nunca decoración |
| `--color-focus` | `#b45309` | Anillo de foco de 4px |
| `--space-1` | `0.5rem` | Separación mínima |
| `--space-2` | `0.75rem` | Controles y etiquetas |
| `--space-3` | `1rem` | Bloques compactos |
| `--space-4` | `1.5rem` | Secciones y respiración |
| `--radius` | `0.5rem` | Bordes discretos |
| `--text-body` | `1rem / 1.5` | Texto base legible |
| `--target-min` | `44px` | Área táctil mínima; preferir 48px en acciones |

Usar pilas tipográficas del sistema, sin descargar fuentes. No usar gradientes, texturas o color como único indicador. El contraste de texto normal y controles debe ser alto; el estado debe seguir siendo entendible en escala de grises y bajo un proyector.

## Componentes

- **Skip link:** primer foco de teclado, salta al contenido principal.
- **Header:** nombre del producto, contexto actual y navegación corta; nunca expone UUIDs ni identificadores técnicos.
- **PrimaryAction:** una por pantalla, mínimo `--target-min`, foco visible y texto explícito; las secundarias son enlaces o botones de menor peso.
- **Roadmap:** árbol visible de unidades, lecciones y actividades; cada nodo tiene nombre, estado textual y relación con el siguiente paso.
- **Status:** etiqueta más texto auxiliar y, cuando aplica, `aria-live`; los estados no dependen solo del color.
- **EditorialBoundary:** bloque tranquilo y persistente que dice que `EditorialReviewer` aprueba/publica y que la maestra activa; la automatización no recibe esa autoridad.
- **SessionCard:** estado de la `ClassroomSession`, snapshot publicado (versión y hash corto legible), siguiente acción y límites de datos.
- **ProjectionMode:** vista de alto contraste con QR o código local sintético, conteo legible y poco contenido periférico.
- **Questionnaire:** una pregunta por pantalla cuando sea posible, opciones grandes, instrucción breve y confirmación determinista; pedir solo lo necesario.
- **ResultsSummary:** resumen pseudónimo y agregado; no es expediente, no muestra identidad real ni infiere aprendizaje.

## Estados y superficies

Cada superficie debe tener una representación estable de sus estados `empty`, `loading`, `ready` y `error`. El texto de recuperación debe ser concreto y no inventar causa ni resultado.

| Superficie | Contrato de estados requerido |
| --- | --- |
| `general:` | `empty` entrada sin sesión; `loading` preparando acceso; `ready` entradas estudiante/docente; `error` reintento local |
| `student:` | `empty` esperando código; `loading` cargando snapshot local; `ready` entrada y siguiente acción; `error` enlace inválido sin filtrar datos |
| `teacher:` | `empty` sin sesiones; `loading` consultando datos locales; `ready` preparar/revisar/activar; `error` no se pudo cargar, conservar contexto |
| `questionnaire:` | `empty` sin pregunta; `loading` preparando pregunta; `ready` consigna y opciones; `error` respuesta no procesada, permitir reintento |
| `projection:` | `empty` espera de participantes; `loading` preparando QR/código; `ready` QR, código y conteo; `error` mostrar código alterno local |
| `results:` | `empty` sesión sin resultados; `loading` calculando reglas explícitas; `ready` resumen pseudónimo/exportable; `error` no presentar resultados parciales como definitivos |

Una `ClassroomSession` además comunica los estados de aula **espera**, **activo**, **cerrado** y **error**. `cerrado` detiene entradas y borra los apodos temporales de la demostración; no se presenta como pérdida ni como calificación.

### Roadmap y progreso

El `Roadmap` conserva estos cinco estados, todos visibles por texto:

- `visto`: la maestra indicó que el paso fue visto; no implica dominio.
- `actual`: siguiente paso enfocado y único objetivo de continuidad.
- `disponible`: preparado para después del actual.
- `bloqueado`: decisión docente explícita; la IA no lo desbloquea.
- `completado`: unidad o actividad terminada en el recorrido, sin declarar aprendizaje.

El avance debe mostrar posición y progreso legible sin convertirlo en ranking, puntos o puntuación individual. Una interacción estudiantil no altera por sí sola el estado curricular.

## Responsive y accesibilidad

### Proyección

Mobile-first: de 280 a 420px usar una columna, controles de ancho disponible, formulario apilado y navegación en segunda línea. Desde pantallas mayores se puede usar una grilla de dos columnas, manteniendo el contenido y la acción principal en el primer plano. No ocultar el estado o la acción para caber en móvil.

Todos los controles tienen al menos 44px de área táctil (48px preferidos), separación suficiente, `:focus-visible` de 4px, HTML semántico, encabezados ordenados, labels asociados y mensajes `aria-live` cuando el estado cambia. El contraste es alto y la interfaz sigue siendo legible en una pantalla compartida o **legible en proyección**: texto grande, QR/código estable, poco relleno vertical y sin depender de hover.

El modo `projection` aumenta QR, código, estado y conteo; elimina navegación secundaria y mantiene una ruta de entrada alternativa escrita. La información operativa debe caber en una pantalla de aula. Respetar `prefers-reduced-motion`: eliminar transiciones y desplazamiento suave; ninguna información puede depender de animación.

## Local, privacidad y datos

- **Assets locales:** CSS, JavaScript, iconos y cualquier fuente o imagen se sirven desde el repositorio. Sin CDN, sin fuentes externas, sin servicios de terceros y **sin red** para el flujo local; no hay `fetch` implícito ni dependencia WAN.
- Un QR de demostración puede dibujarse con CSS/DOM o un recurso local. Nunca codifica una identidad, una cuenta o un destino remoto.
- El contenido visible, códigos, sesiones, conteos y apodos son **datos sintéticos** cuando se trate de demo. Debe aparecer la frontera “Demostración sintética”. No inventar nombres de alumnado ni claims curriculares.
- Los alias temporales son **pseudónimos y acotados**: durante el turno activo solo son visibles en el control autenticado de la maestra; nunca se proyectan públicamente. Se purgan al completar el turno o cerrar la sesión. No son nombres ni identidad real.
- No pedir ni mostrar nombres (sin nombres), correo (sin correo), matrícula (sin matrícula), contraseña, UUID, `local_identifier` ni identificadores técnicos en superficies de aula. La `LocalDeviceQueue` usa un **identificador opaco** y no contiene identidad estudiantil.
- `StudentTurn`, `DeviceAssignment` y `PseudonymousResult` no son cuentas ni expedientes. Los resultados son eliminables y no requieren identidad real; un conteo no es asistencia oficial.
- La interfaz explica que asistencia, ayuda solicitada o progreso visual no constituyen evidencia de aprendizaje. No afirma validación pedagógica ni presenta una demo como material aprobado.

## No-regresión del contrato

Toda nueva superficie debe conservar estos principios, los tokens, la acción principal, estados textuales, la frontera humana de publicación/activación, los límites de privacidad y la operación sin CDN ni red. Las pruebas de contrato deben leer este archivo y fallar si se elimina cualquiera de esas garantías.
