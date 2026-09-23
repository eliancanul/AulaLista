# Prototipo desechable: esqueleto de la vista docente

Responde a la pregunta: **¿cómo debe organizarse la vista principal del docente antes de rediseñar el producto?**

Incluye tres variantes estructuralmente distintas en una sola ruta:

- `?variant=A` — vista actual: navegación superior y bloques por función.
- `?variant=B` — aula primero: navegación lateral y siguiente acción dominante.
- `?variant=C` — ciclo escolar: avance curricular como contexto y sesiones como acción.

La navegación docente no muestra “Salones” en este esqueleto de primaria. Esa capacidad queda condicionada por la configuración institucional que realiza personal IT y solo se habilitaría para secundaria.

También incluye una previsualización del lobby estudiantil. El primer prototipo no muestra mapa curricular al estudiante: solo indica que está esperando a que la maestra abra la sesión.

## Ejecutar

Desde la raíz del repositorio:

```bash
python -m http.server 4173 --directory prototypes/docente-skeleton
```

Abre [http://127.0.0.1:4173/?variant=B](http://127.0.0.1:4173/?variant=B). B es la variante principal. Usa las flechas de la barra inferior o las teclas `←` y `→` para cambiar de variante.

El botón **Preparar sesión** abre un flujo individual por pantallas en `?variant=B&step=prepare`:

1. `prep=1`: roadmap completo y selección de actividad.
2. `prep=2`: roadmap minimizado, número de alumnos y número de dispositivos.

Después de `prep=2` aparece directamente el resumen listo (`prep=3`), sin un paso adicional de “Revisión”.

La sección **Currícula y planeación** se puede abrir con `?variant=B&area=curricula`; desde ahí, “Usar en sesión” lleva al primer paso del flujo de preparación.

Para probar una currícula grande, abre `?variant=B&area=curricula&view=many`. Muestra 6 temas y 22 actividades agrupados en secciones plegables.

Para probar la estructura oficial SEP, abre `?variant=B&area=curricula&view=sep&phase=3`. La vista representa las Fases 3, 4 y 5 de primaria, los cuatro campos formativos, los programas sintético/analítico y algunos ejes articuladores. Los títulos de actividades son datos sintéticos de interfaz, no transcripciones del programa oficial.

Fuentes oficiales consultadas:

- [Plan de Estudio 2022](https://educacionbasica.sep.gob.mx/wp-content/uploads/2024/07/Plan-de-Estudios-Educacion-Basica_digital-2024.pdf)
- [Plan y Programas de Estudio 2022 · Subsecretaría de Educación Básica](https://educacionbasica.sep.gob.mx/plan-y-programas-de-estudio-2022-para-la-educacion-preescolar-primaria-y-secundaria/)

Es un prototipo local, sintético, sin persistencia y sin llamadas al backend. Los botones solo representan estados visuales.
