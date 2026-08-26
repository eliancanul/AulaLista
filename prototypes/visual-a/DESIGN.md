# Visual A — Editorial tranquila

## Intención

Visual A trata AulaLista como una mesa de trabajo editorial, no como un tablero de métricas. La interfaz deja que el contenido y el siguiente paso respiren: primero la idea, después la acción. La confianza docente se construye haciendo visibles los límites de la demostración y la autoridad humana.

La gramática es compartida entre las cuatro vistas:

- **Inicio:** dos entradas equivalentes, estudiante y docente.
- **Estudiante:** entrada breve por código/enlace y un camino curricular calmado, con estados «visto», «ahora» y «después».
- **Docente:** sesiones recientes, preparación y una franja explícita de revisión humana.
- **Actividad:** QR local, código corto, conteo y apodos locales en memoria; los cuatro estados se pueden simular.

## Dirección visual

- **Superficies:** `--paper` (#f6f4ef) como papel cálido, `--surface` (#fffdfa) para tarjetas y `--surface-warm` para metadatos. Bordes finos y sombra muy tenue separan sin convertir la pantalla en un mosaico de tarjetas.
- **Texto:** serif del sistema para lectura y titulares; Arial del sistema para controles, etiquetas y datos. Así se conserva una voz editorial sin descargar fuentes.
- **Color semántico:** teal sobrio para acción, continuidad y estado local; ámbar para revisión humana; rosa apagado únicamente para error. El color siempre acompaña a una etiqueta o símbolo.
- **Ritmo:** mucho espacio entre bloques, reglas horizontales y una sola línea de acción principal. La ruta usa una línea vertical y marcadores, no puntos de gamificación.
- **Proyección:** el control «Modo proyección» cambia a fondo oscuro, sube el contraste y mantiene el QR en superficie clara. No crea otra experiencia ni requiere un asset.

## Componentes y comportamiento

| Componente | Decisión |
| --- | --- |
| Enlace/código | `DEMO-7K4` es un código sintético fijo, visible para poder recorrer la demo sin red. |
| QR | Patrón CSS generado por `app.js`; es ilustrativo, no una imagen, librería o recurso remoto. El código se puede escribir si el escaneo no está disponible. |
| Apodo | Se normaliza, se limita a 18 caracteres y vive solo en memoria durante la visita. Al cerrar la sesión se vacían la lista y el conteo; al recargar o cerrar la página desaparece. No hay cuenta, correo, matrícula o identidad. |
| Estados | Espera, activa, cerrada y error tienen texto, símbolo y control de demostración. Cerrar desactiva el botón de cierre; los controles permiten volver a recorrer cada estado. |
| Conteo | Cuenta apodos locales en esta pantalla. No es puntuación, asistencia oficial ni evidencia de aprendizaje. |
| IA y publicación | El texto mantiene la frontera: la IA solo propone; `EditorialReviewer` aprueba y publica; la maestra activa. |

## Accesibilidad y dispositivos

- HTML semántico, encabezados por vista, navegación con enlaces hash, `aria-live` para comentarios y conteo, y etiquetas asociadas a todos los campos.
- `:focus-visible` usa un anillo ámbar de alto contraste; existe enlace para saltar al contenido.
- El layout baja a una columna en pantallas pequeñas y a un ajuste específico hasta 390 px. Los objetivos de botones conservan un mínimo de 44 px.
- `prefers-reduced-motion` elimina transiciones y el cambio de vista no depende de una animación. El JavaScript consulta la preferencia antes de cambiar de vista tras la entrada.
- No se usan fuentes, imágenes, iconos, CDN, llamadas de red ni assets remotos.

## Datos y límites

Todo contenido, nombres de sesiones, código, temas y apodos iniciales son **datos sintéticos explícitos**. El estado de la sesión vive solo en memoria: no usa almacenamiento persistente del navegador y se borra al cerrar. El prototipo no presenta alumnado real, no muestra puntuación individual y no afirma validación pedagógica. Es un recorrido visual aislado; no modifica los modelos ni las rutas de producción.
