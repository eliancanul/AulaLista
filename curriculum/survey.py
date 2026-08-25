"""Fixed, deterministic student survey questions and server-side validation.

The survey is pseudonymous by construction: answers are validated against
these definitions and stored without any link to turns, devices or names.
"""

MAX_OPEN_ANSWER_LENGTH = 500

STUDENT_SURVEY_QUESTIONS = [
    {
        "id": "claridad",
        "type": "choice",
        "prompt": "La actividad me pareció clara.",
        "choices": ["Sí", "Más o menos", "No"],
    },
    {
        "id": "pistas",
        "type": "choice",
        "prompt": "Las pistas me ayudaron a continuar.",
        "choices": ["Sí", "Más o menos", "No", "No las usé"],
    },
    {
        "id": "mas_actividades",
        "type": "choice",
        "prompt": "Me gustaría tener más actividades como esta.",
        "choices": ["Sí", "Más o menos", "No"],
    },
    {
        "id": "comentario",
        "type": "open",
        "prompt": "¿Qué cambiarías o agregarías? (opcional)",
        "required": False,
        "max_length": MAX_OPEN_ANSWER_LENGTH,
    },
]

CHOICE_QUESTIONS = tuple(
    question for question in STUDENT_SURVEY_QUESTIONS if question["type"] == "choice"
)
OPEN_QUESTIONS = tuple(
    question for question in STUDENT_SURVEY_QUESTIONS if question["type"] == "open"
)


class SurveyContractError(ValueError):
    """Raised when a submitted answer violates the survey contract."""


def validate_survey_answers(post_data):
    """Normalize a POST mapping into the stored answer structure.

    Returns a list of ``{"question_id", "choice"}`` for choice questions and
    ``{"question_id", "text"}`` for open questions. Raises
    ``SurveyContractError`` on any structural violation.
    """

    answers = []
    for question in STUDENT_SURVEY_QUESTIONS:
        raw = str(post_data.get(question["id"], "") or "").strip()
        if question["type"] == "choice":
            if not raw:
                raise SurveyContractError(
                    f"Falta responder la pregunta '{question['prompt']}'."
                )
            if raw not in question["choices"]:
                raise SurveyContractError(
                    f"La respuesta para '{question['prompt']}' no es una opción válida."
                )
            answers.append({"question_id": question["id"], "choice": raw})
            continue

        text = raw[: question["max_length"]]
        if question.get("required") and not text:
            raise SurveyContractError(
                f"La pregunta '{question['prompt']}' es obligatoria."
            )
        answers.append({"question_id": question["id"], "text": text})
    return answers


def survey_aggregate(responses):
    """Aggregate stored responses into counts per choice and open texts."""

    responses = list(responses)
    totals = {
        question["id"]: {choice: 0 for choice in question["choices"]}
        for question in CHOICE_QUESTIONS
    }
    open_texts = []
    for response in responses:
        for answer in response.answers or []:
            definition = next(
                (
                    question
                    for question in STUDENT_SURVEY_QUESTIONS
                    if question["id"] == answer.get("question_id")
                ),
                None,
            )
            if definition is None:
                continue
            if definition["type"] == "choice" and answer.get("choice") in totals[
                definition["id"]
            ]:
                totals[definition["id"]][answer["choice"]] += 1
            elif definition["type"] == "open" and str(answer.get("text", "")).strip():
                open_texts.append(str(answer["text"]).strip())
    return {"response_count": len(responses), "totals": totals, "open_texts": open_texts}
