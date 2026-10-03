"""S06 adapter checks use local PDFs; injected failures are explicitly scoped."""
import copy
import io

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from curriculum import document_extraction as extraction
from curriculum.interpretation_schema import (
    INSUFFICIENT_SOURCE, InterpretationSchemaError, validate_interpretation,
)
from curriculum.interpretation_service import dossier_to_interpretation, interpret_source
from curriculum.source_interpreter import (
    CurriculumSourceInterpreter, ImportDossier, InterpretedField, SourceReference,
    SourcePdfReadError, InterpretationCancelledError, InterpretationTimeoutError,
)
from test_t15_curriculum_import import make_minimal_pdf


def column_pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({
        NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    cells = [(40, 740, 'Proyecto: El patio'),
             (40, 700, 'Momento'), (40, 675, 'Inicio'), (40, 650, 'Cierre'),
             (280, 700, 'Actividad'), (280, 675, 'Leer el cuento.'), (280, 650, 'Compartir ideas.')]
    stream = DecodedStreamObject()
    stream.set_data('\n'.join(f'BT /F1 12 Tf 1 0 0 1 {x} {y} Tm ({text}) Tj ET'
                              for x, y, text in cells).encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_columns_keep_exact_s02_segments_and_original_dossier():
    content = column_pdf()
    extracted = extraction.extract_document(content)
    dossier = CurriculumSourceInterpreter.prepare(content)
    before = copy.deepcopy(dossier)
    result = dossier_to_interpretation(dossier, [p.raw_text for p in extracted.pages], extraction=extracted)
    assert dossier == before
    assert result == interpret_source(content)
    assert result['schema_version'] == 2
    assert result['source_segments'] == extracted.source_segments
    assert result['source_segments'] == interpret_source(content)['source_segments']
    details = result['diagnostics']['source_extraction']
    assert details['status'] == 'complete'
    assert details['requires_review'] is True
    assert details['warnings'] == extracted.to_dict()['warnings']
    page = details['pages'][0]
    assert page['method'] == 'pypdf-layout'
    assert page['raw_text'].index('Cierre') < page['raw_text'].index('Actividad')
    row = next(s for s in result['source_segments'] if s['text'].startswith('Inicio'))
    assert 'Leer el cuento.' in row['text']
    assert row['kind'] == 'table_row_candidate'
    for segment in result['source_segments']:
        assert page['text'][segment['text_start']:segment['text_end']] == segment['text']
    assert result['draft']['approval_status'] == 'pending'
    assert result['draft']['revision'] == 1


@pytest.mark.parametrize('failed', [False, True])
def test_empty_or_failed_middle_page_keeps_page_three_and_warning(monkeypatch, failed):
    content = make_minimal_pdf(['Proyecto: El patio', '', 'Grado: 3ro'])
    if failed:
        original = extraction._extract_page
        def extract_page(page, number):
            if number == 2:
                return extraction.ExtractedPage(2, '', '', 'failed', 'none', ('No se pudo leer la página 2.',))
            return original(page, number)
        monkeypatch.setattr(extraction, '_extract_page', extract_page)
    result = interpret_source(content)
    details = result['diagnostics']['source_extraction']
    assert details['status'] == 'partial'
    assert [p['page'] for p in details['pages']] == [1, 2, 3]
    assert [p['status'] for p in details['pages']] == ['extracted', 'failed' if failed else 'empty', 'extracted']
    assert [s['page'] for s in result['source_segments']] == [1, 3]
    assert any(w['page'] == 2 for w in result['diagnostics']['source_warnings'])
    assert next(f for f in result['fields'] if f['key'] == 'grado')['value'] == '3'
    assert result['draft']['approval_status'] == 'pending'
    assert result['draft']['status'] == INSUFFICIENT_SOURCE


def test_layout_failure_preserves_plain_text_and_requires_review(monkeypatch):
    from pypdf._page import PageObject
    original = PageObject.extract_text
    def extract_text(page, *args, **kwargs):
        if kwargs.get('extraction_mode') == 'layout':
            raise ValueError('injected layout failure')
        return original(page, *args, **kwargs)
    monkeypatch.setattr(PageObject, 'extract_text', extract_text)
    result = interpret_source(make_minimal_pdf(['Proyecto: El patio']))
    page = result['diagnostics']['source_extraction']['pages'][0]
    assert page['method'] == 'pypdf-plain'
    assert page['text'] == page['raw_text']
    assert 'texto lineal' in page['warnings'][0]
    assert next(f for f in result['fields'] if f['key'] == 'proyecto')['status'] == 'suggested'


def test_nonexistent_source_is_safe_and_does_not_enter_interpreter(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('The interpreter must not run without a source')
    monkeypatch.setattr(CurriculumSourceInterpreter, 'prepare', forbidden)
    with pytest.raises(SourcePdfReadError, match='Vuelve a cargar el PDF') as error:
        interpret_source(tmp_path / 'private-missing-file.pdf')
    assert str(tmp_path) not in str(error.value)


def test_truncated_pdf_is_rejected_before_legacy_parse(monkeypatch):
    content = make_minimal_pdf(['Proyecto: El patio'])
    def forbidden(*args, **kwargs):
        pytest.fail('Legacy parsing must follow S02 validation')
    monkeypatch.setattr(CurriculumSourceInterpreter, 'prepare', forbidden)
    with pytest.raises(SourcePdfReadError, match='cierre completo'):
        interpret_source(content[:-2])


def test_legacy_contract_keeps_page_anchors_and_does_not_acquire_layout():
    content = make_minimal_pdf(['Proyecto: El patio'])
    document = extraction.extract_document(content)
    dossier = CurriculumSourceInterpreter.prepare(content)
    result = dossier_to_interpretation(dossier, [p.raw_text for p in document.pages])
    assert result['schema_version'] == 1
    assert result['source_segments'] == [{'id': f'{document.document_id}:p1',
                                          'text': document.pages[0].raw_text, 'page': 1}]
    assert 'source_extraction' not in result['diagnostics']
    assert validate_interpretation(result) == result


@pytest.mark.parametrize('raw,layout', [('Inicio Leer Cierre Compartir', 'Inicio Compartir\nCierre Leer'),
                                       ('Semillas', 'Semillas\nSemillas')])
def test_unmappable_or_duplicate_quote_stays_unknown(raw, layout):
    document = extraction.ExtractedDocument('sha', (extraction.ExtractedPage(1, layout, raw, 'extracted', 'pypdf-layout', ()),))
    dossier = ImportDossier(source_sha256='sha', source_name='test.pdf', page_count=1,
                           general_fields={'proposito': InterpretedField('proposito', raw, evidence=[SourceReference('sha', 1, excerpt=raw)])})
    before = copy.deepcopy(dossier)
    result = dossier_to_interpretation(dossier, [raw], extraction=document)
    field = next(f for f in result['fields'] if f['key'] == 'proposito')
    assert field['status'] == 'unknown'
    assert field['value'] is None
    assert field['evidence_ids'] == []
    assert result['draft']['approval_status'] == 'pending'
    assert dossier == before


@pytest.mark.parametrize('mutate', [
    lambda p: p['source_segments'][0].update(text_start=True),
    lambda p: p['source_segments'][0].update(text_end=900),
    lambda p: p['source_segments'][0].update(id='absent-source'),
    lambda p: p['source_segments'][0].update(page=2),
    lambda p: p['diagnostics']['source_extraction']['pages'][0].update(text='Fuente falsa'),
    lambda p: p['diagnostics']['source_extraction']['pages'][0].update(page=True),
    lambda p: p['diagnostics']['source_extraction'].update(requires_review=False),
    lambda p: p['diagnostics']['source_extraction'].update(status='partial'),
])
def test_version_two_rejects_altered_offsets_pages_identity_and_review(mutate):
    result = interpret_source(column_pdf())
    mutate(result)
    with pytest.raises(InterpretationSchemaError):
        validate_interpretation(result)


@pytest.mark.parametrize('cancel', [True, False])
def test_cancellation_and_deadline_checked_inside_page_extraction(monkeypatch, cancel):
    from curriculum import interpretation_service as service
    content = make_minimal_pdf(['Proyecto: El patio', 'Grado: 3ro'])
    clock = [0.0]
    stopped = [False]
    original = extraction._extract_page
    def extract_page(page, number):
        assert number == 1
        result = original(page, number)
        stopped[0] = True
        clock[0] = 31.0
        return result
    monkeypatch.setattr(extraction, '_extract_page', extract_page)
    monkeypatch.setattr(service.time, 'monotonic', lambda: clock[0])
    with pytest.raises(InterpretationCancelledError if cancel else InterpretationTimeoutError):
        interpret_source(content, is_cancelled=lambda: cancel and stopped[0])


@pytest.mark.parametrize('pages,indices,accepted', [
    (['Propósito: Observar\nplantas'], [0, 1], True),
    (['Propósito: Observar\nOtro contenido\nplantas'], [0, 2], False),
    (['Propósito: Observar', 'plantas'], [0, 1], False),
])
def test_multiline_evidence_must_be_adjacent_and_on_one_page(pages, indices, accepted):
    document = extraction.ExtractedDocument('sha', tuple(
        extraction.ExtractedPage(number, text, text, 'extracted', 'pypdf-plain', ())
        for number, text in enumerate(pages, 1)))
    dossier = ImportDossier(source_sha256='sha', source_name='test.pdf', page_count=len(pages))
    result = dossier_to_interpretation(dossier, pages, extraction=document)
    field = next(f for f in result['fields'] if f['key'] == 'proposito')
    field.update(value='Observar plantas', status='extracted',
                 evidence_ids=[result['source_segments'][i]['id'] for i in indices])
    if accepted:
        assert validate_interpretation(result)['fields'] == result['fields']
    else:
        with pytest.raises(InterpretationSchemaError, match='no aparece'):
            validate_interpretation(result)


def test_extraction_with_wrong_document_identity_cannot_replace_dossier():
    dossier = ImportDossier(source_sha256='original', source_name='test.pdf', page_count=1)
    document = extraction.ExtractedDocument('different', (
        extraction.ExtractedPage(1, 'Proyecto: Otro', 'Proyecto: Otro', 'extracted', 'pypdf-plain', ()),))
    with pytest.raises(InterpretationSchemaError, match='no corresponde'):
        dossier_to_interpretation(dossier, ['Proyecto: Otro'], extraction=document)
