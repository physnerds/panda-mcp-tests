import contextlib

from starlette.applications import Starlette
from starlette.routing import Mount

from aid2e_service.app import mcp
from aid2e_service import tools  # noqa: F401


@contextlib.asynccontextmanager
async def lifespan(app):
    async with mcp.session_manager.run():
        yield


application = Starlette(
    routes=[Mount("/", app=mcp.streamable_http_app())],
    lifespan=lifespan,
)
