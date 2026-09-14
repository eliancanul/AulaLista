# Prototipo desechable: UI de Dirección

Responde a la pregunta: **¿qué estructura permite a Dirección entender primero qué decisión debe tomar?**

Incluye tres variantes estructuralmente distintas en una sola ruta:

- `?variant=A` — **Bandeja de decisiones**: navegación superior y pendientes priorizados.
- `?variant=B` — **Mesa operativa**: navegación lateral, agenda y siguiente acción dominante.
- `?variant=C` — **Mapa institucional**: grupos como contexto explorable y detalle de la decisión.
- `?variant=D&paper=operacion` — **Implementación de los papers**: coordinación, datos/Roadmap, gobernanza y programa de validación en una experiencia integral.

Las tres permiten recorrer `Resumen → Grupos y docentes → Importar/revisar → Acciones → Roadmap agregado → Auditoría`. La importación simula carga, conflictos, confirmación e idempotencia; ninguna acción llama al backend o persiste datos.

## Ejecutar

Desde la raíz del repositorio:

```bash
python -m http.server 4174 --directory prototypes
```

Abre [http://127.0.0.1:4174/director-skeleton/index.html?variant=A](http://127.0.0.1:4174/director-skeleton/index.html?variant=A).

Usa la barra inferior o las teclas `←` y `→` para comparar variantes. El enlace **Comparar docente** abre el prototipo docente dentro del mismo servidor.

La variante D muestra cómo se vería el alcance completo defendible por la investigación. Sus pestañas son:

- `paper=operacion` — coordinación, acuerdos y decisiones.
- `paper=datos` — importación, calidad, fuentes, mínimos de celda y Roadmap agregado.
- `paper=gobernanza` — autoridad, exportación, privacidad, ciclo de vida y límites de la LLM.
- `paper=validacion` — umbrales de ROI, entrevistas y gates de inversión.

Los indicadores de campo permanecen marcados como pendientes: una UI no sustituye entrevistas, medición de tiempos, pruebas de permisos ni validación institucional.

## Recorrido sugerido

1. En Resumen, identifica qué decisión puede tomar Dirección.
2. Abre **Revisar importación** y previsualiza la plantilla sintética.
3. Deja el homónimo pendiente o selecciona manualmente una cuenta existente.
4. Confirma la revisión y consulta la auditoría simulada.
5. Abre Roadmap, observa cómo se distinguen avance agregado y datos faltantes, y crea una acción.
6. Cambia entre A, B y C para comparar jerarquía y orientación.

## Límites deliberados

- Prototipo local, sintético, sin persistencia ni llamadas al backend.
- Una sola `School`, una persona `Director` y una modalidad confirmada.
- Dirección confirma adscripciones y acciones; IT administra cuentas y configuración técnica.
- No hay alumnos nominales, alias, dispositivos, respuestas, CRM, riesgo, ranking docente ni decisiones automáticas.
- El Roadmap muestra actividad agregada con datos faltantes explícitos; no afirma aprendizaje.
