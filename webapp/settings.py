from pathlib import Path
import os
import urllib.parse as urlparse
from dotenv import load_dotenv

# --------------------------------------------------
# BASE_DIR e .env
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# Carrega variáveis do .env (tanto no Mac quanto em produção, se existir)
load_dotenv()

# --------------------------------------------------
# Configurações básicas
# --------------------------------------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret-key-change-me")

DEBUG = os.getenv("DJANGO_DEBUG", "True") == "True"

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "simuladorls.onrender.com",
]

CSRF_TRUSTED_ORIGINS = [
    "https://simuladorls.onrender.com",
]

# --------------------------------------------------
# Aplicativos instalados
# --------------------------------------------------
INSTALLED_APPS = [
    # App do simulador web ANTES DO AUTH
    "simulador_web",

    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

]

# --------------------------------------------------
# Middleware
# --------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "webapp.urls"

# --------------------------------------------------
# Templates
# --------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],  # usamos apenas os templates dos apps
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "webapp.wsgi.application"

# --------------------------------------------------
# Banco de dados – APENAS Postgres via DATABASE_URL
# --------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não definido. "
        "Configure a URL do Postgres no .env (Mac) ou nas variáveis de ambiente (Render)."
    )

urlparse.uses_netloc.append("postgres")
url = urlparse.urlparse(DATABASE_URL)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": url.path[1:],  # remove a barra inicial
        "USER": url.username,
        "PASSWORD": url.password,
        "HOST": url.hostname,
        "PORT": url.port or 5432,
    }
}

# --------------------------------------------------
# Validação de senha
# --------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# --------------------------------------------------
# Localização
# --------------------------------------------------
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------
# Arquivos estáticos (Render)
# --------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGOUT_REDIRECT_URL = "/"


# ============================
# EMAIL (envio de leads)
# ============================

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True

EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL")

