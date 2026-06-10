import os


def env(name, default=None):
    value = os.getenv(name)
    return value if value not in (None, "") else default


SECRET_KEY = env("DJANGO_SECRET_KEY", "local-dev-only")
INSTALLED_APPS = []
USE_TZ = True
TIME_ZONE = env("TIME_ZONE", "UTC")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
    "panda": {
        "ENGINE": env("PANDA_DB_ENGINE", "django.db.backends.postgresql"),
        "HOST": env("PANDA_DB_HOST", "pandadb01.sdcc.bnl.gov"),
        "PORT": env("PANDA_DB_PORT", "5432"),
        "NAME": env("PANDA_DB_NAME", "panda_db"),
        "USER": env("PANDA_DB_USER", "panda"),
        "PASSWORD": env("PANDA_DB_PASSWORD", ""),
        "OPTIONS": {
            "sslmode": env("PANDA_DB_SSLMODE", "require"),
        },
    },
}
