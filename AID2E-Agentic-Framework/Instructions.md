# Setting up the panda-swf server

## Terminal 1
Start a ssh session for the rcfsub machine that will listen to a port number (say 8443) such that it forwards it to pandaserver02.sdcc.bnl.gov

```bash
ssh -N \
-L 8443:pandaserver02.sdcc.bnl.gov:443 rcfsub
```



##  Terminal 2

Copy over the grid certificates from the SDCC home area to your local area. This is a one time thing
```bash
rsync -av rcfsub:/etc/grid-security/certificates/ "$HOME/sdcc-grid-certificates/"
```
And
```bash
export SSL_CERT_DIR="$HOME/sdcc-grid-certificates"
```
Add pandaserver02 to your list of local hosts.
```bash
sudo sh -c 'echo "127.0.0.1 pandaserver02.sdcc.bnl.gov" >> /etc/hosts'
```
Make sure that the URL in the test-epic-mcp.py is set to 
```text
URL = "https://pandaserver02.sdcc.bnl.gov:8443/swf-monitor/mcp/"
```

Make sure to load the token:
```bash
export SWF_MONITOR_MCP_TOKEN="$(tr -d '\r\n' < ".token-swf")"
```
Run the test code test-epic-mcp.py

## Clean up
Once done remove the panda server from the list of local hosts

```bash
sudo sed -i.bak '/pandaserver02.sdcc.bnl.gov/d' /etc/hosts
```


The communication pathway is:
```text
local laptop -> SSH tunnel -> SDCC -> MCP server
```