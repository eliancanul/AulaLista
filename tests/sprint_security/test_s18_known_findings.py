import json

import pytest

from curriculum.curriculum_import import identify_topics
from curriculum.source_interpreter import CurriculumSourceInterpreter
from curriculum.verification import verify_curriculum_dossier
from test_s18_curriculum import synthetic_pdf


@pytest.mark.xfail(strict=True, reason="S18-F01: value outside cited excerpt is marked checked")
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


@pytest.mark.xfail(strict=True, reason="S18-F02: legacy topic adapter accepts invented title and page")
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
