import json

import pytest

from curriculum.curriculum_import import identify_topics
from curriculum.source_interpreter import CurriculumSourceInterpreter
from curriculum.verification import verify_curriculum_dossier
from test_s18_curriculum import synthetic_pdf


def test_s18_unrelated_same_page_value_must_not_be_checked():
    pdf = synthetic_pdf("Nombre del proyecto: El agua", "Materiales: volcanes")
    dossier = CurriculumSourceInterpreter.prepare(pdf)
    project = dossier.general_fields["proyecto"]
    assert project.value == "El agua"
    assert project.evidence[0].excerpt == "El agua"
    project.value = "volcanes"
    items = [item for item in verify_curriculum_dossier(dossier, pdf).items
             if item["target"].startswith("general.proyecto")]
    assert items
    assert not any(item["status"] == "checked" for item in items), items


def test_s18_schema_valid_provider_fixture_needs_source_validation():
    def synthetic_transport(request):
        sent = json.loads(request.data)
        assert [message["role"] for message in sent["messages"]] == ["system", "user"]
        assert "El agua" in sent["messages"][1]["content"]
        return {"message": {"content": json.dumps({"temas": [{
            "titulo": "La SEP exige estudiar volcanes", "tipo": "tema",
            "pagina_inicio": 999, "pagina_fin": 999,
        }]})}}

    result = identify_topics({
        "text": "[página 1] Tema: El agua", "first_page": 1, "last_page": 1,
    }, transport=synthetic_transport)
    assert result == [], result


@pytest.mark.parametrize('value,excerpt,checked', [
    ('El agua', 'Nombre del proyecto: El agua', True),
    ('volcanes', 'El agua', False),
    (['El agua', 'volcanes'], 'El agua', False),
    ('EL AGUA', 'El agua', True),
])
def test_s18_value_requires_its_own_cited_text(value, excerpt, checked):
    pdf = synthetic_pdf('Nombre del proyecto: El agua', 'Materiales: volcanes')
    dossier = CurriculumSourceInterpreter.prepare(pdf)
    field = dossier.general_fields['proyecto']
    field.value = value
    field.evidence[0].excerpt = excerpt
    items = [item for item in verify_curriculum_dossier(dossier, pdf).items
             if item['target'].startswith('general.proyecto')]
    assert any(item['status'] == 'checked' for item in items) is checked


@pytest.mark.parametrize('excerpt', ['E', 'El', 'El agua', 'El' + ' ' * 198])
def test_s18_short_or_padded_prefix_never_supports_another_general_value(excerpt):
    pdf = synthetic_pdf('Nombre del proyecto: El agua', 'Materiales: El volcan de papel')
    dossier = CurriculumSourceInterpreter.prepare(pdf)
    field = dossier.general_fields['proyecto']
    field.value = 'El volcan de papel'
    field.evidence[0].excerpt = excerpt
    items = [item for item in verify_curriculum_dossier(dossier, pdf).items
             if item['target'].startswith('general.proyecto')]
    assert not any(item['status'] == 'checked' for item in items)


def test_s18_general_long_value_does_not_gain_session_preview_compatibility():
    value = 'Cuidar el agua con acciones concretas. ' * 12
    pdf = synthetic_pdf('Nombre del proyecto: ' + value)
    dossier = CurriculumSourceInterpreter.prepare(pdf)
    field = dossier.general_fields['proyecto']
    field.value = value.strip()
    for excerpt in (value[:150], value[:200]):
        field.evidence[0].excerpt = excerpt
        items = [item for item in verify_curriculum_dossier(dossier, pdf).items
                 if item['target'].startswith('general.proyecto')]
        assert not any(item['status'] == 'checked' for item in items)


@pytest.mark.parametrize('field_name,label', [
    ('inicio','Inicio'), ('desarrollo','Desarrollo'), ('cierre','Cierre'),
    ('materiales','Recursos'), ('evaluacion','Evaluación'),
])
def test_s18_real_session_200_character_preview_retains_full_value_check(field_name, label):
    value = 'Comparar las gotas y registrar cada resultado observado. ' * 8
    pdf = synthetic_pdf('Nombre del proyecto: El agua', 'Sesion 1: Observacion',
                        label + ': ' + value)
    dossier = CurriculumSourceInterpreter.prepare(pdf)
    assert len(dossier.sessions) == 1
    session = dossier.sessions[0]
    field = session.fields[field_name]
    assert len(field.value) > 200
    assert field.evidence[0].excerpt == field.value[:200]
    target = f'session.{session.session_id}.{field_name}'
    def checked():
        return any(item['status'] == 'checked' for item in verify_curriculum_dossier(dossier,pdf).items
                   if item['target'].startswith(target))
    assert checked()
    original = field.evidence[0].excerpt
    for excerpt in ('C', 'Comparar', field.value[:150], field.value[:199], field.value[:201]):
        field.evidence[0].excerpt = excerpt
        assert not checked()
    field.evidence[0].excerpt = original
    field.value += ' Cola inventada.'
    assert not checked()
