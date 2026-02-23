# Issues
```bash
root@lpo-178574:/home/amitbashyal/Documents/BNL-AiD2E/mcp-server# docker create   --name panda-mcp   -dt  --user atlpan   -p 25888:25888   -e PANDA_API_URL=http://panda-server-hostname:25080/api/v1   -e PANDA_API_URL_SSL=https://panda-server-hostname:25443/api/v1   ghcr.io/pandawms/panda-server:latest   sh -c "/etc/rc.d/init.d/panda-mcp start && tail -f /dev/null"
unknown shorthand flag: 'd' in -dt

Usage:  docker create [OPTIONS] IMAGE [COMMAND] [ARG...]

Run 'docker create --help' for more information
```
# No config_json directory in the container
```bash
docker create --name panda-mcp -dt --user atlpan -p 25888:25888 \
   -e PANDA_API_URL=http://<panda_server_hostname:http_port>/api/v1 \
   -e PANDA_API_URL_SSL=https://<panda_server_hostname:https_post>/api/v1  \
   ghcr.io/pandawms/panda-server:latest \
   sh -c "/etc/rc.d/init.d/panda-mcp start && tail -f /dev/null"
docker cp panda_mcp_endpoints.json panda-mcp:/opt/panda/etc/panda/
docker cp panda_server_config.json panda-mcp:/opt/panda/etc/panda/config_json/
```

# Entering the docker image
```bash
sudo docker start panda-mcp
sudo docker exec -it panda-mcp bash
```
#  Testing PanDA MCP
Make sure if your server is remote or the docker container....


# When installing ollama in the docker, does not detect GPU
(panda) [atlpan@a2ef876ee292 ollama]$ ollama serve &
[1] 557
(panda) [atlpan@a2ef876ee292 ollama]$ time=2026-01-12T23:43:24.202Z level=INFO source=images.go:863 msg="total blobs: 0"
time=2026-01-12T23:43:24.202Z level=INFO source=images.go:870 msg="total unused blobs removed: 0"
time=2026-01-12T23:43:24.203Z level=INFO source=routes.go:999 msg="Listening on 127.0.0.1:11434 (version 0.1.24)"
time=2026-01-12T23:43:24.203Z level=INFO source=payload_common.go:106 msg="Extracting dynamic libraries..."
time=2026-01-12T23:43:26.183Z level=INFO source=payload_common.go:145 msg="Dynamic LLM libraries [cuda_v11 cpu_avx2 cpu rocm_v5 rocm_v6 cpu_avx]"
time=2026-01-12T23:43:26.183Z level=INFO source=gpu.go:94 msg="Detecting GPU type"
time=2026-01-12T23:43:26.183Z level=INFO source=gpu.go:242 msg="Searching for GPU management library libnvidia-ml.so"
time=2026-01-12T23:43:26.184Z level=INFO source=gpu.go:288 msg="Discovered GPU libraries: []"
time=2026-01-12T23:43:26.184Z level=INFO source=gpu.go:242 msg="Searching for GPU management library librocm_smi64.so"
time=2026-01-12T23:43:26.184Z level=INFO source=gpu.go:288 msg="Discovered GPU libraries: []"
time=2026-01-12T23:43:26.184Z level=INFO source=cpu_common.go:11 msg="CPU has AVX2"
time=2026-01-12T23:43:26.184Z level=INFO source=routes.go:1022 msg="no GPU detected"


## Tests to see if the docker server is running or not:

(base) amitbashyal@lpo-178574:~/Documents/BNL-AiD2E/mcp-server$  sudo docker cp panda_mcp_endpoints.json panda-mcp:/opt/panda/etc/panda/
[sudo] password for amitbashyal: 
Successfully copied 2.05kB to panda-mcp:/opt/panda/etc/panda/
(base) amitbashyal@lpo-178574:~/Documents/BNL-AiD2E/mcp-server$  sudo docker restart panda-mcp
panda-mcp
(base) amitbashyal@lpo-178574:~/Documents/BNL-AiD2E/mcp-server$  sleep 3 && sudo docker logs panda-mcp --tail 20
Starting PanDA MCP ...
PanDA MCP started with PID 9.
Starting PanDA MCP ...
PanDA MCP started with PID 10.
Starting PanDA MCP ...
PanDA MCP started with PID 11.
Starting PanDA MCP ...
PanDA MCP started with PID 11.
(base) amitbashyal@lpo-178574:~/Documents/BNL-AiD2E/mcp-server$  sudo docker exec panda-mcp cat /var/log/panda/panda_mcp_stderr.log | tail -20
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:25888 (Press CTRL+C to quit)
Traceback (most recent call last):
  File "/opt/panda/lib/python3.11/site-packages/pandaserver/pandamcp/mcp_main.py", line 42, in <module>
    func = getattr(api_module, func_name)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: module 'pandaserver.api.v1.job_api' has no attribute 'get_job_status'. Did you mean: 'get_status'?
Traceback (most recent call last):
  File "/opt/panda/lib/python3.11/site-packages/pandaserver/pandamcp/mcp_main.py", line 42, in <module>
    func = getattr(api_module, func_name)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: module 'pandaserver.api.v1.job_api' has no attribute 'get_job_status'. Did you mean: 'get_status'?
/opt/panda/lib/python3.11/site-packages/websockets/legacy/__init__.py:6: DeprecationWarning: websockets.legacy is deprecated; see https://websockets.readthedocs.io/en/stable/howto/upgrade.html for upgrade instructions
  warnings.warn(  # deprecated in 14.0 - 2024-11-09
/opt/panda/lib/python3.11/site-packages/uvicorn/protocols/websockets/websockets_impl.py:17: DeprecationWarning: websockets.server.WebSocketServerProtocol is deprecated
  from websockets.server import WebSocketServerProtocol
INFO:     Started server process [11]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:25888 (Press CTRL+C to quit)
(base) amitbashyal@lpo-178574:~/Documents/BNL-AiD2E/mcp-server$  sudo docker exec panda-mcp ps aux | grep python
atlpan        11  2.3  0.1 102432 85952 pts/0    S+   20:55   0:00 python -u /opt/panda/lib/python3.11/site-packages/pandaserver/pandamcp/mcp_main.py
(base) amitbashyal@lpo-178574:~/Documents/BNL-AiD2E/mcp-server$  curl -s http://localhost:25888/mcp/ | head -20
(base) amitbashyal@lpo-178574:~/Documents/BNL-AiD2E/mcp-server$  curl -v http://localhost:25888/mcp/ 2>&1 | head -30
* Host localhost:25888 was resolved.
* IPv6: ::1
* IPv4: 127.0.0.1
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0*   Trying [::1]:25888...
* Connected to localhost (::1) port 25888
> GET /mcp/ HTTP/1.1
> Host: localhost:25888
> User-Agent: curl/8.5.0
> Accept: */*
> 
< HTTP/1.1 307 Temporary Redirect
< date: Fri, 20 Feb 2026 20:56:38 GMT
< server: uvicorn
< content-length: 0
< location: http://localhost:25888/mcp
< 
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
* Connection #0 to host localhost left intact


### Issue February 20 2025 To look at tomorrow
I think I can connect to the PANDA-MCP server in SDCC that talks to PANDA server in SDCC.
However, in the PANDA-MCP server hosted in SDCC, only one api is exposed (is_alive).
Hence a local PandA MCP server is needed that talks to PANDA server hosted in SDCC. This will allow me to add other PandA APIs for the testing purpose. 


See the preliminary testing reports here: 
https://docs.google.com/document/d/15jCHwIkfmtJ6AI99L0ZDRiy4AEe4ycxwk_xwApsZ1Is/edit?usp=sharing

# This issue is solved. Should use the correct server (pandacern instead of pandaserver01)