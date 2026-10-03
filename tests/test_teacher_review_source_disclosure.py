"""Self-contained new-review disclosure regression; generated PDF bytes only."""
import io
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory
from django.urls import reverse
from pypdf import PdfWriter
from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
from curriculum.models import CurriculumImportJob
from curriculum.views import tutor_import_interpretation


def synthetic_partial_pdf():
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    for lines in [
        ['Proyecto: Parque sintetico', 'Sesion 5: Escucha inicial',
         'Inicio: Escuchar sonidos.', 'Desarrollo: Registrar sonidos.',
         'Actividad 1: Dibujar lo escuchado.'],
        [],
        ['Sesion 9: Relato final', 'Desarrollo: Leer dibujos.',
         'Actividad 1: Narrar lo observado.'],
    ]:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        stream = DecodedStreamObject()
        stream.set_data(('BT /F1 12 Tf 40 750 Td 20 TL ' +
                         ' '.join('(' + line + ') Tj T*' for line in lines) +
                         ' ET').encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    out = io.BytesIO(); writer.write(out)
    return out.getvalue()


@pytest.mark.django_db
def test_new_review_keeps_source_warnings_and_context_provenance():
    user = get_user_model().objects.create_user('synthetic-disclosure', is_staff=True)
    client = Client(); client.force_login(user)
    upload = client.post(reverse('tutor-import-upload'), {
        'pdf': SimpleUploadedFile('synthetic-partial.pdf', synthetic_partial_pdf(),
                                  content_type='application/pdf')})
    assert upload.status_code == 302
    job = CurriculumImportJob.objects.get(created_by=user)
    assert job.has_valid_ready_dossier()
    dossier = job.get_interpretation_dossier()
    request = RequestFactory().get('/legacy-test-only/')
    request.user = user
    old = tutor_import_interpretation(request, job.pk).content.decode()
    response = client.get(reverse('tutor-import-interpretation', args=[job.pk]))
    assert response.status_code == 200
    new = response.content.decode()
    warning = dossier.page_warnings[2]
    assert warning in old
    assert warning in new
    for session in dossier.sessions:
        assert session.project_context['anchor']['excerpt'] in old
        assert session.project_context['anchor']['excerpt'] in new
        assert session.project_context['reason'] in new
        assert session.layout_notes in new
