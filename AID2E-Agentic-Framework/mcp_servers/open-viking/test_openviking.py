import os
from pathlib import Path

from openviking_client import DEFAULT_OPENVIKING_CA_FILE, OpenVikingAipandaClient


def configure_ssl_cert_file() -> None:
    """Use the CERN root CA required by the OpenViking HTTPS endpoint."""
    default_ca = DEFAULT_OPENVIKING_CA_FILE
    path = os.environ.get("OPENVIKING_SSL_CERT_FILE")
    ca_file = Path(path).expanduser() if path else default_ca

    try:
        content = ca_file.read_text(errors="ignore")
    except OSError:
        content = ""

    if "BEGIN CERTIFICATE" not in content:
        ca_file = default_ca

    os.environ["OPENVIKING_SSL_CERT_FILE"] = str(ca_file)


configure_ssl_cert_file()



url="http://localhost:1933"

url="https://aipanda106.cern.ch:443"

client = OpenVikingAipandaClient(url=url)



results = client.find(query="how to use openviking")

print(results)

print("*****************DONE PRINTING RESULTS****************")

ret = client.find(query="user authentication")       # Semantic search

print(ret)
print("************************DONE PRINTING USER AUTHENTICATION********************************************")
ret = client.ls(uri="viking://resources/")            # List directory

print(ret)
print("***************************DONE PRINTING RESOURCES*****************************************")
# ret = client.read(uri="viking://resources/doc")       # Read content

# print(ret)

# ret = client.abstract(uri="viking://...")             # Get L0 abstract

# print(ret)

# ret = client.overview(uri="viking://...")             # Get L1 overview

# print(ret)



filename = os.environ.get("OPENVIKING_RESOURCE_PATH", "./original-ks.cfg")
resource_path = Path(filename)

if resource_path.exists():
    result = client.add_resource(str(resource_path))  # you can use other functions like add_message()
    print(result)
else:
    print(f"Skipping add_resource: {resource_path} does not exist")



client.close()
