# Desarrollo conservador tras la segunda evaluación

Relacionado con [#149](https://github.com/eliancanul/AulaLista/issues/149).
Base: `e7c2105373ed381e39ef871105af7b92f9bf89ec`.

Este cambio corrige el límite del propósito ante un patrón tabular corroborado
y reconoce una forma inequívoca de encabezado de sesión partido. **La sexta
sesión del documento expuesto sigue pendiente:** una comilla editorial anterior
está sin cerrar y no se elimina la protección de citas para recuperar ese caso.
No se resolvieron automáticamente los dos defectos originales.

## Reglas y límites

El recorte nuevo sólo se aplica a propósito/finalidad con cierre de oración,
ante una fila completa de metodología conocida y, en la línea física adyacente,
una cabecera completa de Campo(s), Contenido(s) y PDA/Proceso(s) de desarrollo.
El cuerpo de esa tabla no se incorpora al objetivo. Se conservan el fragmento
literal y la revisión pendiente. Prosa intermedia, citas, columnas incompletas,
una sola pista o un objetivo sin cierre conservan el candidato para revisión.
No se amplía la regla para títulos ni se reconstruyen celdas geométricamente.
Una transcripción no entrecomillada con esa misma forma sigue siendo
indistinguible en texto plano.

La forma partida admitida contiene etiqueta completa, un LF/CRLF, entero
positivo aislado y otro LF/CRLF seguido inmediatamente de Inicio, Desarrollo o
Cierre como etiqueta. El ancla conserva los saltos y offsets originales.
Los títulos partidos con puntuación, fechas, listas, líneas intermedias y otros
separadores dentro de esa forma siguen sin crear sesión. No se unen páginas.
La gramática legacy de los demás encabezados y sus cortes se conserva.

Una comilla sin cerrar puede corresponder a una errata o a una cita multilínea
auténtica. El documento conocido presenta una errata visible en una celda
anterior; eso no proporciona al parser textual una frontera verificable de
celda. El tramo detectado permanece sin asignar para revisión. La recuperación
automática de esa sesión requiere evidencia estructural adicional; se reserva
para investigación separada, con contrato y fallback explícitos.

No cambian los esquemas v1, predicados, gates ni autoridad de publicación. La
verificación recomputa anclas y alcance. Cuando recuperar una ocurrencia cambia
los IDs de sesiones repetidas, las decisiones docentes que ya no se emparejan
se conservan para revisión y no saltan a otra sesión por número o posición.

## Comprobaciones de desarrollo

Los tests nuevos contienen texto sintético escrito para este patrón. No son un
holdout ni una estimación de precisión. La base pasó 212 pruebas focales y la
suite de main existente pasó 1203, con 10 omitidas. Antes de implementar, el TDD
inicial produjo 35 fallos previstos para objetivos y 19 para encabezados
partidos; 47 controles ya pasaban. Los fallos registran comportamiento esperado
nuevo, no errores introducidos en la suite anterior.

La revisión adversarial detectó efectos laterales antes de publicar:

- Una cabecera curricular se confundía con un valor de campo y desactivaba el
  corte de un bloque posterior. Ahora las columnas no borran el último campo
  real; los campos explícitos desconocidos mantienen su tratamiento anterior
- Endurecer el whitespace global quitaba cortes y entidades legacy. La
  restricción se aisló a la nueva forma partida, con regresiones de sesiones,
  días, proyectos citados, reinicios y unidades por fases
- Filas con separadores verticales o CR malformados corroboraban límites
  indebidamente. Se comprueban los finales físicos de ambas filas y su separación
- Un número muy largo podía abortar la extracción. Los ceros iniciales sólo se
  normalizan al convertir el número; los enteros no convertibles permanecen
  como límites débiles con su texto sin asignar, sin excepción

El candidato final pasa **355 pruebas focales**, incluidas las 212 previas, y
**93 controles independientes**. Cubren citas, variantes numéricas, páginas,
continuaciones, repetición, manipulación de anclas, round-trip y decisiones
humanas. Los checks globales y CI del commit final se registran en el PR.

## Documento conocido: regresión expuesta, no evaluación nueva

El documento C2D01 de la [segunda cohorte](./prospective-cohort2-2026-10-01.md)
se usa ahora expresamente como desarrollo. Sus resultados congelados anteriores
permanecen intactos; no se recalculó el benchmark para sustituirlos ni se presenta
este control como evidencia prospectiva.

Sobre la única oportunidad objetivo de propósito, la coincidencia normalizada
con la referencia IA previamente expuesta pasa de **0/1 a 1/1 (+100 puntos
porcentuales)**. Ese denominador de uno sólo comprueba la regresión trabajada:
no es precisión humana, exactitud general ni mejora en documentos desconocidos.
El valor pasa de 1976 a 592 caracteres normalizados al excluir contenido
adyacente; la reducción de caracteres no se usa como score de calidad.
El campo sigue pendiente de revisión.

Se siguen emitiendo **9 unidades**, sin recuperar la sexta sesión mencionada.
La abstención frente a la comilla abierta se conserva deliberadamente. No se
afirma una mejora global de segmentación ni se cambia la referencia para
convertir esa ausencia en acierto.

Los originales y las salidas textuales permanecen privados. Una evaluación de
generalización necesita fuentes nuevas seleccionadas y congeladas después del
release, antes de observar sus salidas. Los veinte documentos históricos siguen
sin originales/hashes recuperados; Luna fue referencia IA, no validación docente.
