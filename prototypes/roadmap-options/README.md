# Prototipo de opciones de Roadmap docente

Prototipo desechable para responder una pregunta de diseño: **¿qué forma de roadmap resulta más intuitiva para una maestra?**

Incluye tres variantes en la misma ruta y con datos sintéticos:

- `?variant=A` — camino vertical inspirado en Duolingo.
- `?variant=B` — recorrido compacto por lecciones siguiendo el patrón de Lingo.
- `?variant=C` — propuesta propia de AulaLista, con jerarquía y acciones docentes.

## Ejecutar

Desde la raíz del repositorio:

```bash
python -m http.server 8000 --directory prototypes/roadmap-options
```

Abre `http://127.0.0.1:8000/?variant=A`. Cambia `A`, `B` o `C` en la barra inferior; las flechas izquierda/derecha del teclado también cambian de variante.

En la variante C puedes probar las tres microinteracciones del último punto con los botones `1`, `2` y `3` o usando `?variant=C&motion=1|2|3`.

Todo es sintético, local y no persistente. Los botones sólo simulan estados visuales; no llaman al backend ni modifican producción.
