"""Overview role attribution from labelled synthetic text; no semantic scoring."""
import copy
import io
import pytest
from pypdf import PdfReader
from curriculum.document_extraction import extract_document
from curriculum.interpretation_service import interpret_source, dossier_to_interpretation
from curriculum.interpretation_schema import validate_interpretation, InterpretationSchemaError, FIELD_QUESTIONS
from curriculum.source_interpreter import CurriculumSourceInterpreter
from test_t15_curriculum_import import make_minimal_pdf

SOURCE = 'Nombre del proyecto: El huerto\nPropósito: Observar hojas.\nFinalidad: Compartir hallazgos.\nMateriales: Papel.'


def field(payload, key):
    return next(f for f in payload['fields'] if f['key'] == key)


@pytest.mark.parametrize('key,expected', [('proyecto','El huerto'),('proposito','Observar hojas.'),('finalidad','Compartir hallazgos.')])
def test_explicit_overview_roles_remain_extracted(key, expected):
    baseline = interpret_source(make_minimal_pdf([SOURCE]))
    assert field(baseline, key)['status'] == 'extracted'
    assert field(baseline, key)['value'] == expected
    assert validate_interpretation(baseline) == baseline


@pytest.mark.parametrize('key', ['proyecto', 'proposito', 'finalidad'])
@pytest.mark.parametrize('cited', ['materials', 'all'])
def test_literal_value_from_materials_cannot_become_an_overview_role(key, cited):
    baseline = interpret_source(make_minimal_pdf([SOURCE]))
    candidate = copy.deepcopy(baseline)
    refs = [s['id'] for s in baseline['source_segments'] if cited == 'all' or 'Materiales:' in s['text']]
    field(candidate,key).update(value='Papel.', evidence_ids=refs)
    if key == 'proyecto':
        candidate['draft']['title'] = 'Papel.'
    with pytest.raises(InterpretationSchemaError):
        validate_interpretation(candidate, expected_document_id=baseline['document_id'], source_segments=baseline['source_segments'])


@pytest.mark.parametrize('key', ['proposito', 'finalidad'])
def test_projection_abstains_on_mutated_value_and_materials_quote(key):
    content = make_minimal_pdf([SOURCE])
    dossier = CurriculumSourceInterpreter.prepare(content)
    dossier.general_fields[key].value = 'Papel.'
    dossier.general_fields[key].evidence[0].excerpt = 'Materiales: Papel.'
    before = copy.deepcopy(dossier)
    pages = [page.extract_text() for page in PdfReader(io.BytesIO(content)).pages]
    result = dossier_to_interpretation(dossier, pages, extraction=extract_document(content))
    assert dossier == before
    assert field(result,key)['status'] == 'unknown'
    assert field(result,key)['value'] is None
    assert FIELD_QUESTIONS[key] in result['missing_questions']
    assert result['draft']['approval_status'] == 'pending'


def test_purpose_and_finality_are_not_interchangeable():
    baseline = interpret_source(make_minimal_pdf([SOURCE]))
    candidate = copy.deepcopy(baseline)
    field(candidate,'proposito').update(value='Compartir hallazgos.', evidence_ids=field(candidate,'finalidad')['evidence_ids'])
    with pytest.raises(InterpretationSchemaError):
        validate_interpretation(candidate)
