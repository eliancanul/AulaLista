# Prototipo visual B · Camino de aprendizaje

Prototipo estático aislado de AulaLista. Es una demostración navegable de un camino `unidades → lecciones → actividades`, no una parte de producción.

> **Demostración sintética:** todos los nombres, apodos, conteos, códigos, estados y textos de contenido son inventados para probar la interfaz. No introduzcas datos reales en este prototipo.

## Ejecutar sin red

Desde la raíz de este worktree:

```bash
python -m http.server 8000 --directory prototypes/visual-b
```

Abre `index.html` a través del servidor local. También se puede abrir el archivo directamente, aunque el almacenamiento del navegador funciona de forma más consistente con el servidor local. No se necesita instalar nada ni conectar el servidor a Internet.

## Recorrido sugerido

1. En **Inicio**, elige **Entrar por enlace o QR**.
2. Escribe un apodo sintético y entra al camino. También puedes usar **Ver camino sin entrar**.
3. Observa unidades, lecciones y actividades: hay temas `visto`, `actual`, `disponible`, `bloqueado` y una unidad `completada`.
4. En **Vista docente**, confirma que la activación es una decisión de la maestra después de la aprobación de `EditorialReviewer`.
5. Activa la sesión para ver el QR persistente, el conteo y los apodos locales.
6. Usa los controles del modo activo para revisar `Espera`, `Activo`, `Cerrado` y `Error`.

La acción **Continuar con la actividad** abre una sola actividad por pantalla; sus respuestas solo producen un mensaje sintético local. La IA no publica, no activa, no declara avance y no decide resultados.

## Archivos

- `index.html`: landings, camino, vistas docente y activa.
- `styles.css`: sistema visual local, móvil pequeño, proyección y movimiento reducido.
- `app.js`: navegación, QR gráfico, estado de sesión y apodos locales.
- `DESIGN.md`: decisiones, estados y límites del prototipo.
