# Prototipo visual A

Prototipo estático navegable de AulaLista, dirección **Editorial tranquila**. Es una carpeta aislada: sus datos son sintéticos y su propósito es revisar jerarquía, confianza docente y estados de aula.

## Recorrido local

No requiere instalación ni conexión de red. Desde la raíz del repositorio:

```sh
cd prototypes/visual-a
python -m http.server 8000
```

Abre `localhost:8000` en el navegador. También se puede abrir `index.html` directamente, aunque el servidor local reproduce mejor una navegación estática.

### Rutas de la demo

- `#inicio`: landing general con las entradas estudiante y docente.
- `#estudiante`: entrada por código/enlace y camino con temas vistos.
- `#docente`: sesiones sintéticas, preparación y regla de revisión humana.
- `#actividad`: modo de aula con QR CSS, conteo y apodos locales en memoria.

En la actividad se pueden simular los estados **espera**, **activa**, **cerrada** y **error**. «Modo proyección» cambia la superficie para una pantalla compartida. El código de prueba es `DEMO-7K4`.

## Límites intencionales

- `EditorialReviewer` es una persona humana: aprueba y publica. La IA solo propone.
- La maestra activa la sesión.
- No hay identidades reales, cuentas estudiantiles, UUIDs visibles ni puntuaciones individuales.
- Los apodos iniciales son constantes sintéticas en memoria. Los apodos añadidos viven solo en memoria durante la visita, se vacían al cerrar la sesión y desaparecen al recargar o cerrar la página.
- No hay fetch, CDN, fuentes web, imágenes, assets remotos ni almacenamiento persistente del navegador; el estado se borra al cerrar la página. No se modifica el producto de producción.

Las decisiones de tokens, layout, estados y accesibilidad están en [DESIGN.md](DESIGN.md).
