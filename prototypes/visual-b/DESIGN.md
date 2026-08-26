# Camino B — nota de diseño

## Intención

Visual B presenta un **DemoPackage** de aprendizaje como un camino que se puede leer de izquierda a derecha y de arriba abajo: `unidades → lecciones → actividades`. La pantalla ofrece una sola decisión principal a la vez. El tono es de acompañamiento, no de competencia.

Todo texto, código de entrada, apodo, conteo y estado que aparece en este prototipo es un **dato de demostración sintética**. No representa una planeación autorizada, alumnado real ni evidencia de aprendizaje.

## Mapa de pantallas

- **Inicio general (`home`)**: dos entradas independientes: enlace/QR para estudiante y vista docente.
- **Entrada estudiante (`student`)**: espera de una sesión local, QR sintético, código persistente y formulario de apodo temporal.
- **Camino (`roadmap`)**: progreso 50%, guía de unidades/lecciones/actividades y la acción única de continuar a una actividad.
- **Vista docente (`teacher`)**: revisión del mismo camino, estado de la sesión y acción explícita para activar.
- **Modo activo (`active`)**: QR persistente, código local, contador de apodos y estados de espera, activo, cerrado y error.

Los botones de la cabecera permiten recorrer las cinco vistas sin servidor de aplicación. El formulario conserva el apodo únicamente en `localStorage` del navegador de demostración.

## Estados del camino

| Estado | Tratamiento | Significado en la demo |
| --- | --- | --- |
| `visto` | marca verde y texto auxiliar | La maestra indicó explícitamente que el tema ya fue visto. |
| `actual` | acento coral y flecha | Es el siguiente paso que la persona puede abrir. |
| `disponible` | círculo neutro | Está preparado para después del paso actual. |
| `bloqueado` | superficie gris y candado | Bloqueado por decisión docente; no lo desbloquea la IA. |
| `completado` | marca verde y etiqueta de unidad | Unidad sintética terminada en el recorrido de la demo. |

Los estados no son puntuaciones individuales. La interfaz evita que el clic de una persona cambie por sí mismo el avance del camino: la maestra conserva esa decisión.

## Estados de sesión

- **Espera**: la maestra está preparando; la entrada estudiante lo comunica.
- **Activo**: la maestra confirmó la activación y el QR permite participar.
- **Cerrado**: el acompañamiento terminó; se conserva como estado visible de la demo.
- **Error**: el almacenamiento local no estuvo disponible o se simuló un fallo de enlace; se ofrece reintento local.

El código `AULA-B7Q2` es sintético, legible y persistente en este navegador. El QR es un patrón gráfico generado por CSS y JavaScript, sin imágenes, red ni servicios de terceros.

## Autoridad y límites

El bloque editorial deja la secuencia visible: una IA puede preparar una propuesta; **EditorialReviewer** aprueba y publica el paquete; la maestra activa la `ClassroomSession`. La IA no publica, no declara avance, no decide bloqueos y no calcula resultados.

La actividad muestra una regla local explícita y solo confirma una respuesta de demostración. No presenta calificaciones individuales ni pretende validación pedagógica.

## Accesibilidad y contexto

- HTML semántico, `lang="es"`, enlace para saltar al contenido, etiquetas de formulario y mensajes con `aria-live`.
- Estados comunicados con texto además de color; foco visible de alto contraste y controles con tamaño táctil.
- `prefers-reduced-motion: reduce` elimina las transiciones y la entrada animada de pantallas.
- `@media projection` aumenta el QR y elimina elementos de navegación para proyectar el modo activo.
- El corte de 520px reorganiza tarjetas, botones y leyenda para un móvil pequeño.
- La tipografía usa la pila del sistema y todos los estilos se sirven desde este directorio.
