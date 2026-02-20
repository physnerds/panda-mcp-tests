# PanDA MCP AI Agent

An AI-powered interface for [PanDA (Production and Distributed Analysis) Workload Management System](https://panda-wms.readthedocs.io/) using the Model Context Protocol (MCP). This project enables natural language interaction with PanDA servers through various Large Language Models (LLMs) and provides intelligent job analysis capabilities.

## Project Overview

This project implements an MCP-based client-server architecture that bridges PanDA's RESTful API with AI language models. It consists of two main components:

### 1. **PanDA MCP Client (`mcp_agent.py`)**
A Python agent that connects to PanDA MCP servers and uses local or remote LLMs (Mistral, OpenAI, Claude, Gemini) to:
- Query PanDA server status and health
- Retrieve and analyze job information
- Perform natural language queries on PanDA operations
- Execute PanDA API calls through natural conversation

### 2. **Ask PanDA RAG Service (`ask-panda/`)**
A FastAPI-based Retrieval-Augmented Generation (RAG) service that provides:
- **Document Query Agent**: Answers questions about PanDA documentation using vector embeddings (ChromaDB)
- **Log Analysis Agent**: Analyzes PanDA job logs and error codes
- **Maintenance Agent**: Provides guidance on system maintenance tasks
- Multi-LLM support (Anthropic Claude, OpenAI GPT, Google Gemini, Local Llama via Ollama)

### Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   User Query    │────────>│   mcp_agent.py   │────────>│  LLM (Mistral/  │
│                 │         │                  │         │  OpenAI/Claude) │
└─────────────────┘         └──────────────────┘         └─────────────────┘
                                     │                            │
                                     v                            v
                            ┌──────────────────┐         ┌─────────────────┐
                            │  PanDA MCP       │<────────│  Tool Execution │
                            │  Server (Docker) │         │  & Response     │
                            └──────────────────┘         └─────────────────┘
                                     │
                                     v
                            ┌──────────────────┐
                            │  PanDA Server    │
                            │  (SDCC/Local)    │
                            └──────────────────┘

┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│  Ask PanDA      │────────>│  FastAPI Server  │────────>│  Vector Store   │
│  Questions      │         │  (RAG Service)   │         │  (ChromaDB)     │
└─────────────────┘         └──────────────────┘         └─────────────────┘
                                     │
                                     v
                            ┌──────────────────┐
                            │  Multi-LLM       │
                            │  Backends        │
                            └──────────────────┘
```

## Features

- **Multi-LLM Support**: Works with OpenAI GPT, Anthropic Claude, Google Gemini, and local Mistral/Llama models via Ollama
- **PanDA Integration**: Direct integration with PanDA's MCP-enabled servers
- **RAG-based Documentation**: Intelligent question answering using PanDA documentation embeddings
- **Job Analysis**: Automated analysis of job logs and error codes
- **Docker Support**: Easy deployment using PanDA's official Docker images
- **Flexible Architecture**: Supports both remote PanDA servers (e.g., SDCC) and local Docker deployments

## Requirements

### System Requirements
- Python 3.11 or higher
- Docker (for PanDA MCP server deployment)
- GPU (optional, for local LLM acceleration)
- 8GB+ RAM (16GB recommended for local LLMs)

### Python Dependencies

Core dependencies for MCP client (`mcp_agent.py`):
```
fastmcp
requests
```

Ask PanDA service dependencies (`ask-panda/requirements.txt`):
```
anthropic
chromadb
faiss-cpu
fastapi
fastmcp
google-generativeai
langchain
langchain_community
langchain-chroma
langchain-huggingface
langchain-openai
numpy<2
openai
psutil
requests
sentence-transformers
transformers
uvicorn[standard]
```

### Local LLM Setup (Mistral via Ollama)

To use local NLP models like Mistral, you need to install Ollama:

#### On Host System
```bash
# Download and install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull the Mistral model
ollama pull mistral

# Start Ollama server (runs on http://localhost:11434 by default)
ollama serve
```

#### Inside Docker Container
```bash
# Download Ollama binary
curl -L https://github.com/ollama/ollama/releases/download/v0.1.24/ollama-linux-amd64 -o ~/ollama
chmod +x ~/ollama

# Add to PATH
export PATH="$HOME:$PATH"
export OLLAMA_MODELS="$HOME/models"

# Start Ollama server
ollama serve &

# Pull Mistral model
ollama pull mistral
```

**Note**: Docker containers may not detect GPU acceleration. For GPU support, use the host installation or configure Docker with NVIDIA runtime.

### API Keys for Remote LLMs

Set environment variables for the LLMs you plan to use:

```bash
# Anthropic Claude
export ANTHROPIC_API_KEY='your_anthropic_api_key'

# OpenAI GPT
export OPENAI_API_KEY='your_openai_api_key'

# Google Gemini
export GEMINI_API_KEY='your_gemini_api_key'

# Local Llama/Mistral (Ollama)
export LLAMA_API_URL='http://localhost:11434/api/generate'
```

## Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd mcp-server
```

### 2. Create Virtual Environment
```bash
# For MCP agent
python3 -m venv panda-mcp
source panda-mcp/bin/activate
pip install fastmcp requests

# For Ask PanDA service
python3 -m venv ask-panda-env
source ask-panda-env/bin/activate
pip install -r ask-panda/requirements.txt
```

### 3. Set Up PanDA MCP Docker Container

#### Create Docker Container
```bash
# For local PanDA server
docker create --name panda-mcp -it --user atlpan -p 25888:25888 \
   -e PANDA_API_URL=http://<panda_server_hostname>:25080/api/v1 \
   -e PANDA_API_URL_SSL=https://<panda_server_hostname>:25443/api/v1 \
   ghcr.io/pandawms/panda-server:latest \
   sh -c "/etc/rc.d/init.d/panda-mcp start && tail -f /dev/null"

# For SDCC PanDA server
docker create --name panda-mcp -it --user atlpan -p 25888:25888 \
   -e PANDA_API_URL=http://pandaserver01.sdcc.bnl.gov:25443/server/panda/api/v1 \
   -e PANDA_API_URL_SSL=https://pandaserver01.sdcc.bnl.gov:25443/server/panda/api/v1 \
   ghcr.io/pandawms/panda-server:latest \
   sh -c "/etc/rc.d/init.d/panda-mcp start && tail -f /dev/null"
```

#### Configure the Container
```bash
# Start the container
sudo docker start panda-mcp

# Create config directory (run as root)
sudo docker exec -u root panda-mcp mkdir -p /opt/panda/etc/panda/config_json

# Copy configuration files
sudo docker cp panda_server_config.json panda-mcp:/opt/panda/etc/panda/config_json/
sudo docker cp panda_mcp_endpoints.json panda-mcp:/opt/panda/etc/panda/

# Restart to apply configuration
sudo docker restart panda-mcp
```

#### Verify Installation
```bash
# Check logs
sudo docker logs panda-mcp --tail 20

# Verify PanDA MCP is running
sudo docker exec panda-mcp ps aux | grep python

# Test the endpoint
curl -v http://localhost:25888/mcp/
```

## Configuration

### PanDA Server Configuration (`panda_server_config.json`)

This file configures the MCP server transport and endpoints:

```json
{
  "mcp": {
    "transport": "http",
    "endpoint_list_file": "/opt/panda/etc/panda/panda_mcp_endpoints.json"
  }
}
```

### MCP Endpoints Configuration (`panda_mcp_endpoints.json`)

Define which PanDA API endpoints to expose via MCP:

```json
{
  "system": [
    "is_alive"
  ],
  "job": [
    "get_job_status",
    "get_job_details",
    "retry_job"
  ],
  "task": [
    "get_task_status",
    "finish_task"
  ]
}
```

**Available API Categories:**
- `system`: Health checks and system status
- `job`: Job management and queries
- `task`: Task operations
- `user`: User-related operations
- `file`: File catalog operations

## Adding Additional APIs in PanDA Server (Docker Container)

To extend the MCP server with additional PanDA API endpoints:

### 1. Edit the Endpoints Configuration

Update `panda_mcp_endpoints.json` to include new endpoints:

```json
{
  "system": [
    "is_alive",
    "get_load"
  ],
  "job": [
    "get_job_status",
    "get_job_details",
    "retry_job",
    "kill_job",
    "get_job_statistics"
  ],
  "task": [
    "get_task_status",
    "finish_task",
    "retry_task"
  ],
  "user": [
    "get_user_jobs",
    "get_user_quota"
  ]
}
```

### 2. Update Configuration in Docker Container

```bash
# Copy updated configuration
sudo docker cp panda_mcp_endpoints.json panda-mcp:/opt/panda/etc/panda/

# Restart the container to apply changes
sudo docker restart panda-mcp

# Verify the new endpoints are available
sudo docker exec panda-mcp cat /opt/panda/etc/panda/panda_mcp_endpoints.json
```

### 3. Test New Endpoints

```bash
# Enter the container
sudo docker exec -it panda-mcp bash

# Activate virtual environment
source /opt/panda/bin/activate

# Test using mcp_test_client.py
python /opt/panda/lib/python3.11/site-packages/pandaserver/pandamcp/mcp_test_client.py \
  --tool get_job_status \
  --host pandaserver01.sdcc.bnl.gov \
  --port 25443 \
  --kv pandaid=12345
```

### 4. Available PanDA API Modules

PanDA MCP maps to these API modules:
- `pandaserver.api.v1.system_api` → system operations
- `pandaserver.api.v1.job_api` → job operations
- `pandaserver.api.v1.task_api` → task operations
- `pandaserver.api.v1.user_api` → user operations
- `pandaserver.api.v1.file_api` → file operations

**Example - Adding a Custom Tool:**

If you need to expose a new function like `get_job_statistics`, ensure it exists in `pandaserver.api.v1.job_api` and add it to the `job` section in `panda_mcp_endpoints.json`.

## Using mcp_agent.py

The `mcp_agent.py` script is the main client for interacting with PanDA through natural language.

### Basic Usage

```bash
# Activate the virtual environment
source panda-mcp/bin/activate

# Query SDCC PanDA server
python mcp_agent.py --server sdcc

# Query local Docker PanDA server
python mcp_agent.py --server docker

# Use specific Ollama model
python mcp_agent.py --server sdcc --model mistral

# Specify custom MCP URL
python mcp_agent.py --mcp-url http://localhost:25888/mcp/ --ollama-url http://localhost:11434
```

### Command-Line Arguments

```
--server {sdcc,docker}  : Preset configurations for SDCC or local Docker
--mcp-url URL          : Custom MCP server URL
--ollama-url URL       : Custom Ollama server URL (default: http://localhost:11434)
--model MODEL          : LLM model name (default: mistral)
--auth-token TOKEN     : OIDC authentication token for write operations
--vo VO                : Virtual organization name
```

### Example Interactions

```bash
$ python mcp_agent.py --server sdcc

Available PanDA Tools:
- is_alive: Check if the server is alive (no arguments required)
- get_job_status: Get the status of a PanDA job
- get_job_details: Get detailed information about a job

Enter your question (or 'quit' to exit): Is the PanDA server alive?

Agent: I'll check the PanDA server status using the is_alive tool.
Tool: is_alive
Result: {"success": true}
Response: Yes, the PanDA server is alive and responding.

Enter your question (or 'quit' to exit): What is the status of job 12345?

Agent: I'll query the job status for PandaID 12345.
Tool: get_job_status
Arguments: {"pandaid": 12345}
Result: {"status": "finished", "jobstatus": "finished"}
Response: Job 12345 has finished successfully.
```

### How It Works

1. **Tool Discovery**: On startup, the agent fetches available tools from the PanDA MCP server
2. **Prompt Engineering**: User queries are combined with tool descriptions and sent to the LLM
3. **Tool Selection**: The LLM decides which tools to use and generates appropriate arguments
4. **Execution**: The agent executes the selected tools via MCP protocol
5. **Response Generation**: Results are sent back to the LLM for natural language summary

### Code Structure

```python
class PanDAAgentOllama:
    def __init__(self, mcp_url, ollama_url, auth_token=None, vo=None):
        # Initialize MCP client and Ollama connection
        
    async def initialize_tools(self):
        # Fetch available tools from PanDA MCP
        
    async def execute_tool(self, tool_name, arguments):
        # Execute a PanDA tool via MCP
        
    def query_ollama(self, prompt):
        # Send prompt to Ollama and get LLM response
        
    async def process_question(self, question):
        # Main loop: LLM decides tools → execute → summarize
```

## Using Ask PanDA RAG Service

The Ask PanDA service provides RAG-based question answering about PanDA documentation and job analysis.

### 1. Start the Server

```bash
cd ask-panda
source ../ask-panda-env/bin/activate

# Start the FastAPI server
uvicorn ask_panda_server:app --reload --port 8000
```

The server will:
- Initialize ChromaDB vector store with PanDA documentation
- Load embedding models (HuggingFace)
- Start periodic documentation updates
- Listen on `http://localhost:8000`

### 2. Query the Service

#### Using Document Query Agent

```bash
curl -X POST http://localhost:8000/rag_ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How do I configure pilot error codes?",
    "llm": "anthropic"
  }'
```

#### Using Log Analysis Agent

```bash
curl -X POST http://localhost:8000/analyze_log \
  -H "Content-Type: application/json" \
  -d '{
    "panda_id": "12345",
    "log_content": "ERROR 1098: Payload failed to start",
    "llm": "openai"
  }'
```

### 3. Available LLM Backends

- `anthropic` - Anthropic Claude (requires ANTHROPIC_API_KEY)
- `openai` - OpenAI GPT (requires OPENAI_API_KEY)
- `gemini` - Google Gemini (requires GEMINI_API_KEY)
- `llama` - Local Llama via Ollama (default: http://localhost:11434)

### 4. Agent Architecture

```
ask-panda/
├── ask_panda_server.py       # FastAPI server with RAG endpoints
├── agents/
│   ├── selection_agent.py    # Routes queries to specialized agents
│   ├── document_query_agent.py  # Answers documentation questions
│   ├── log_analysis_agent.py    # Analyzes job logs
│   └── maintenance_agent.py     # System maintenance guidance
├── tools/
│   ├── vectorstore_manager.py   # ChromaDB management
│   ├── errorcodes.py           # PanDA error code definitions
│   └── tools.py                # Utility functions
├── resources/                   # Documentation files
└── chromadb/                    # Vector database storage
```

### 5. Endpoints

- `POST /rag_ask` - Ask questions about PanDA documentation
- `POST /analyze_log` - Analyze job logs and errors
- `GET /health` - Health check endpoint
- `GET /docs` - Swagger API documentation

## Project Structure

```
mcp-server/
├── mcp_agent.py                    # Main MCP client agent
├── mcp_test_client.py              # Basic MCP connection testing
├── panda_server_config.json        # PanDA MCP server configuration
├── panda_mcp_endpoints.json        # API endpoints to expose
├── Instructions.md                 # Detailed setup instructions
├── Issues.md                       # Known issues and troubleshooting
├── CLAUDE.md                       # AI assistant instructions
├── Docker_mcp.md                   # Docker deployment guide
│
├── ask-panda/                      # RAG service
│   ├── ask_panda_server.py         # FastAPI RAG server
│   ├── test_server.py              # Test client
│   ├── requirements.txt            # Python dependencies
│   ├── agents/                     # Specialized AI agents
│   ├── tools/                      # Utility functions
│   ├── resources/                  # Documentation corpus
│   └── cache/                      # Error code caches
│
├── panda-mcp/                      # Virtual environment (MCP client)
└── pclient/                        # PanDA client tools
```

## Troubleshooting

### Docker Container Issues

**Problem**: Container fails to start
```bash
# Check container status
sudo docker ps -a | grep panda-mcp

# View logs
sudo docker logs panda-mcp

# Recreate container
sudo docker rm panda-mcp
# Then recreate using the docker create command
```

**Problem**: Configuration not applied
```bash
# Verify config files are copied
sudo docker exec panda-mcp ls -la /opt/panda/etc/panda/
sudo docker exec panda-mcp cat /opt/panda/etc/panda/config_json/panda_server_config.json

# Restart container
sudo docker restart panda-mcp
```

### Ollama Issues

**Problem**: GPU not detected in Docker
- Ollama in Docker may not detect GPU. Use host installation or configure Docker with `--gpus all`

**Problem**: Model not found
```bash
ollama list                    # Check installed models
ollama pull mistral            # Download model
```

### MCP Agent Issues

**Problem**: Connection timeout
```bash
# Test MCP endpoint directly
curl http://localhost:25888/mcp/

# Check if container is running
sudo docker ps | grep panda-mcp
```

**Problem**: Tool execution fails
- Verify the endpoint exists in `panda_mcp_endpoints.json`
- Check that the PanDA API function exists in the server
- Review error messages in responses

### Ask PanDA Service Issues

**Problem**: Vector store initialization fails
- Ensure `resources/` directory contains documentation files
- Check ChromaDB directory permissions
- Verify HuggingFace models are downloaded

**Problem**: LLM API errors
- Verify API keys are set correctly
- Check internet connectivity for remote APIs
- Ensure Ollama is running for local LLM

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Test your changes thoroughly
4. Submit a pull request with clear description

## References

- [PanDA Documentation](https://panda-wms.readthedocs.io/)
- [PanDA MCP Guide](https://panda-wms.readthedocs.io/en/latest/advanced/mcp.html)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Ollama](https://ollama.ai/)

## License

See LICENSE file for details.

## Support

For issues and questions:
- PanDA: https://panda-wms.readthedocs.io/
- GitHub Issues: <repository-issues-url>

## Acknowledgments

This project integrates with:
- PanDA Workload Management System
- FastMCP framework
- LangChain for RAG
- ChromaDB for vector storage
- Multiple LLM providers (Anthropic, OpenAI, Google, Ollama)
