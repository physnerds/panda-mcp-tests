#!/bin/bash
# Script to recreate panda-mcp container pointing to SDCC server

echo "Stopping and removing old container..."
sudo docker stop panda-mcp 2>/dev/null
sudo docker rm panda-mcp 2>/dev/null

echo "Creating new panda-mcp container pointing to SDCC..."

#sudo docker create --name panda-mcp -it --user atlpan -p 25888:25888 \
#   -e PANDA_API_URL=http://pandaserver01.sdcc.bnl.gov:25080/server/panda/api/v1 \
#   -e PANDA_API_URL_SSL=https://pandaserver01.sdcc.bnl.gov:25443/server/panda/api/v1 \
#   ghcr.io/pandawms/panda-server:latest \
#   sh -c "/etc/rc.d/init.d/panda-mcp start && tail -f /dev/null"

# Check the proper server url and port in the docker container itself ()
# /opt/panda/etc/panda/sysconfig/panda_server_env.systemd.rpmnew
sudo docker create --name panda-mcp -it --user atlpan -p 25888:25888 \
   -e PANDA_API_URL=http://pandaserver.cern.ch:25080/api/v1 \
   -e PANDA_API_URL_SSL=https://pandaserver.cern.ch:25443/api/v1 \
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

echo "Restarting container to apply configuration..."
sudo docker restart panda-mcp

echo "Waiting for MCP service to start..."
sleep 5

echo ""
echo "Container created and started!"
echo ""
echo "Test with:"
echo "  python mcp_test_client.py --tool is_alive --host localhost --port 25888 --use_http"
echo ""
echo "Or use the agent:"
echo "  python mcp_agent.py --server docker"
