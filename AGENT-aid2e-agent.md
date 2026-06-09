# MCP Agent for the AID2E

## Purpose
The main purpose of the AID2E agent is to create an MCP agent to execute AID2E related jobs. https://github.com/aid2e/AID2E-framework/tree/testing-pymoo-models

# Task list
1. Create an aid2e-mcp agent that will be deployed in the docker. The docker will also have the AID2E installed (testing-pymoo-models branch).

2. Create mcp tools that can access the aid2e cli command (run `aid2e`), and run existing aid2e optimization script. Start with example like (https://github.com/aid2e/AID2E-framework/blob/testing-pymoo-models/examples/dtlz2_ax_optimizer_joblib_showcase.py)

@ mcptool: `aid2e`

```bash
(.venv) (base) amitbashyal@lpo-178574:~/Documents/BNL-AiD2E/mcp-server/AID2E-framework$ aid2e 
Usage: aid2e [OPTIONS] COMMAND [ARGS]...

  AID2E - AI assisted Detector Design for EIC.

  A framework for optimization of detector designs and other complex systems.

  Commands are organized into categories:

  Configuration Inspection:
    describe   - Quick summary of config files (auto-detects type)
    inspect    - Detailed configuration view with section filtering
    validate   - Validate configuration syntax and structure

  Workflow Execution:
    optimize   - Run optimization from configuration

  Utilities:
    list       - Show available optimizers/templates/problems
    version    - Display version information

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  describe  Describe the contents and structure of a configuration file.
  inspect   Display detailed information about a configuration file.
  list      List available optimizers, templates, or problem types.
  optimize  Run optimization based on configuration file.
  validate  Validate a configuration file without loading full context.
  version   Display version information.


```

3. Create mcptools needed to create optimization script when users provide information like schedulers (joblib, panda, slurm), configuration parameters (yaml file) and of course the optimization problem (dtlz2, bic, drich etc). As a starting point, we will start with simple dtlz2 problems. 

4. Create a mcp client that can access the aid2e mcp server and is able to use the mcp tools. 




