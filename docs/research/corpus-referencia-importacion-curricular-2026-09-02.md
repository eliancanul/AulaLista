# Corpus de referencia para importacion curricular

Fecha de inventario: 2026-09-02.

Este manifiesto agrupa fuentes locales y web para diagnosticar la lectura de
planeaciones heterogeneas. No incorpora ni redistribuye copias nuevas de los
documentos. Antes de convertir cualquier fuente en fixture versionada se debe
confirmar su licencia o sustituirla por un derivado sintetico minimo.

## Fuentes locales

| ID | Ruta local | SHA-256 | Paginas | Clase estructural observada | Expectativa inicial |
| --- | --- | --- | ---: | --- | --- |
| C01 | `output/pdf/prueba-issue-96-paginas-4-a-8.pdf` | `33d7c2862a7d14127b2906518b26bc16f0f571f85d765dd6cd63325f52337648` | 5 | Planeacion semanal con sesiones, momentos y tres anexos | Control positivo del fast path existente; no representa generalizacion |
| C02 | `/Users/dojo/Downloads/curricula completa.pdf` | `c5a5455b52aa55dba2c9f58b650c8d37cdf1a486c07ce6a4645230d296bc043a` | 44 | Compendio con cuatro proyectos, sesiones, rubricas y trece anexos | Debe producir manifest completo, conservar paginas sin texto y abstenerse por unidad no reconocida sin descartar el resto |
| C03 | `/Users/dojo/Downloads/Planeacio5toGradoSemana02MeReconozco_a_Através_De_Mi_Familia.docx.pdf` | `12f24c6b2ea356edfde1fb31c1f112644d72b386a87798d17d8a66e8c04f0354` | 15 | Proyecto por sesiones y momentos; anexos graficos; paginas promocionales | Debe separar planeacion, anexos/cuadernillo y material ajeno al contenido curricular |
| C04 | `/Users/dojo/Downloads/planeacion-julio-quinto-grado.pdf` | `065e5bed6bddf2f88035c1088f6b4dd450136ab0b2a718825da03239ff41aadb` | 11 | Planeacion mensual multiasignatura por semanas, dias y proyectos | Debe conservar jerarquia mensual/semanal/diaria y no forzarla a un unico tema |

## Fuente web

| ID | URL | Clase estructural observada | Expectativa inicial |
| --- | --- | --- | --- |
| W01 | <https://www.redmagisterial.com/planeacionesnme/primaria/5-5to/53-espanol/1> | Bloque I, semana 1, cinco sesiones de 50 minutos con Inicio, Desarrollo, Cierre, recursos y evaluacion | Debe poder representarse como sesiones relacionadas sin copiar recursos externos ni confundir una sesion completa con una actividad digital de AulaLista |

## Uso de prueba propuesto

- El PDF original es evidencia fuente inmutable; cada corrida registra su hash.
- La unidad de evaluacion es la pagina y el bloque estructural, no el nombre del
  archivo ni el dominio de origen.
- Un gold set revisado por una persona debe marcar tipo de pagina, jerarquia,
  texto, tablas, figuras, referencias a anexos y rangos de fuente.
- Las paginas o bloques no reconocidos permanecen en el manifest con una
  advertencia. Nunca se omiten en silencio.
- Los cuadernillos se clasifican y conservan. En esta etapa solo se usa su texto;
  sus imagenes no se transforman en actividades ni claves de respuesta.
- La salida de importacion termina en propuestas editables. No aprueba, publica,
  activa sesiones ni cambia `CurriculumProgress`.

## Estado del inventario

Este archivo registra el corpus y sus primeras expectativas, no un gold set
terminado ni evidencia de precision. Las anotaciones por pagina, los criterios de
aceptacion y la autorizacion de uso deben revisarse antes de implementar.
