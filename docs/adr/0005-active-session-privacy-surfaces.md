# ADR-0005: Superficies de privacidad para el modo activo

- **Estado:** Aceptado
- **Fecha:** 2026-08-26

## Contexto

Una sesión activa necesita una pantalla para que la docente opere la actividad y otra
pantalla que pueda proyectarse frente al grupo. Aunque el apodo local es útil para
el control, una pantalla pública no debe convertirlo en una identidad observable.
La sesión ya conserva los turnos temporalmente y los elimina al cerrar; no se
agrega almacenamiento ni una relación nueva para resolver esta diferencia.

## Decisión

Se separan las superficies:

1. **Control docente autenticado** (`tutor-session-active`): sólo una persona de
   personal autenticada puede verlo. Mientras la sesión está `active`, muestra los
   `StudentTurn` activos cuyo `display_name` no está vacío. En `prepared` y
   `closed` no muestra apodos. Puede conservar la operación de cierre mediante el
   endpoint existente POST+CSRF; no convierte un GET en una autoridad.
2. **Proyección pública** (`session-projection`): no requiere login y sólo muestra
   estado, conteo de participantes y, mientras está activa, el QR/enlace local de
   entrada. Nunca muestra apodos, UUID o identificadores de dispositivo,
   capacidad, resultados, puntuaciones ni controles peligrosos.

Ambas páginas son no-cacheables. La activación y el cierre continúan siendo las
operaciones humanas existentes, con POST y CSRF. Al cerrar, `ClassroomSession.close`
conserva únicamente resultados seudónimos y borra los turnos, asignaciones y
resumen efímero antes de presentar la revisión cerrada.

## Consecuencias

El conteo público puede cambiar entre solicitudes, pero no revela qué estudiante
entró. La docente puede distinguir temporalmente los apodos sólo en el control
privado. El enfoque reutiliza el enlace/QR local existente y los contratos actuales,
sin modelos, migraciones, almacenamiento efímero adicional ni dependencias remotas.
El diseño visual usa una base sobria C, con jerarquía editorial para comunicar
snapshot, versión y autoridad humana en la superficie docente.
