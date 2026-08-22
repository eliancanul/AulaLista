"""Deterministic T06 preparation contracts.

This module deliberately does not create StudentTurn rows or store answers.
"""

from dataclasses import dataclass
import re


class DistributionInputError(ValueError):
    """Raised when a preparation count is missing or outside the T06 contract."""


class CapacityOverflowError(ValueError):
    """Raised when a local queue would exceed capacity without authorization."""


@dataclass(frozen=True)
class CapacityReservation:
    requested_capacity: int
    remaining_capacity: int
    overflow: int


def _positive_integer(value, label):
    if isinstance(value, bool):
        raise DistributionInputError(f"{label} debe ser un entero positivo.")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        number = int(value.strip())
    else:
        raise DistributionInputError(f"{label} debe ser un entero positivo.")
    if number <= 0:
        raise DistributionInputError(f"{label} debe ser un entero positivo.")
    return number


def calculate_distribution(student_count, device_count):
    """Return deterministic balanced capacities, in local device order."""

    students = _positive_integer(student_count, "El número de estudiantes")
    devices = _positive_integer(device_count, "El número de dispositivos")
    if devices > students:
        raise DistributionInputError(
            "El número de dispositivos no puede superar al de estudiantes."
        )

    base, remainder = divmod(students, devices)
    return tuple(base + (1 if position < remainder else 0) for position in range(devices))


def validate_distribution(student_count, device_count, capacities):
    """Validate persisted capacities before a prepared session becomes active."""

    expected = calculate_distribution(student_count, device_count)
    try:
        actual = tuple(capacities)
    except TypeError as error:
        raise DistributionInputError("La distribución debe ser una secuencia.") from error
    if actual != expected:
        raise DistributionInputError("La distribución de dispositivos no es válida.")
    return actual


def ensure_capacity(assignment, requested_capacity, *, allow_overflow=False):
    """Check a local queue request without persisting a student turn or result."""

    requested = _positive_integer(
        requested_capacity,
        "La reserva de capacidad",
    )
    remaining = assignment.remaining_capacity
    if isinstance(remaining, bool) or not isinstance(remaining, int) or remaining < 0:
        raise DistributionInputError("La capacidad restante no puede ser negativa.")
    overflow = max(0, requested - remaining)
    if overflow and allow_overflow is not True:
        raise CapacityOverflowError(
            "La cola local no puede superar su capacidad sin autorización explícita de overflow."
        )
    return CapacityReservation(
        requested_capacity=requested,
        remaining_capacity=max(0, remaining - requested),
        overflow=overflow,
    )


# Public synonym for callers that describe the operation as distribution.
distribute_students = calculate_distribution
