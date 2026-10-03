type ActivityContent = {
  title: string;
  objective: string;
  materials: string[];
  steps: string[];
  assessment: string;
  source_ids: string[];
};

// Structural subset of S13 EditorState, not a persistence or approval API.
export type ExportState = {
  saved: { revision: number };
  draft: ActivityContent;
  approved: { revision: number; content: ActivityContent } | null;
};
export type ExportSource = {
  document_id: string;
  source_segments: { id: string; text: string; page: number }[];
};
export type ExportMode = 'draft' | 'approved';
export type ActivityFile = { filename: string; mime: string; content: string };

const escape = (value: string) => value.replace(/[&<>"']/g, character => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[character]!);

function validateContent(content: ActivityContent) {
  if (!content || ['title', 'objective', 'assessment'].some(key => typeof content[key as keyof ActivityContent] !== 'string') ||
    ['materials', 'steps', 'source_ids'].some(key => !Array.isArray(content[key as keyof ActivityContent]) ||
      !(content[key as 'materials'] as unknown[]).every(item => typeof item === 'string'))) {
    throw new Error('No se pudo preparar la copia. La actividad está incompleta o tiene un formato inválido. Tu texto sigue en el editor.');
  }
}

export function createActivityFile(state: ExportState, source: ExportSource, mode: ExportMode = 'draft', demo = false): ActivityFile {
  if (mode !== 'draft' && mode !== 'approved') throw new Error('Elige una copia del borrador o de la versión aprobada.');
  const selection = mode === 'approved' ? state?.approved : { revision: state?.saved?.revision, content: state?.draft };
  if (!selection) throw new Error('Todavía no hay una versión aprobada. Puedes descargar el borrador para revisarlo.');
  const { content, revision } = selection;
  if (!Number.isSafeInteger(revision) || revision < 0) throw new Error('No se pudo identificar la revisión de esta actividad.');
  validateContent(content);
  if (!source || typeof source.document_id !== 'string' || !source.document_id.trim() || !Array.isArray(source.source_segments)) {
    throw new Error('Falta el contexto del documento de origen. Conserva tu borrador y vuelve a cargar sus fuentes.');
  }
  const segments = new Map<string, ExportSource['source_segments'][number]>();
  for (const segment of source.source_segments) {
    if (!segment || typeof segment.id !== 'string' || !segment.id.trim() || typeof segment.text !== 'string' ||
      !segment.text.trim() || !Number.isSafeInteger(segment.page) || segment.page < 1 || segments.has(segment.id)) {
      throw new Error('Las referencias de origen no son válidas. Revisa las fuentes antes de exportar.');
    }
    segments.set(segment.id, segment);
  }
  const missingSources = !content.source_ids.length || content.source_ids.some(id => !segments.has(id));
  const missingContent = !content.title.trim() || !content.objective.trim() || !content.assessment.trim() ||
    !content.steps.length || content.steps.some(step => !step.trim());
  if (mode === 'approved' && (missingSources || missingContent)) {
    throw new Error('Falta contenido esencial o una fuente de la versión aprobada. Descarga el borrador y solicita su revisión.');
  }
  const text = (value: string) => value.trim() ? escape(value) : '<em>Pendiente de completar por la maestra o el maestro.</em>';
  const list = (items: string[], ordered = false) => items.length
    ? `<${ordered ? 'ol' : 'ul'}>${items.map(item => `<li>${text(item)}</li>`).join('')}</${ordered ? 'ol' : 'ul'}>`
    : '<p>Pendiente de confirmar por la maestra o el maestro.</p>';
  const references = [...new Set(content.source_ids)].map(id => {
    const segment = segments.get(id);
    return segment
      ? `<section class="source"><h3>Página ${segment.page}</h3><p>Referencia: ${escape(id)}</p><blockquote>${escape(segment.text)}</blockquote></section>`
      : `<p class="notice">Falta el fragmento de la referencia ${escape(id)}.</p>`;
  }).join('');
  const label = mode === 'draft' ? 'Borrador para revisión humana' : 'Copia de la versión aprobada por una persona';
  return {
    filename: `aulalista-actividad-${mode === 'draft' ? 'borrador-base' : 'aprobada'}-${revision}.html`,
    mime: 'text/html;charset=utf-8',
    content: `<!doctype html>
<html lang="es-MX">
<head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escape(content.title || 'Actividad para revisar')} · AulaLista</title>
<style>
@page { size: auto; margin: 18mm; }
* { box-sizing: border-box; }
body { max-width: 780px; margin: 2rem auto; padding: 0 1rem; color: #17212b; background: white; font: 16px/1.55 system-ui, sans-serif; }
h1 { font-size: 1.8rem; line-height: 1.2; }
h2 { font-size: 1.2rem; margin-top: 1.7rem; border-bottom: 1px solid #687583; }
h1, h2, h3 { break-after: avoid; }
p, li, blockquote, h1 { white-space: pre-wrap; overflow-wrap: anywhere; }
li { margin-bottom: .7rem; }
blockquote { margin: .5rem 0; border-left: 3px solid #687583; padding-left: 1rem; }
.notice { border: 2px solid #687583; padding: .8rem; }
.source { margin-bottom: 1.5rem; }
@media print { body { max-width: none; margin: 0; padding: 0; font-size: 11pt; } .screen-help { display: none; } p, li { orphans: 3; widows: 3; } }
</style></head>
<body>
<header><p>AulaLista · ${label}</p>
${demo ? '<p class="notice">Ejemplo sintético para probar el software. No es material curricular validado ni un resultado de un proveedor de IA.</p>' : ''}
<h1>${text(content.title)}</h1>
<p>${mode === 'draft' ? `Basado en la revisión guardada ${revision}. Incluye el texto actual, aunque no esté guardado. Esta copia no autoriza su publicación ni uso con el grupo.` : `Revisión aprobada ${revision}. Esta copia conserva esa versión; puede ser distinta del borrador actual. La aprobación no implica publicación.`}</p></header>
<main>
${missingSources ? '<p class="notice">No hay suficiente fuente local. Verifica las referencias antes de autorizar la actividad.</p>' : ''}
${missingContent ? '<p class="notice">Falta contenido esencial. Completa objetivo, pasos y evaluación antes de autorizar la actividad.</p>' : ''}
<section><h2>Objetivo</h2><p>${text(content.objective)}</p></section>
<section><h2>Materiales</h2>${list(content.materials)}</section>
<section><h2>Pasos de la actividad</h2>${list(content.steps, true)}</section>
<section><h2>Evaluación y respuestas previstas</h2><p>${text(content.assessment)}</p></section>
<section><h2>Uso sin conexión</h2>
<p>Guarda este archivo en el dispositivo antes de desconectarte. Ábrelo con un navegador para leerlo o imprimirlo. No requiere conexión para mostrar el texto incluido.</p>
<p>Prepara los materiales de la lista. Las imágenes, videos, anexos, enlaces y el PDF original no se incluyen. Si la actividad los requiere, consíguelos por separado antes de la clase o pide una adaptación.</p>
<p>Este archivo no genera actividades, no guarda cambios en AulaLista y no sincroniza. Para guardar o aprobar en la aplicación, necesitas acceso al servidor de AulaLista; la asistencia que use servicios externos también requiere conexión.</p>
<p class="screen-help">Para imprimir o guardar un PDF, usa Imprimir en el menú del navegador. Revisa las páginas en la vista previa.</p></section>
<section><h2>Fuentes conservadas</h2><p>Documento de origen: ${escape(source.document_id)}</p>
<p>Los siguientes fragmentos conservan el contexto de origen. No verifican por sí solos las adaptaciones hechas en el borrador.</p>
${references || '<p>No se indicaron referencias de origen.</p>'}</section>
</main></body></html>`,
  };
}

export function downloadActivityFile(file: ActivityFile): { ok: boolean; message: string } {
  let url: string | undefined;
  let anchor: HTMLAnchorElement | undefined;
  try {
    url = URL.createObjectURL(new Blob([file.content], { type: file.mime }));
    anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = file.filename;
    document.body.append(anchor);
    anchor.click();
    return { ok: true, message: 'Se solicitó la descarga. Verifica el archivo en Descargas y ábrelo antes de la clase.' };
  } catch {
    return { ok: false, message: 'El navegador no pudo iniciar la descarga. Tu actividad sigue en el editor. Reintenta en un navegador que permita descargar archivos.' };
  } finally {
    anchor?.remove();
    if (url) setTimeout(() => URL.revokeObjectURL(url!), 1000);
  }
}
