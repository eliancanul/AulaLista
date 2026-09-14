# PROTOTYPE — revisión de planeación

Pregunta: ¿qué estructura permite a un docente leer su planeación y resolver dudas con menos esfuerzo?

Tres variantes estructurales, mismo estado de demostración:
- A: Cuaderno de clase, dudas dentro de la lectura diaria.
- B: Revisión guiada, una duda y su fuente por paso.
- C: Mesa de revisión, índice lateral y comparación en paralelo.

## Ejecutar

Desde la raíz del repo:

```sh
python3 prototypes/revision-planeacion-prototype/serve.py
```

Abrir http://127.0.0.1:8876/tutor/imports/96/interpretacion/?variant=A

Las flechas de la barra inferior o del teclado cambian A/B/C. ↺ reinicia. Las flechas no se interceptan en campos editables ni en diálogos. Los cambios se comparten al alternar diseños y desaparecen al recargar.

Servidor independiente, ligado a localhost. Reproduce el contexto visual y la ruta de interpretación, sin modificar las vistas, autenticación ni datos reales del servidor 8000. La ruta no consulta la importación 96: todo es una demostración en memoria. No hay integración de producción ni llamadas al modelo. Solo sirve el HTML de este prototipo.

Los fragmentos del lunes se inspiran en el texto visible durante el recorrido. El martes y los estados de comprobación son simulados; la redacción de las clases está resumida para evaluar organización, no fidelidad de extracción. Una implementación real no debe convertir datos en automáticamente comprobados por esta demostración.

Interacciones: cambiar clase, abrir resumen automático, editar grado, consultar referencia, resolver, aplazar, corregir nuevamente y aprobación simulada. Tres dudas de ejemplo, seis datos automáticos de ejemplo. Estado completo desplegable al pie.

Al preparar: checkout de producción ya tenía numerosos cambios ajenos; solo se añadieron archivos en esta carpeta. No se integra ningún ganador ni se realizan cambios en GitHub. El usuario eligió explícitamente B (Revisión guiada). Pendiente decidir ajustes para mayor volumen e integración; no se autoriza integrar por esta elección. Cuando haya una elección, registrar el resultado y capturar los prototipos en una rama descartable según la skill prototype, preservando el trabajo previo del checkout.

Referencia de alcance acordado: `/tmp/aulalista-handoff-ux-importacion.md`. El usuario aceptó dejar la carga actual tal como está y pidió explorar únicamente esta revisión.

## B con más volumen

`?variant=B&volume=large`: 20 clases en cuatro semanas, 40 páginas simuladas, 68 campos de ejemplo y 12 dudas. Incluye instrucciones largas, referencia paralela, índice por semana para saltar o volver, consulta de datos automáticos por clase y lectura general de las 20 clases. Cambiar entre ejemplo corto y extenso desde el control superior. Cantidades y contenido sintéticos; no representan capacidad, exactitud o rendimiento medidos del importador.
