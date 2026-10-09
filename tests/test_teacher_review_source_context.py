"""Synthetic-only complete digital-source context; no provider inference."""
import copy
import hashlib
import io
import json
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client
from django.urls import reverse
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from curriculum.models import CurriculumImportJob
from curriculum.teacher_review_source import source_document_context
from curriculum.teacher_review_provider import ReviewProviderError
from test_teacher_review import ready_job, start, save, advance, ask_first
from helpers import MINIMAL_VALID_PDF_BYTES

pytestmark = pytest.mark.django_db


class OneReadSource:
    def __init__(self, data):
        self.data, self.opens = data, 0

    def open(self, mode):
        assert mode == "rb"
        self.opens += 1
        assert self.opens == 1, "Do not reopen mutable source after its SHA check"
        return io.BytesIO(self.data)


def context_inputs(data=MINIMAL_VALID_PDF_BYTES, count=1):
    source = OneReadSource(data)
    return SimpleNamespace(pdf=source), SimpleNamespace(
        source_sha256=hashlib.sha256(data).hexdigest(), page_count=count)


def full_source_pdf():
    writer = PdfWriter()
    for lines in [
        ["Proyecto: Parque sintetico", "Sesion 1: Mapa inicial", "Inicio: Escuchar.",
         "Desarrollo: Dibujar.", "Actividad 1: Revisar el anexo 3."],
        ["ANEXO 3", "Mapa revisado", "Cuerpo completo de la lamina para comparar.",
         "  Texto literal con espacios conservados.  "],
        [],
    ]:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                 NameObject('/Subtype'): NameObject('/Type1'),
                                 NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        stream = DecodedStreamObject()
        stream.set_data(('BT /F1 12 Tf 40 750 Td 20 TL ' +
                         ' '.join('(' + line + ') Tj T*' for line in lines) +
                         ' ET').encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO(); writer.write(output)
    return output.getvalue()


def test_every_physical_page_text_is_exact_and_image_gap_explicit():
    data = full_source_pdf()
    job, dossier = context_inputs(data, 3)
    result = source_document_context(job, dossier)
    expected = [page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages]
    assert [page["page_number"] for page in result["pages"]] == [1, 2, 3]
    assert [page["text"] for page in result["pages"]] == expected
    assert [page["status"] for page in result["pages"]] == ["text", "text", "no_digital_text"]
    assert result["missing_text_pages"] == [3]
    assert result["source_sha256"] == hashlib.sha256(data).hexdigest()
    assert result["page_count"] == 3 and result["ocr_performed"] is False
    assert "Mapa revisado" in result["pages"][1]["text"]
    assert "Cuerpo completo de la lamina" in result["pages"][1]["text"]
    assert job.pdf.opens == 1


@pytest.mark.django_db(transaction=True)
def test_provider_gets_whole_source_after_claim_commit_without_mutating_dossier(monkeypatch):
    user = get_user_model().objects.create_user('full-source-context', is_staff=True)
    client = Client(); client.force_login(user)
    data = full_source_pdf()
    assert client.post(reverse('tutor-import-upload'), {
        'pdf': SimpleUploadedFile('synthetic-source.pdf', data, content_type='application/pdf')}).status_code == 302
    job = CurriculumImportJob.objects.get(created_by=user)
    assert job.has_valid_ready_dossier()
    before = copy.deepcopy(job.interpretation_dossier)
    real_reader = PdfReader
    def reader(source):
        assert not connection.in_atomic_block
        assert source.getvalue() == data
        return real_reader(source)
    monkeypatch.setattr('curriculum.teacher_review_source.PdfReader', reader)
    captured = []
    def provider(context):
        captured.append(context)
        assert context['dossier'] == before
        assert 'Mapa revisado' in context['source_document']['pages'][1]['text']
        assert 'Cuerpo completo de la lamina' in context['source_document']['pages'][1]['text']
        assert context['source_document']['missing_text_pages'] == [3]
        return ask_first(context)
    review = start(job, user, provider)
    assert len(captured) == 1 and review.state['status'] == 'asking'
    job.refresh_from_db()
    assert job.interpretation_dossier == before
    assert not job.is_approved
    assert all(ref.confirmed_page is None for session in job.get_interpretation_dossier().sessions
               for ref in session.annex_references)


def test_source_change_is_rejected_before_pdf_parsing(monkeypatch):
    job, dossier = context_inputs()
    job.pdf.data = b'different synthetic bytes'
    monkeypatch.setattr('curriculum.teacher_review_source.PdfReader',
                        lambda _: pytest.fail('Changed source must not be parsed'))
    with pytest.raises(ReviewProviderError, match='source_context_changed'):
        source_document_context(job, dossier)


def test_page_count_change_is_rejected():
    job, dossier = context_inputs(count=2)
    with pytest.raises(ReviewProviderError, match='source_context_changed'):
        source_document_context(job, dossier)


def test_page_extraction_error_stays_explicit_without_exception_details(monkeypatch):
    class GoodPage:
        def extract_text(self): return 'Exact first-page text\n'
    class BadPage:
        def extract_text(self): raise ValueError('PRIVATE_ERROR_SENTINEL')
    class EmptyPage:
        def extract_text(self): return None
    job, dossier = context_inputs(full_source_pdf(), 3)
    monkeypatch.setattr('curriculum.teacher_review_source.PdfReader',
                        lambda _: SimpleNamespace(pages=[GoodPage(), BadPage(), EmptyPage()]))
    result = source_document_context(job, dossier)
    assert result['pages'] == [
        {'page_number': 1, 'text': 'Exact first-page text\n', 'status': 'text'},
        {'page_number': 2, 'text': None, 'status': 'extraction_unavailable'},
        {'page_number': 3, 'text': '', 'status': 'no_digital_text'},
    ]
    assert result['missing_text_pages'] == [2, 3]
    assert 'PRIVATE_ERROR_SENTINEL' not in json.dumps(result)


def test_oversize_source_never_reaches_provider_and_keeps_saved_answer(ready_job, monkeypatch):
    _, user, job = ready_job
    review = save(start(job, user, ask_first), user, 'Literal answer saved before source preparation.')
    class LargePage:
        def extract_text(self): return 'x' * 65
    monkeypatch.setattr('curriculum.teacher_review_source.MAX_SOURCE_TEXT_BYTES', 64)
    monkeypatch.setattr('curriculum.teacher_review_source.PdfReader',
                        lambda _: SimpleNamespace(pages=[LargePage()]))
    review = advance(review, user, lambda _: pytest.fail('No partial source may be sent'))
    assert review.state['error'] == 'gemini_full_context_too_large'
    assert review.state['turns'][0]['answer'] == 'Literal answer saved before source preparation.'
    assert review.generation_token is None


def test_source_change_after_claim_does_not_call_provider_or_lose_answer(ready_job, monkeypatch):
    _, user, job = ready_job
    review = save(start(job, user, ask_first), user, 'Retained literal answer.')
    def changed_source(current_job, dossier):
        current_job.pdf = OneReadSource(b'another synthetic source')
        return source_document_context(current_job, dossier)
    monkeypatch.setattr('curriculum.teacher_review.source_document_context', changed_source)
    review = advance(review, user, lambda _: pytest.fail('Changed bytes must not be sent'))
    assert review.state['error'] == 'source_context_changed'
    assert review.state['turns'][0]['answer'] == 'Retained literal answer.'
    assert review.generation_token is None
