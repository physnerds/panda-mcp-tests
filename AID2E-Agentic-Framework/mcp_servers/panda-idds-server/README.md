This directory contains the information to launch the panda-idds server.
To launch the panda-idds server, you have to launch the shell scrip recreate_docker_bnl.sh which will create docker container with the mcp_server code (mcp_main.py) with the list of tools mentioned in server-files/panda_mcp_endpoints.json.

This will need a Bearer token. The token information is in the .token file in the same directory as recreate_docker_bnl.sh
