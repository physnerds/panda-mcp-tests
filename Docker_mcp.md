I am trying to run a mcp agent that can talk to the PanDA-server. I am using the Docker contianer for this purpose. The instructions are based on the following: 

#########

PandaMCP can also be deployed and operated independently of the PanDA Server. In this setup, the MCP server may directly communicate with AI agents without going through the HTTP forwarding in the PanDA Server. The easiest way for this setup is to use the Docker image.

docker create --name panda-mcp -dt --user atlpan -p 25888:25888 \
   -e PANDA_API_URL=http://<panda_server_hostname:http_port>/api/v1 \
   -e PANDA_API_URL_SSL=https://<panda_server_hostname:https_post>/api/v1  \
   ghcr.io/pandawms/panda-server:latest \
   sh -c "/etc/rc.d/init.d/panda-mcp start && tail -f /dev/null"
docker cp panda_mcp_endpoints.json panda-mcp:/opt/panda/etc/panda/
docker cp panda_server_config.json panda-mcp:/opt/panda/etc/panda/config_json/
docker start panda-mcp

where <panda_server_hostname:http_port> and <panda_server_hostname:https_post> should be replaced with the hostname and port numbers of the PanDA Server. In this configuration, PandaMCP receives requests from AI agents through port 25888. panda_mcp_endpoints.json contains the list of API endpoints to be exposed via MCP, as described in the previous section. panda_server_config.json is a JSON file to overwrite default values in panda_server.cfg, e.g.,

{"mcp": {"transport": "http",
         "endpoint_list_file": "/opt/panda/etc/panda/panda_mcp_endpoints.json"
         }
}
########## 

Steps so far:
# Create the docker container:
```bash
$sudo docker create   --name panda-mcp   -it  --user atlpan   -p 25888:25888   -e PANDA_API_URL=http://pandaserver01.sdcc.bnl.gov:25443/server/panda/api/v1  -e PANDA_API_URL_SSL= https://pandaserver01.sdcc.bnl.gov:25443/server/panda/api/v1  ghcr.io/pandawms/panda-server:latest   sh -c "/etc/rc.d/init.d/panda-mcp start && tail -f /dev/null"

sudo docker start panda-mcp
```

# Copy over the config files:

```bash
$sudo docker exec panda-mcp mkdir -p /opt/panda/etc/panda/config_json
$docker cp panda_server_config.json panda-mcp:/opt/panda/etc/panda/config_json/
$docker cp panda_mcp_endpoints.json panda-mcp:/opt/panda/etc/panda/
```

# Enter the docker container and test and run mcp_test_client.pu

```bash
$sudo docker exec -it panda-mcp bash
$source /opt/panda/bin/activate
$cp /opt/panda/lib/python3.11/site-packages/pandaserver/pandamcp/mcp_test_client.py .
$python mcp_test_client.py --tool is_alive --host pandaserver01.sdcc.bnl.gov --port 25443
Client connected

Available tools:
- is_alive -

 Description: 
    Is alive

    Check if the server is alive. Basic function for the health check used in SLS monitoring.

    API details:
        HTTP Method: GET
        Path: /v1/system/is_alive

    Args:
        req(PandaRequest): internally generated request object containing the env variables

    Returns:
        dict: The system response with the name of the endpoint
              Example: `{"success": True}`
    



Testing is_alive:
Result: CallToolResult(content=[TextContent(type='text', text='{"success":true,"message":"","data":null}', annotations=None, meta=None)], structured_content={'success': True, 'message': '', 'data': None}, meta=None, data={'success': True, 'message': '', 'data': None}, is_error=False)

Client disconnected
Done
```

# Now Download ollama

```bash
$curl -L https://github.com/ollama/ollama/releases/download/v0.1.24/ollama-linux-amd64 -o ollama
$chmod +x ollama

$echo 'export PATH="$HOME/panda-mcp/ollama:$PATH"' >> ~/.bashrc
/home/atlpan/panda-mcp/ollama
$echo 'export OLLAMA_MODELS="$HOME/ollama/panda-mcp/models"' >> ~/.bashrc
$source ~/.bashrc 
$which ollama
~/panda-mcp/ollama/ollama
$ollama
Usage:
  ollama [flags]
  ollama [command]
  .. 
  ..

```

# Get the mistral model
```bash
ollama serve & 
 ollama pull mistral

```

# try running the mcp_agent.py 

```bash
python mcp_agent.py 

```