"""curriculum.atlas.constants
--------------------------
Constantes de gobernanza, licenciamiento y privacidad para el Atlas SEP.
"""

from __future__ import annotations

# --- Estados del ciclo de vida del índice ---
INDEX_STATUS_UNINITIALIZED = "uninitialized"
INDEX_STATUS_READY = "ready"
INDEX_STATUS_INVALIDATED = "invalidated"

# --- Garantía de privacidad y modo offline ---
PRIVACY_GUARANTEE_OFFLINE = "OFFLINE_LOCAL_NO_EGRESS"

# --- Disclaimer pedagógico obligatorio ---
DISCLAIMER_RELEVANCE_NOT_TRUTH = (
    "La puntuación de relevancia refleja exclusivamente similitud léxica y estructural; "
    "NO constituye verdad pedagógica, respaldo fáctico ni certificación curricular automática."
)

# --- Licencias autorizadas para fuentes reales ---
APPROVED_REAL_LICENSES = {
    "SEP-CONALITEG-Uso-Educativo-Nacional",
    "CC-BY-NC-SA-4.0",
    "CC-BY-4.0",
    "Dominio-Publico-Gobierno-Mexico",
}

# --- Stop words en español para tokenización ---
SPANISH_STOP_WORDS = {
    "de", "la", "el", "en", "y", "a", "los", "las", "del", "se", "por", "con", "para",
    "un", "una", "unos", "unas", "su", "al", "lo", "como", "mas", "pero", "sus", "le",
    "ya", "o", "fue", "este", "ha", "si", "sobre", "entre", "cuando", "todo", "esta",
    "ser", "son", "dos", "tambien", "era", "muy", "hasta", "desde", "nos", "durante",
    "uno", "les", "ni", "contra", "otros", "ese", "eso", "ante", "ellos", "e", "esto",
    "mi", "antes", "algunos", "que", "es",
}
