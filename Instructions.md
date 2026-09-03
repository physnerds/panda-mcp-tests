# Building the docker client

# Create a docker container for panda-mcp [One time]
```bash
docker create --name panda-mcp -dt --user atlpan -p 25888:25888 \
   -e PANDA_API_URL=http://<panda_server_hostname:http_port>/api/v1 \
   -e PANDA_API_URL_SSL=https://<panda_server_hostname:https_post>/api/v1  \
   ghcr.io/pandawms/panda-server:latest \
   sh -c "/etc/rc.d/init.d/panda-mcp start && tail -f /dev/null"
docker cp panda_mcp_endpoints.json panda-mcp:/opt/panda/etc/panda/
docker cp panda_server_config.json panda-mcp:/opt/panda/etc/panda/config_json/
```

# Start the docker container
You may not need sudo privilege but the following instruction assumes you may need
```bash
sudo docker start panda-mcp
sudo docker exec -it panda-mcp bash # if you want to go inside the container interactively
```

# You need to copy the config files to  the docker container (one time action)
```bash
$sudo docker exec panda-mcp mkdir -p /opt/panda/etc/panda/config_json
$docker cp panda_server_config.json panda-mcp:/opt/panda/etc/panda/config_json/
$docker cp panda_mcp_endpoints.json panda-mcp:/opt/panda/etc/panda/
```

# Running the panda-mcp

## PandaServer hosted in SDCC
```bash
python mcp_agent.py --server sdcc 
```
## Your local Panda Server in docker
```bash
python mcp_agent.py --server docker
```



```bash

  cp .codex/remote-vllm.config.toml ~/.codex/remote-vllm.config.toml
  codex --profile remote-vllm
```

Before starting Codex, make sure the vLLM OpenAI-compatible endpoint is reachable at the configured URL:

```bash
  curl http://127.0.0.1:8000/v1/models # whatever is the appropriate url after setting up the vllm in perlmutter/remote machine

  ```
  