"""Fixed, deterministic star-rating survey for the local student path."""

STUDENT_SURVEY_QUESTIONS = [
    {
        "id": "rating",
        "type": "rating",
        "prompt": "¿Te gustó la dinámica?",
        "choices": [1, 2, 3, 4, 5],
    }
]


class SurveyContractError(ValueError):
    """Raised when a submitted star rating violates the survey contract."""


def validate_survey_answers(post_data):
    """Return the one validated numeric rating from a student POST."""

    raw = str(post_data.get("rating", "") or "").strip()
    try:
        rating = int(raw)
    except (TypeError, ValueError) as error:
        raise SurveyContractError("Selecciona una calificación de 1 a 5 estrellas.") from error
    if rating < 1 or rating > 5:
        raise SurveyContractError("La calificación debe estar entre 1 y 5 estrellas.")
    return rating


def survey_aggregate(responses):
    """Expose only the group average; never return a per-student answer."""

    ratings = [int(response.rating) for response in responses if response.rating is not None]
    average = sum(ratings) / len(ratings) if ratings else None
    return {
        "response_count": len(ratings),
        "rating_average": average,
        # Alias keeps callers readable while the canonical UI vocabulary stays
        # focused on the group average.
        "average_rating": average,
    }
