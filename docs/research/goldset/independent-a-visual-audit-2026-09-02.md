# Auditoria visual independiente A - corpus semilla

**Alcance.** Auditoria manual independiente de los cuatro PDFs locales del
manifiesto, hecha contra paginas renderizadas; no es adjudicacion ni validacion
de un adapter. No se copio ningun PDF comercial al repositorio. La anotacion
maquina-legible asociada es `independent-a-annotations-2026-09-02.jsonl`.

## Metodo y trazabilidad

- Render: Poppler `pdftoppm`; C01 a 110 dpi y C02-C04 a 75 dpi para revisar la
  totalidad; las regiones profundas de C01 se reabrieron a 110 dpi. Los renders
  son temporales fuera del repositorio.
- Extraccion auxiliar: pypdf por pagina, solo para contrastar texto visible; no
  se uso como prueba de orden, tabla o semantica visual.
- Bboxes regionales son manuales, normalizados, aproximados y marcados como
  tales. Las cajas de pagina usan el MediaBox exacto. No hay bboxes de celdas,
  palabras ni imagenes: eso requeriria una segunda pasada de anotacion a mayor
  resolucion.
- Fuente/licencia: C02-C04 siguen siendo fuentes locales comerciales/de terceros
  con licencia no confirmada. Solo se registran ruta y SHA-256; no deben pasar a
  fixtures ni redistribuirse. C01 es fuente derivada/parcial (paginas 4-8 de
  C02), por lo que no es documento independiente ni evidencia de generalizacion.

## Cobertura completa de paginas

Los estados siguientes se aplican a **cada** pagina indicada; no hay pagina
omitida. `I` = `included`, `R` = `reference_only`, `E` = `excluded`.

| Documento | Paginas y estado |
| --- | --- |
| C01, 5 paginas | 1 I (ficha); 2 I (tabla de sesiones); 3 R (anexo 01); 4 R (anexo 02); 5 R (anexo 03) |
| C02, 44 paginas | 1 E (portada); 2 I (metadatos); 3 R (separador); 4 I (ficha); 5 I (sesiones); 6 R, 7 R, 8 R, 9 R (anexos/continuacion); 10 I (sesiones); 11 R, 12 R (anexo/continuacion); 13 I (sesion); 14 I (rubrica); 15 R (pagina vacia/separadora); 16 I (ficha); 17 I (sesiones); 18 R, 19 R, 20 R, 21 R (anexos/continuacion); 22 I (sesiones); 23 R, 24 R (anexos); 25 I (sesion); 26 I (rubrica); 27 R (separador); 28 I (ficha); 29 I (sesiones); 30 R (anexo); 31 I (sesiones); 32 R, 33 R (anexos); 34 I (sesion); 35 I (rubrica); 36 R (separador); 37 I (ficha); 38 I (sesiones); 39 R, 40 R (anexo/continuacion); 41 I, 42 I (sesiones); 43 I (rubrica); 44 E (promocion) |
| C03, 15 paginas | 1 I, 2 I, 3 I, 4 I, 5 I, 6 I, 7 I, 8 I (planeacion/sesiones); 9 R, 10 R (anexos); 11 E, 12 E, 13 E, 14 E, 15 E (redes, QR y tablas de grupos) |
| C04, 11 paginas | 1 I, 2 I, 3 I, 4 I, 5 I, 6 I, 7 I, 8 I, 9 I, 10 I (planeacion, semanas, rubrica/adecuaciones); 11 E (promocion) |

No se marco ninguna pagina como `quarantined`: la abstencion aparece en
relaciones o semantica de region que no pueden justificarse con esta pasada.

## Muestra profunda estratificada

| Documento/pagina | Rasgo cubierto | Observacion verificable | Estado/abstencion |
| --- | --- | --- | --- |
| C01/1 | Vertical, ficha, jerarquia | Encabezado y metadatos sobre tabla | `included`; bbox de encabezado aproximado |
| C01/2 | Tabla, sesiones/fases/recursos | Columnas y filas visibles; no se anotaron celdas | `included`; estructura de celdas pendiente |
| C01/3 | Cuadernillo mixto | Anexo 01 con texto, URL e ilustracion | `reference_only`; semantica de imagen abstained |
| C02/14 | Rubrica | Tabla de criterios y niveles | `included`; celdas combinadas `unknown` |
| C02/24 | Anexo con tabla | Tabla de clasificacion en hoja de trabajo | `reference_only`; no se derivan respuestas |
| C02/44 | Promocion | Llamados de seguimiento y enlaces | `excluded` |
| C03/1 | Horizontal, tabla densa | Contexto y objetivo en columnas | `included`; orden de columnas debe medirse |
| C03/8 | Continuacion/producto | Cierre y producto visibles | `included`; relacion exacta sesion-producto `unknown` |
| C03/10 | Cuadernillo visual | Anexos 03-04 con imagenes/lineas | `reference_only`; semantica visual abstained |
| C03/13 | Promocion tabular | Tabla de grupos de Facebook | `excluded` |
| C04/1 | Horizontal, ficha/tablas | Contexto curricular en tabla | `included` |
| C04/3 | Mes-semana-dia | Semana 1 y estructura diaria visible | `included`; limite exacto de subarbol diario `unknown` |
| C04/9 | Rubrica | Instrumento de evaluacion formativa tabular | `included`; celdas no anotadas |
| C04/10 | Tabla de adecuaciones | Reflexion y adecuaciones curriculares | `included` |

## Relaciones y bloqueos visuales

- C01/2 a C01/3: hay continuidad documental hacia el anexo, pero la sesion
  exacta a la que se adjunta no es legible con certeza. Se conserva la relacion
  como `reference_only`, con abstencion del destino exacto.
- C02/4 a C02/14: el nombre del proyecto coincide explicitamente con el titulo
  de la rubrica; esta es la unica relacion proyecto-rubrica afirmada.
- C03/1-8 a C03/9-10: los anexos siguen las sesiones, pero no existe una ancla
  inequívoca para asignar cada anexo a una sesion. La relacion queda
  `quarantined`/`unknown`, no se resuelve por proximidad.
- C03/11-15 y C02/44 son material promocional, no una ausencia o fallo de
  extractor. Deben aparecer en cualquier manifest y excluirse con razon.

## Resultado de la auditoria

La semilla basta para medir captura, orden, layout y abstencion por clase de
pagina, pero no para declarar precision general ni escoger un adapter. Antes de
calcular CER/WER, IoU, tablas o jerarquia hace falta una segunda anotacion
independiente y adjudicacion; esta A no debe ser reemplazada por la salida de
ningun adapter.
