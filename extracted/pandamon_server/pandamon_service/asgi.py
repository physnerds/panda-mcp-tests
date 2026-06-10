import contextlib
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pandamon_service.settings")

import django
from starlette.applications import Starlette
from starlette.routing import Mount

django.setup()

from pandamon_service.app import mcp  # noqa: E402
from pandamon_service import tools  # noqa: F401,E402


@contextlib.asynccontextmanager
async def lifespan(app):
    async with mcp.session_manager.run():
        yield


application = Starlette(
    routes=[Mount("/", app=mcp.streamable_http_app())],
    lifespan=lifespan,
)
