#!/bin/bash
# Script to recreate panda-mcp container pointing to SDCC server

echo "Stopping and removing old container..."
sudo docker stop panda-mcp 2>/dev/null
sudo docker rm panda-mcp 2>/dev/null

# Extract ID token from .token file
if [ ! -f ".token" ]; then
    echo "ERROR: .token file not found!"
    echo "Please ensure you have a valid .token file with OIDC credentials."
    exit 1
fi

echo "Extracting ID token from .token file..."
ID_TOKEN=$(python3 -c "import json; print(json.load(open('.token'))['id_token'])" 2>/dev/null)

if [ -z "$ID_TOKEN" ]; then
    echo "ERROR: Failed to extract id_token from .token file!"
    exit 1
fi

echo "Creating new panda-mcp container pointing to SDCC..."

# FIXED: Correct API URLs without /server/panda prefix
sudo docker create --name panda-mcp -it --user atlpan -p 25888:25888 \
   -e PANDA_API_URL=http://pandaserver01.sdcc.bnl.gov:25080/api/v1 \
   -e PANDA_API_URL_SSL=https://pandaserver01.sdcc.bnl.gov:25443/api/v1 \
   -e PANDA_AUTH=oidc \
   -e PANDA_AUTH_ID_TOKEN="$ID_TOKEN" \
   -e PANDA_URL_SSL=https://pandaserver01.sdcc.bnl.gov:25443/server/panda \
   -e PANDA_URL=https://pandaserver01.sdcc.bnl.gov:25443/server/panda \
   -e PANDACACHE_URL=https://pandaserver01.sdcc.bnl.gov:25443/server/panda \
   -e PANDAMON_URL=https://pandamon01.sdcc.bnl.gov \
   -e PANDA_AUTH_VO=EIC \
   -e PANDA_USE_NATIVE_HTTPLIB=1 \
   -e PANDA_BEHIND_REAL_LB=1 \
   ghcr.io/pandawms/panda-server:latest \
   sh -c "/etc/rc.d/init.d/panda-mcp start && tail -f /dev/null"

echo "Starting container..."
sudo docker start panda-mcp

echo "Waiting for container to be ready..."
sleep 2

echo "Creating config directory..."
sudo docker exec -u root panda-mcp mkdir -p /opt/panda/etc/panda/config_json

echo "Copying configuration files..."
sudo docker cp panda_server_config.json panda-mcp:/opt/panda/etc/panda/config_json/
sudo docker cp panda_mcp_endpoints.json panda-mcp:/opt/panda/etc/panda/

echo "Copying modified Python files (for OIDC auth support)..."
sudo docker cp mcp_main.py panda-mcp:/opt/panda/lib/python3.11/site-packages/pandaserver/pandamcp/mcp_main.py
sudo docker cp mcp_utils.py panda-mcp:/opt/panda/lib/python3.11/site-packages/pandaserver/pandamcp/mcp_utils.py

echo "Restarting container to apply configuration..."
sudo docker restart panda-mcp

echo "Waiting for MCP service to start..."
sleep 5

echo ""
echo "✓ Container created and started!"
echo ""
echo "Verify authentication token is set:"
echo "  sudo docker exec panda-mcp env | grep PANDA_AUTH"
echo ""
echo "Debug MCP logs:"
echo "  sudo docker exec panda-mcp tail -f /var/log/panda/panda_mcp_stderr.log"
echo ""
echo "Test with:"
echo "  python mcp_test_client.py --tool is_alive --host localhost --port 25888 --use_http"
echo ""
echo "Or use the agent:"
echo "python mcp_agent.py --server docker"