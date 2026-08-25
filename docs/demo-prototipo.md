# Guion de demostración — Prototipo del viernes

**Milestone:** Prototipo viernes · **Duración estimada:** 15–20 minutos
**Requisitos:** MacBook con Ollama (`ollama list` debe mostrar `qwen2.5:7b`), red local sin necesidad de WAN.

> Regla inquebrantable de la demo: la IA **sólo propone borradores**. Toda revisión,
> aprobación y publicación es humana. No presentar el contenido generado como
> planeación aprobada ni atribuir autoridad editorial a la IA.

## Checklist pre-demo (10 minutos antes)

```sh
cd ~/Documents/ChatGPT/AulaLista-repo
source .venv/bin/activate
python manage.py check                 # sin errores
python manage.py migrate --check      # sin migraciones pendientes
pytest -q                              # suite completa en verde
ollama serve &                         # si el daemon no está corriendo
curl -s localhost:11434/api/tags | grep qwen2.5   # modelo presente
```

- [ ] Cuenta staff creada para la maestra (`python manage.py createsuperuser`).
- [ ] PDF de la currícula real listo en el escritorio (digital, no escaneado).
- [ ] Dos teléfonos/tablets en la misma red Wi-Fi; `AULALISTA_LAN_URL` configurada.
- [ ] Plan B sin WAN: todo el pipeline corre local (Ollama incluido); verificar
      que ningún recurso externo aparece en `docs/evidence/`.

## Recorrido de la demo

### Acto 1 — De la currícula al borrador (LLM como asistente) · ~6 min

1. Entrar a Wagtail (`/cms/`) con la cuenta de la maestra → sección del maestro → **Importar currícula** (`/tutor/imports/new/`).
2. Cargar el PDF. El sistema extrae el texto y muestra páginas detectadas.
3. **El modelo local identifica los temas** con citas de página (~10 s por bloque). *Mostrar las citas: cada tema apunta a su página del PDF.*
4. **Checkpoint humano:** editar/eliminar/agregar temas → confirmar.
5. **La LLM propone subtemas** por tema, con conteo de actividades sugeridas según densidad.
6. **Checkpoint humano:** ajustar subtemas → confirmar jerarquía.
7. "Generar actividades": por cada subtema se redacta un borrador completo (objetivo, microlección, reactivos con opciones/pistas/retroalimentación). *Los inválidos aparecen marcados y no son convertibles (#24).*
8. **Checkpoint humano:** seleccionar los buenos → **Convertir en borradores**.
9. En Wagtail: los paquetes aparecen etiquetados **"borrador asistido por IA"**, esperando revisión humana. *Subrayar: la IA no publicó nada.*

### Acto 2 — Revisión y publicación humanas · ~3 min

1. Como `EditorialReviewer`, abrir un borrador, ajustar lo necesario y guardarlo.
2. Intentar aprobar un paquete incompleto → **el sistema lo rechaza mostrando los faltantes** (#16/#19).
3. Iniciar workflow → aprobar → snapshot publicado (versión + hash).

### Acto 3 — Sesión de aula y encuesta · ~6 min

1. Sección del maestro → preparar sesión sobre el snapshot publicado (revisar versión/hash en pantalla) → confirmar → activar.
2. Compartir el QR/enlace único; dos dispositivos se incorporan solos.
3. Alumnos: apodo local → microlección → reactivos → pistas (sin cambiar la puntuación).
4. **Encuesta** (`/student/sessions/<id>/encuesta/`): anónima, una por dispositivo.
5. Maestro cierra la sesión: se borran turnos/asignaciones; quedan métricas seudonimizadas.
6. Resultados: agregados deterministas + **resumen de la encuesta** (conteos y comentarios abiertos) + exportación JSON (incluye `"survey"`).

## Respaldos por afirmación

| Afirmación de la demo | Prueba automatizada |
|---|---|
| La IA no crea paquetes ni publica | `test_t15_curriculum_import.py`, `test_t16_activity_generation.py` |
| Nada inválido se publica aunque la IA lo proponga | `test_t03_publication_snapshot.py` |
| Encuesta sin identidad y conservada tras cierre | `test_t14_student_survey.py` |
| Práctica determinista, ayuda sin penalización | `test_t05_deterministic_practice.py` |
| Cierre elimina relaciones temporales | `test_t08_pseudonymous_close.py` |
| Acceso docente protegido | `test_t17_teacher_console.py` |

## Evidencia posterior

- Captura por acto guardada en `evidence/demo-viernes/` (nomenclatura: `acto1-paso3.png`, …).
- Registrar en `docs/evidence/` cualquier desviación observada durante el ensayo.
