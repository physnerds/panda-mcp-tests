import json
import os
from importlib import import_module

import uvicorn
from fastmcp import FastMCP

from pandaserver.config import mcp_config
from pandaserver.pandamcp.mcp_utils import create_tool

# remove or overwrite environment variables to avoid server's credential being used
# EXCEPT when using OIDC auth (needed for BNL SDCC authentication)
if os.environ.get("PANDA_AUTH") != "oidc":
    for var in ["PANDA_AUTH_ID_TOKEN", "PANDA_AUTH_VO", "X509_USER_PROXY"]:
        if var in os.environ:
            del os.environ[var]
    os.environ["X509_USER_PROXY"] = "/dev/null"

# FIXED: Use correct module path instead of parsing from URL
# The API modules are located at pandaserver.api.v1, not pandaserver.server.panda.api.v1
api_module_path = "api.v1"

# get a list of API endpoints to expose
endpoints_to_expose = {}

if os.path.exists(mcp_config.endpoint_list_file):
    with open(mcp_config.endpoint_list_file, "r") as f:
        endpoints_to_expose = json.load(f)

# add an example endpoint if the file does not exist
endpoints_to_expose.setdefault("system", [])
if "is_alive" not in endpoints_to_expose["system"]:
    endpoints_to_expose["system"].append("is_alive")

# create FastMCP instance
main_mcp = FastMCP(name="Main")

# add tools
for mod, func_list in endpoints_to_expose.items():
    api_module = import_module(f"pandaserver.{api_module_path}.{mod}_api")
    for func_name in func_list:
        func = getattr(api_module, func_name)
        tool = create_tool(func)
        main_mcp.add_tool(tool)

# get HTTP app
http_app = main_mcp.http_app(transport=mcp_config.transport)

if __name__ == "__main__":
    uvicorn.run(
        http_app,
        host="0.0.0.0",
        port=int(os.getenv("PANDA_SERVER_CONF_PORT_MCP", 25888)),
        ssl_keyfile=mcp_config.ssl_keyfile,
        ssl_certfile=mcp_config.ssl_certfile,
    )