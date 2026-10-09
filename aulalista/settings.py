import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SPRINT_PERSISTENCE_PATH = os.environ.get("AULALISTA_DRAFTS_DB_PATH")

SECRET_KEY = "aulalista-t01-local-development-only"
DEBUG = True
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("AULALISTA_ALLOWED_HOSTS", "*").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    "taggit",
    "health",
    "curriculum",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]

ROOT_URLCONF = "aulalista.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "aulalista.wsgi.application"
ASGI_APPLICATION = "aulalista.asgi.application"

_sqlite_database_path = os.environ.get("AULALISTA_DB_PATH")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(_sqlite_database_path) if _sqlite_database_path else BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            # WAL permits concurrent readers while SQLite serializes writers.
            # The timeout is finite so lock contention remains observable.
            "timeout": 5,
            "init_command": (
                "PRAGMA journal_mode=WAL;"
                "PRAGMA synchronous=NORMAL;"
                "PRAGMA busy_timeout=5000"
            ),
        },
    }
}

CACHES = {
    "default": {
        # T05 targets the initial single-process local node. A shared cache is
        # required before deploying multiple workers or nodes.
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "aulalista-local-cache",
    }
}

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Cancun"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = os.environ.get("AULALISTA_MEDIA_ROOT", str(BASE_DIR / "media"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# The only real login in this project is Wagtail's admin login. Without this,
# redirect_to_login() sends anonymous users to the nonexistent /accounts/login/.
LOGIN_URL = "/cms/login/"

WAGTAIL_SITE_NAME = "AulaLista"
WAGTAILADMIN_BASE_URL = "http://localhost:8000"
# The operator supplies the address other devices can reach on the LAN. The
# node deliberately does not inspect interfaces or infer a possibly-wrong IP.
AULALISTA_LAN_URL = os.environ.get("AULALISTA_LAN_URL", "").strip()

# Local LLM used only for curriculum-import staging proposals (never for the
# student path, grading or publishing). Defaults match a stock Ollama install.
AULALISTA_OLLAMA_URL = os.environ.get("AULALISTA_OLLAMA_URL", "http://localhost:11434")
AULALISTA_LLM_MODEL = os.environ.get("AULALISTA_LLM_MODEL", "qwen2.5:14b")

# Maximum upload size for curriculum PDF imports (25 MiB)
CURRICULUM_MAX_UPLOAD_SIZE_BYTES = int(
    os.environ.get("CURRICULUM_MAX_UPLOAD_SIZE_BYTES", 25 * 1024 * 1024)
)

# Adaptive review is opt-in. No implicit local model or cloud fallback.
AULALISTA_TEACHER_REVIEW_PROVIDER = os.environ.get("AULALISTA_TEACHER_REVIEW_PROVIDER", "pi_luna").strip()
# Experimental semantic projection is OFF unless explicitly selected for an A/B run.
AULALISTA_TEACHER_REVIEW_CONTEXT_MODE = os.environ.get("AULALISTA_TEACHER_REVIEW_CONTEXT_MODE", "complete").strip()

# Explicit local Codex route. No API key or credential is read by the application.
AULALISTA_LUNA_CLI_EXECUTABLE = os.environ.get("AULALISTA_LUNA_CLI_EXECUTABLE", "")
AULALISTA_LUNA_RUNTIME_REVIEW = os.environ.get("AULALISTA_LUNA_RUNTIME_REVIEW", "")
AULALISTA_LUNA_ATTEMPT_DIR = os.environ.get("AULALISTA_LUNA_ATTEMPT_DIR", str(BASE_DIR / ".runtime" / "luna"))
AULALISTA_LUNA_LIVE_ENABLED = os.environ.get("AULALISTA_LUNA_LIVE_ENABLED", "") == "1"
AULALISTA_LUNA_TIMEOUT_SECONDS = int(os.environ.get("AULALISTA_LUNA_TIMEOUT_SECONDS", "30"))

# Separate Pi 0.84.4 route; never inferred from Luna/Codex selection or login.
AULALISTA_PI_NODE_EXECUTABLE = os.environ.get("AULALISTA_PI_NODE_EXECUTABLE", "")
AULALISTA_PI_PACKAGE_DIR = os.environ.get("AULALISTA_PI_PACKAGE_DIR", "")
AULALISTA_PI_AGENT_DIR = os.environ.get("AULALISTA_PI_AGENT_DIR", "")
AULALISTA_PI_CATALOG_FILE = os.environ.get("AULALISTA_PI_CATALOG_FILE", "")
AULALISTA_PI_ISOLATION_LAUNCHER = os.environ.get("AULALISTA_PI_ISOLATION_LAUNCHER", "")
AULALISTA_PI_RUNTIME_REVIEW = os.environ.get("AULALISTA_PI_RUNTIME_REVIEW", "")
AULALISTA_PI_ATTEMPT_DIR = os.environ.get("AULALISTA_PI_ATTEMPT_DIR", str(BASE_DIR / ".runtime" / "pi-luna"))
AULALISTA_PI_LIVE_ENABLED = os.environ.get("AULALISTA_PI_LIVE_ENABLED", "") == "1"
AULALISTA_PI_TIMEOUT_SECONDS = int(os.environ.get("AULALISTA_PI_TIMEOUT_SECONDS", "30"))

# Historical explicit Gemini HIGH route. Luna is selected above; no fallback. No credentials are read/copied by the application;
# the official, already-authenticated CLI manages its own cached sign-in.
AULALISTA_GEMINI_MODEL = os.environ.get("AULALISTA_GEMINI_MODEL", "gemini-3.8-flash-high")
AULALISTA_GEMINI_AGY_LAUNCHER = os.environ.get("AULALISTA_GEMINI_AGY_LAUNCHER", "")
AULALISTA_GEMINI_AGY_AGENT_FILE = os.environ.get("AULALISTA_GEMINI_AGY_AGENT_FILE", "")
AULALISTA_GEMINI_ATTEMPT_DIR = os.environ.get("AULALISTA_GEMINI_ATTEMPT_DIR", str(BASE_DIR / ".runtime" / "gemini"))
AULALISTA_GEMINI_LIVE_ENABLED = os.environ.get("AULALISTA_GEMINI_LIVE_ENABLED", "") == "1"
AULALISTA_GEMINI_TIMEOUT_SECONDS = int(os.environ.get("AULALISTA_GEMINI_TIMEOUT_SECONDS", "90"))
