"""Local authored PDFs exercise pypdf itself; no provider or pedagogy claims."""

import io
from unittest.mock import patch

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def positioned_pdf(*pages, password=None):
    writer = PdfWriter()
    font = DictionaryObject({
        NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'),
        NameObject('/BaseFont'): NameObject('/Helvetica'),
        NameObject('/Encoding'): NameObject('/WinAnsiEncoding'),
    })
    for cells in pages:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)}),
        })
        commands = []
        for x, y, text in cells:
            escaped = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            commands.append(f'BT /F1 12 Tf 1 0 0 1 {x} {y} Tm ({escaped}) Tj ET')
        stream = DecodedStreamObject()
        stream.set_data('\n'.join(commands).encode('cp1252'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    if password:
        writer.encrypt(password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


TABLE = [
    (40, 740, 'SESIÓN 1'),
    (40, 700, 'Momento'), (40, 675, 'Inicio'), (40, 650, 'Cierre'),
    (280, 700, 'Actividad'), (280, 675, 'Leer el cuento.'), (280, 650, 'Compartir ideas.'),
]


def test_reproduce_column_major_pdf_reading_order():
    page = PdfReader(io.BytesIO(positioned_pdf(TABLE))).pages[0]
    plain = page.extract_text()
    layout = page.extract_text(extraction_mode='layout', layout_mode_space_vertically=False)
    assert plain.index('Cierre') < plain.index('Actividad')
    assert 'Inicio' not in plain.splitlines()[plain.splitlines().index('Leer el cuento.')]
    assert any('Inicio' in line and 'Leer el cuento.' in line for line in layout.splitlines())
    assert any('Cierre' in line and 'Compartir ideas.' in line for line in layout.splitlines())

from curriculum.document_extraction import (
    DocumentExtractionCancelled,
    DocumentExtractionError,
    extract_document,
)
from curriculum.source_segments import extracted_page_segments


def test_table_rows_headings_and_every_page_have_stable_literal_references():
    content = positioned_pdf(TABLE, [], [(40, 700, 'Proyecto: El patio')])
    result = extract_document(content)
    assert result.status == 'partial'
    assert [page.page for page in result.pages] == [1, 2, 3]
    assert [page.status for page in result.pages] == ['extracted', 'empty', 'extracted']
    assert result.pages[0].method == 'pypdf-layout'
    assert result.pages[0].raw_text.index('Cierre') < result.pages[0].raw_text.index('Actividad')
    rows = [s for s in result.source_segments if s['kind'] == 'table_row_candidate']
    assert [s['text'].split('  ')[0] for s in rows] == ['Momento', 'Inicio', 'Cierre']
    assert 'Leer el cuento.' in rows[1]['text']
    assert 'Compartir ideas.' in rows[2]['text']
    headings = [s['text'] for s in result.source_segments if s['kind'] == 'heading_candidate']
    assert headings == ['SESIÓN 1', 'Proyecto: El patio']
    assert result.pages[1].warnings and 'página 2' in result.pages[1].warnings[0]
    assert result.source_segments == extract_document(content).source_segments
    for segment in result.source_segments:
        page = result.pages[segment['page'] - 1]
        assert page.text[segment['text_start']:segment['text_end']] == segment['text']
    payload = result.to_dict()
    assert payload['page_count'] == 3
    assert payload['requires_review'] is True
    assert payload['source_segments'] == result.source_segments
    assert payload['pages'][1]['status'] == 'empty'


def test_repeated_text_on_different_pages_has_distinct_ids():
    content = positioned_pdf([(40, 700, 'Leer.')], [(40, 700, 'Leer.')])
    segments = extract_document(content).source_segments
    assert [s['text'] for s in segments] == ['Leer.', 'Leer.']
    assert len({s['id'] for s in segments}) == 2


def test_changed_text_representation_or_document_never_reuses_ids():
    original = extracted_page_segments('Inicio\nLeer.', 'document-a', 1)
    changed = extracted_page_segments('Inicio\n Leer.', 'document-a', 1)
    other_document = extracted_page_segments('Inicio\nLeer.', 'document-b', 1)
    assert original[0]['id'] != changed[0]['id']
    assert original[0]['id'] != other_document[0]['id']
    assert original[0]['id'] == extracted_page_segments('Inicio\nLeer.', 'document-a', 1)[0]['id']


def test_crlf_unicode_and_indentation_preserve_exact_offsets():
    text = '  SESIÓN 3\r\n\r\n\tInicio\tLeer en náhuatl.  \r\n'
    segments = extracted_page_segments(text, 'document-a', 7)
    assert [s['text'] for s in segments] == ['SESIÓN 3', 'Inicio\tLeer en náhuatl.']
    assert [s['kind'] for s in segments] == ['heading_candidate', 'table_row_candidate']
    assert [text[s['text_start']:s['text_end']] for s in segments] == ['SESIÓN 3', 'Inicio\tLeer en náhuatl.']
    assert all(s['page'] == 7 for s in segments)


def test_bad_page_remains_visible_and_later_page_keeps_its_number():
    content = positioned_pdf([(40, 700, 'Primera')], [(40, 700, 'Segunda')], [(40, 700, 'Tercera')])
    from pypdf._page import PageObject
    original = PageObject.extract_text

    def broken_second_page(page, *args, **kwargs):
        if original(page).strip() == 'Segunda':
            raise ValueError('private parser detail')
        return original(page, *args, **kwargs)

    with patch.object(PageObject, 'extract_text', broken_second_page):
        result = extract_document(content)
    assert result.status == 'partial'
    assert [page.status for page in result.pages] == ['extracted', 'failed', 'extracted']
    assert result.pages[1].text == ''
    assert [s['page'] for s in result.source_segments] == [1, 3]
    assert result.source_segments[-1]['text'] == 'Tercera'
    assert 'página 2' in result.pages[1].warnings[0]
    assert 'private parser detail' not in str(result.to_dict())


@pytest.mark.parametrize('layout_failure', ['exception', 'missing', 'duplicate', 'changed'])
def test_layout_failure_keeps_plain_text_and_explains_fallback(layout_failure):
    from pypdf._page import PageObject
    original = PageObject.extract_text

    def unreliable_layout(page, *args, **kwargs):
        if kwargs.get('extraction_mode') == 'layout':
            if layout_failure == 'exception':
                raise KeyError('private detail')
            return {'missing': 'Leer', 'duplicate': 'Leer. Leer.', 'changed': 'Otra cosa.'}[layout_failure]
        return original(page, *args, **kwargs)

    with patch.object(PageObject, 'extract_text', unreliable_layout):
        result = extract_document(positioned_pdf([(40, 700, 'Leer.')]))
    assert result.status == 'complete'
    assert result.pages[0].method == 'pypdf-plain'
    assert result.pages[0].text == result.pages[0].raw_text == 'Leer.'
    assert result.pages[0].warnings
    assert 'página 1' in result.pages[0].warnings[0]


def test_entirely_blank_pdf_reports_unreadable_without_inventing_evidence():
    result = extract_document(positioned_pdf([], []))
    assert result.status == 'unreadable'
    assert len(result.pages) == 2
    assert result.source_segments == []
    assert all(page.warnings for page in result.pages)


@pytest.mark.parametrize('content,filename,message', [
    (b'plain text', 'archivo.txt', 'admite archivos PDF'),
    (b'plain text', 'archivo.pdf', 'PDF válido'),
    (b'%PDF-corrupt', 'archivo.pdf', 'No se pudo abrir'),
])
def test_unsupported_or_corrupt_upload_has_actionable_spanish_error(content, filename, message):
    with pytest.raises(DocumentExtractionError, match=message):
        extract_document(content, filename=filename)


def test_encrypted_pdf_is_explicitly_rejected():
    with pytest.raises(DocumentExtractionError, match='protegido'):
        extract_document(positioned_pdf(TABLE, password='local-fixture-password'))


def test_empty_pdf_is_explicitly_rejected():
    with pytest.raises(DocumentExtractionError, match='no contiene páginas'):
        extract_document(positioned_pdf())


def test_limits_reject_whole_document_without_silent_truncation():
    content = positioned_pdf(TABLE, TABLE)
    with pytest.raises(DocumentExtractionError, match='límite de páginas'):
        extract_document(content, max_pages=1)
    with pytest.raises(DocumentExtractionError, match='tamaño permitido'):
        extract_document(content, max_bytes=len(content) - 1)


def test_cancellation_propagates_without_returning_an_incomplete_document():
    checks = iter([False, False, True])
    with pytest.raises(DocumentExtractionCancelled, match='cancelada'):
        extract_document(positioned_pdf(TABLE, TABLE), is_cancelled=lambda: next(checks))


def test_plain_single_column_pdf_remains_complete_and_requires_review():
    result = extract_document(positioned_pdf([(40, 740, 'SESIÓN 3'), (40, 700, 'Leer el cuento.')]), filename='PLAN.PDF')
    assert result.status == 'complete'
    assert [s['text'] for s in result.source_segments] == ['SESIÓN 3', 'Leer el cuento.']
    assert result.to_dict()['requires_review'] is True


@pytest.mark.parametrize('tail', [b'%%EO', b'%%E', b'%%', b'%', b''])
def test_truncated_eof_is_rejected_instead_of_silently_repaired(tail):
    content = positioned_pdf(TABLE)
    truncated = content[:content.rfind(b'%%EOF')] + tail
    with pytest.raises(DocumentExtractionError, match='cierre completo'):
        extract_document(truncated)


@pytest.mark.parametrize('cut', ['middle', 'xref'])
def test_truncated_body_or_cross_reference_has_explicit_error(cut):
    content = positioned_pdf(TABLE)
    end = len(content) // 2 if cut == 'middle' else content.index(b'xref')
    with pytest.raises(DocumentExtractionError):
        extract_document(content[:end])


@pytest.mark.parametrize('ending', [b'', b'\n', b'\r\n', b' \t\r\n\x00\x0c'])
def test_complete_eof_accepts_pdf_whitespace_without_changing_references(ending):
    content = positioned_pdf(TABLE).rstrip() + ending
    result = extract_document(content)
    assert result.status == 'complete'
    assert result.pages[0].page == 1
    for segment in result.source_segments:
        assert result.pages[0].text[segment['text_start']:segment['text_end']] == segment['text']


def test_exact_limits_include_blank_pages_and_preserve_last_page_reference():
    content = positioned_pdf(TABLE, [], [(40, 700, 'Ultima')])
    result = extract_document(content, max_bytes=len(content), max_pages=3)
    assert [page.page for page in result.pages] == [1, 2, 3]
    assert [page.status for page in result.pages] == ['extracted', 'empty', 'extracted']
    assert result.status == 'partial'
    assert result.source_segments[-1]['page'] == 3
    assert result.source_segments[-1]['text'] == 'Ultima'
    assert result.source_segments == extract_document(content).source_segments


def test_byte_limit_rejects_before_constructing_parser():
    content = positioned_pdf(TABLE)
    with patch('curriculum.document_extraction.PdfReader') as reader:
        with pytest.raises(DocumentExtractionError, match='tamaño permitido'):
            extract_document(content, max_bytes=len(content) - 1)
    reader.assert_not_called()


def test_page_limit_counts_blank_pages_and_rejects_before_text_extraction():
    from pypdf._page import PageObject

    content = positioned_pdf(TABLE, [], [])
    with patch.object(PageObject, 'extract_text') as extract_text:
        with pytest.raises(DocumentExtractionError, match='límite de páginas'):
            extract_document(content, max_pages=2)
    extract_text.assert_not_called()


def test_encryption_with_empty_user_password_is_still_explicitly_rejected():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt('', owner_password='local-owner-password')
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(DocumentExtractionError, match='protegido'):
        extract_document(buffer.getvalue())


def test_non_whitespace_after_eof_has_explicit_error():
    with pytest.raises(DocumentExtractionError, match='datos posteriores'):
        extract_document(positioned_pdf(TABLE) + b'partial incremental update')
