"""curriculum.atlas.exceptions
---------------------------
Jerarquía de excepciones especializadas del Atlas SEP.
"""

from __future__ import annotations


class AtlasError(Exception):
    """Excepción base del Atlas SEP."""


class AtlasSecurityError(AtlasError):
    """Error de seguridad, gobernanza o licencia."""


class AtlasPermissionError(AtlasSecurityError):
    """Falta permiso verificado para agregar una fuente real."""


class AtlasIntegrityError(AtlasSecurityError):
    """Discrepancia en la identidad, versión o hash SHA-256 de la fuente."""


class AtlasIndexError(AtlasError):
    """Error operativo en la estructura del índice del Atlas."""


class AtlasIndexNotReadyError(AtlasIndexError):
    """El índice no está construido o ha sido invalidado."""
