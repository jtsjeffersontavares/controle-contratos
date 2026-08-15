from pathlib import Path
import os
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path: Path):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('\"').strip("'")
        os.environ.setdefault(key, value)


load_env_file(BASE_DIR / '.env')


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, '1' if default else '0').strip().lower()
    return value in {'1', 'true', 'yes', 'sim', 'on'}


SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'troque-esta-chave-antes-do-uso-em-producao')
DEBUG = env_bool('DJANGO_DEBUG', True)

allowed_hosts = [host.strip() for host in os.getenv('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost').split(',') if host.strip()]
for domain in [
    os.getenv('RENDER_EXTERNAL_HOSTNAME', ''),
    os.getenv('RENDER_EXTERNAL_URL', ''),
    os.getenv('RENDER_SERVICE_NAME', ''),
]:
    if not domain:
        continue
    hostname = domain.replace('https://', '').replace('http://', '').split('/')[0]
    if hostname and hostname not in allowed_hosts:
        allowed_hosts.append(hostname)
allowed_hosts.extend(['.onrender.com', 'onrender.com'])
ALLOWED_HOSTS = allowed_hosts

csrf_origins = [origin.strip() for origin in os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()]

def add_csrf_origin(origin: str):
    if origin and origin not in csrf_origins:
        csrf_origins.append(origin)

for host in ['localhost', '127.0.0.1']:
    for scheme in ['http', 'https']:
        add_csrf_origin(f'{scheme}://{host}')
        for port in ['8000', '8080', '3000']:
            add_csrf_origin(f'{scheme}://{host}:{port}')

for domain in [
    os.getenv('RENDER_EXTERNAL_HOSTNAME', ''),
    os.getenv('RENDER_EXTERNAL_URL', ''),
    os.getenv('RENDER_SERVICE_NAME', ''),
]:
    if not domain:
        continue
    if domain.startswith(('http://', 'https://')):
        origin = domain
    else:
        origin = f'https://{domain}'
    add_csrf_origin(origin)
if 'https://*.onrender.com' not in csrf_origins:
    add_csrf_origin('https://*.onrender.com')
CSRF_TRUSTED_ORIGINS = csrf_origins

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'contracts.apps.ContractsConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'contracts.middleware.CurrentUserMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
            'contracts.context_processors.system_context',
        ],
    },
}]
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DB_ENGINE = os.getenv('DB_ENGINE', '').strip().lower()
database_url = os.getenv('DATABASE_URL', '').strip()
parsed_database_url = urlparse(database_url) if database_url else None
uses_postgres = DB_ENGINE in {'postgres', 'postgresql'} or (
    parsed_database_url is not None and parsed_database_url.scheme in {'postgres', 'postgresql', 'postgresql+psycopg', 'postgresql+psycopg2'}
)

if uses_postgres:
    if parsed_database_url is not None:
        database_name = parsed_database_url.path.lstrip('/') or os.getenv('POSTGRES_DB', 'gestao_contratos')
        database_user = parsed_database_url.username or os.getenv('POSTGRES_USER', 'gestao_contratos')
        database_password = parsed_database_url.password or os.getenv('POSTGRES_PASSWORD', '')
        database_host = parsed_database_url.hostname or os.getenv('POSTGRES_HOST', 'db')
        database_port = str(parsed_database_url.port or os.getenv('POSTGRES_PORT', '5432'))
    else:
        database_name = os.getenv('POSTGRES_DB', 'gestao_contratos')
        database_user = os.getenv('POSTGRES_USER', 'gestao_contratos')
        database_password = os.getenv('POSTGRES_PASSWORD', '')
        database_host = os.getenv('POSTGRES_HOST', 'db')
        database_port = os.getenv('POSTGRES_PORT', '5432')

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': database_name,
            'USER': database_user,
            'PASSWORD': database_password,
            'HOST': database_host,
            'PORT': database_port,
            'CONN_MAX_AGE': int(os.getenv('POSTGRES_CONN_MAX_AGE', '60')),
        }
    }
else:
    sqlite_path = Path(os.getenv('SQLITE_PATH', 'db.sqlite3'))
    if not sqlite_path.is_absolute():
        sqlite_path = BASE_DIR / sqlite_path
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': sqlite_path,
            'OPTIONS': {'timeout': 30},
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage' if not DEBUG else 'django.contrib.staticfiles.storage.StaticFilesStorage'
MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', 'media'))
if not MEDIA_ROOT.is_absolute():
    MEDIA_ROOT = BASE_DIR / MEDIA_ROOT

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

FILE_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024 * 1024

SESSION_COOKIE_SECURE = env_bool('DJANGO_SECURE_COOKIES', False)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', False)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if env_bool('DJANGO_SECURE_SSL_REDIRECT', False) else None
USE_X_FORWARDED_HOST = env_bool('DJANGO_SECURE_SSL_REDIRECT', False)
SECURE_HSTS_SECONDS = int(os.getenv('DJANGO_HSTS_SECONDS', '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'gestao.contratos@localhost')
SYSTEM_NAME = os.getenv('SYSTEM_NAME', 'Gestão de Contratos — SDAP')
SYSTEM_ORGANIZATION = os.getenv('SYSTEM_ORGANIZATION', 'Subdiretoria de Apoio Administrativo')
