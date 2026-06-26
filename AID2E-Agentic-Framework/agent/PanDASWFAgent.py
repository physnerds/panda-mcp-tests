import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.BaseAgent import BaseAgent
from agent.llm_providers import LLMProvider


DEFAULT_SWF_MCP_URL = "https://pandaserver02.sdcc.bnl.gov:8443/swf-monitor/mcp/"


class PanDASWFAgent(BaseAgent):
    """Agent for the PanDA-SWF MCP server."""

    def __init__(
        self,
        mcp_url: str = DEFAULT_SWF_MCP_URL,
        llm: Optional[LLMProvider] = None,
        token: Optional[str] = None,
        token_env_var: str = "SWF_MONITOR_TOKEN",
        fallback_token_env_var: str = "SWF_MONITOR_MCP_TOKEN",
        ssl_cert_dir_env_var: str = "SSL_CERT_DIR",
        ollama_url: str = "http://localhost:11434",
        transport_mode: str = "streamable-http",
        use_vllm: bool = False,
        vllm_url: Optional[str] = None,
        model: str = "mistral",
        tool_output_row_limit: int = 200,
    ):
        self.token_env_var = token_env_var
        self.fallback_token_env_var = fallback_token_env_var
        self.ssl_cert_dir_env_var = ssl_cert_dir_env_var
        self.ssl_cert_dir = self._require_ssl_cert_dir(ssl_cert_dir_env_var)
        env_token = self._require_token_env(token_env_var, fallback_token_env_var)
        self.swf_monitor_token = token or env_token
        self.tool_output_row_limit = tool_output_row_limit

        super().__init__(
            mcp_url=mcp_url,
            ollama_url=ollama_url,
            llm=llm,
            auth_token=self.swf_monitor_token,
            transport_mode=transport_mode,
            use_vllm=use_vllm,
            vllm_url=vllm_url,
            model=model,
            agent_name="PanDA-SWF Agent",
        )
        self.tool_output_row_limit = tool_output_row_limit

    def _require_env(self, env_var: str) -> str:
        value = os.environ.get(env_var)
        if not value:
            raise RuntimeError(f"{env_var} environment variable is not set.")
        return value

    def _require_token_env(self, env_var: str, fallback_env_var: Optional[str]) -> str:
        value = os.environ.get(env_var)
        if value:
            return value
        if fallback_env_var:
            fallback_value = os.environ.get(fallback_env_var)
            if fallback_value:
                return fallback_value
        raise RuntimeError(
            f"{env_var} environment variable is not set. "
            "PanDA-SWF access requires this token before agent initialization."
        )

    def _require_ssl_cert_dir(self, env_var: str) -> str:
        cert_dir = self._require_env(env_var)
        if not Path(cert_dir).is_dir():
            raise RuntimeError(
                f"{env_var} points to '{cert_dir}', but that directory does not exist."
            )
        return cert_dir

    def _build_headers(self, auth_token: Optional[str], vo: Optional[str]) -> Dict[str, str]:
        """Build SWF MCP headers. SWF monitor expects a bearer token."""
        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        if vo:
            headers["Origin"] = vo
        return headers

    def _format_tools_for_prompt(self) -> str:
        """Format discovered tools plus PanDA-specific local instructions."""
        tool_lines = []
        for tool in self.available_tools:
            desc_lines = (tool.description or "").strip().split("\n")
            short_desc = desc_lines[0] if desc_lines else ""
            params_info = self._format_tool_parameters(tool)
            instruction = self._load_tool_instruction(tool.name)
            if instruction:
                tool_lines.append(
                    f"- {tool.name}: {short_desc}{params_info}\n"
                    f"  Local usage instructions:\n{self._indent_text(instruction, '  ')}"
                )
            else:
                tool_lines.append(f"- {tool.name}: {short_desc}{params_info}")
        return "\n".join(tool_lines)

    def create_tool_reasoning_prompt(self, question: str) -> str:
        """Build a compact LLM fallback prompt from the most relevant tool instruction files."""
        candidates = self._rank_tool_instruction_candidates(question, limit=4)
        if not candidates:
            return super().create_tool_reasoning_prompt(question)

        sections = [
            "You are routing a PanDA-SWF user request to an MCP tool.",
            "Deterministic routing did not select a tool, so reason from the relevant tool instructions below.",
            "If a tool should be used, return exactly one JSON object with keys 'tool' and 'arguments'.",
            "If no tool is needed, answer the user directly. Do not invent unavailable tools or parameters.",
            "Prefer concise markdown tables for JSON-like tool results after the tool is executed.",
            "",
            "Relevant tools:",
        ]

        for tool, score, instruction in candidates:
            desc_lines = (tool.description or "").strip().split("\n")
            short_desc = desc_lines[0] if desc_lines else ""
            params_info = self._format_tool_parameters(tool)
            sections.append(
                f"\nTool: {tool.name}\n"
                f"Description: {short_desc}{params_info}\n"
                f"Relevance score: {score}\n"
                f"Instructions:\n{instruction}"
            )

        return "\n".join(sections).strip()

    def _rank_tool_instruction_candidates(
        self, question: str, limit: int = 4
    ) -> List[Tuple[Any, int, str]]:
        """Score local tool instruction files against the prompt and return the top tools."""
        scored = []
        for tool in self.available_tools:
            instruction = self._load_tool_instruction(tool.name)
            if not instruction:
                continue

            score = self._score_tool_instruction(question, tool, instruction)
            scored.append((tool, score, instruction))

        scored.sort(key=lambda item: (item[1], item[0].name), reverse=True)
        positive = [item for item in scored if item[1] > 0]
        return (positive or scored)[:limit]

    def _score_tool_instruction(self, question: str, tool: Any, instruction: str) -> int:
        q = question.lower()
        question_tokens = self._routing_tokens(question)
        corpus = f"{tool.name} {tool.description or ''} {instruction}"
        corpus_tokens = self._routing_tokens(corpus)

        score = 0
        for token in question_tokens:
            if token in corpus_tokens:
                score += 2
            if token and token in tool.name.lower():
                score += 3

        metadata = self._load_tool_instruction_metadata(tool.name)
        for keyword in metadata.get("keywords", []):
            keyword_lower = keyword.lower()
            keyword_tokens = self._routing_tokens(keyword_lower)
            if keyword_lower and keyword_lower in q:
                score += 12
            elif keyword_tokens and keyword_tokens.issubset(question_tokens):
                score += 8
            elif keyword_tokens and question_tokens.intersection(keyword_tokens):
                score += len(question_tokens.intersection(keyword_tokens))

        tool_name = tool.name.lower()
        pandaids = self._extract_pandaids(question)
        if pandaids and "study_job" in tool_name:
            score += 25
        if re.search(r"\berrors?\b", q) and "error_summary" in tool_name:
            score += 20
        if re.search(r"\bqueues?\b", q) and "queue" in tool_name:
            score += 18
        if re.search(r"\btasks?\b", q) and "tasks" in tool_name:
            score += 18
        if re.search(r"\bharvester|workers?\b", q) and "harvester" in tool_name:
            score += 18
        if re.search(r"\bresource|usage|core[- ]?hour", q) and "resource_usage" in tool_name:
            score += 18
        if re.search(r"\bactivity|overview\b", q) and "activity" in tool_name:
            score += 18
        if re.search(r"\bdiagnos|fault|failed|pilot|ddm|executor\b", q) and "diagnose" in tool_name:
            score += 14

        return score

    def _routing_tokens(self, text: str) -> set:
        stopwords = {
            "a", "an", "and", "are", "as", "for", "from", "give", "i", "in",
            "include", "is", "last", "me", "of", "on", "please", "show", "the",
            "to", "use", "with", "you", "your",
        }
        return {
            token
            for token in re.findall(r"[a-z0-9_]+", text.lower())
            if len(token) > 1 and token not in stopwords
        }

    def _load_tool_instruction(self, tool_name: str) -> str:
        instruction_path = Path(__file__).parent / "tool_instructions" / f"{tool_name}.md"
        if not instruction_path.exists():
            return ""
        return instruction_path.read_text(encoding="utf-8").strip()

    def _indent_text(self, text: str, prefix: str) -> str:
        return "\n".join(f"{prefix}{line}" if line else prefix.rstrip() for line in text.splitlines())

    def format_available_tools(self) -> str:
        """Render available tools with MCP descriptions and local PanDA usage instructions."""
        if not self.available_tools:
            return "No tools are currently available from the connected MCP server."

        lines = [f"Available tools ({len(self.available_tools)}):"]
        for tool in self.available_tools:
            description = (tool.description or "").strip()
            instruction = self._load_tool_instruction(tool.name)
            if description:
                line = f"- {tool.name}:\n{description}"
            else:
                line = f"- {tool.name}"
            if instruction:
                line += f"\n\nUsage and output instructions:\n{instruction}"
            lines.append(line)
        return "\n\n".join(lines)

    def discover_tool_call(self, question: str) -> Tuple[Optional[str], Optional[dict]]:
        """Select common PanDA-SWF tool calls before asking the LLM."""
        single_job_call = self._discover_single_job_call(question)
        if single_job_call[0]:
            return single_job_call

        instruction_call = self._discover_instruction_tool_call(question)
        if instruction_call[0]:
            return instruction_call

        error_call = self._discover_error_summary_call(question)
        if error_call[0]:
            return error_call

        job_call = self._discover_list_jobs_call(question)
        if job_call[0]:
            return job_call
        return None, None

    def recover_tool_call_after_llm_failure(
        self, question: str
    ) -> Tuple[Optional[str], Optional[dict]]:
        """Use the highest-ranked local instruction file if the LLM gives no response."""
        candidates = self._rank_tool_instruction_candidates(question, limit=1)
        if not candidates:
            return None, None

        tool, score, _ = candidates[0]
        if score <= 0:
            return None, None

        metadata = self._load_tool_instruction_metadata(tool.name)
        arguments = self._arguments_from_instruction_metadata(question, metadata)
        arguments = self._filter_arguments_for_tool(tool.name, arguments)
        if not self._tool_has_required_arguments(tool.name, arguments):
            return None, None

        return tool.name, arguments

    def _tool_has_required_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        schema = None
        for tool in self.available_tools:
            if tool.name == tool_name:
                schema = tool.inputSchema
                break

        if not isinstance(schema, dict):
            return True

        required = schema.get("required") or []
        return all(name in arguments for name in required)

    async def process_question(self, question: str):
        """Process PanDA-SWF questions, including repeated study calls for multiple jobs."""
        multi_job_call = self._discover_multi_job_study_call(question)
        if not multi_job_call:
            return await super().process_question(question)

        self.reset_token_usage_tracking()
        tool_name, pandaids = multi_job_call
        print(f"Agent: Using tool '{tool_name}' for {len(pandaids)} jobs...")

        results = []
        for pandaid in pandaids:
            arguments = self._filter_arguments_for_tool(tool_name, {"pandaid": pandaid})
            raw_tool_result = await self.execute_tool(tool_name, arguments)
            tool_result = self.normalize_tool_result(raw_tool_result)
            results.append(
                {
                    "pandaid": pandaid,
                    "arguments": arguments,
                    "result": tool_result,
                    "error": self.tool_result_has_error(tool_result),
                }
            )

        response = self._format_multi_study_job_response(results)
        response = self.append_token_usage_if_requested(question, response)
        print(f"Agent: {response}")
        return response

    def _discover_multi_job_study_call(self, question: str) -> Optional[Tuple[str, List[int]]]:
        pandaids = self._extract_pandaids(question)
        if len(pandaids) < 2:
            return None

        q = question.strip().lower()
        study_patterns = [
            r"\bsummary\b",
            r"\bsummarize\b",
            r"\bstudy\b",
            r"\binspect\b",
            r"\bdetails?\b",
            r"\bstatus\b",
            r"\burls?\b",
            r"\bmonitor\b",
            r"\blogs?\b",
            r"\bfiles?\b",
            r"\berrors?\b",
            r"\bjobs?\b",
            r"\bpanda[- ]?ids?\b",
        ]
        if not any(re.search(pattern, q) for pattern in study_patterns):
            return None

        tool_name = self._find_tool_name(["panda_study_job", "study_job"])
        if not tool_name:
            return None

        return tool_name, pandaids

    def _discover_single_job_call(self, question: str) -> Tuple[Optional[str], Optional[dict]]:
        pandaid = self._extract_pandaid(question)
        if pandaid is None:
            return None, None

        q = question.strip().lower()
        single_job_patterns = [
            r"\bpandaid\b",
            r"\bjobs?(?:\s+id)?\s*#?\s*\d{5,}\b",
            r"#\d{5,}\b",
            r"\b(study|inspect|diagnose|explain|summarize|summary|details?|status|url|monitor|log|files?|errors?)\b.*\bjobs?\b",
            r"\bjobs?\b.*\b(study|inspect|diagnose|explain|summarize|summary|details?|status|url|monitor|log|files?|errors?)\b",
        ]
        if not any(re.search(pattern, q) for pattern in single_job_patterns):
            return None, None

        tool_name = self._find_tool_name(["panda_study_job", "study_job"])
        if not tool_name:
            return None, None

        return tool_name, self._filter_arguments_for_tool(tool_name, {"pandaid": pandaid})

    def _discover_instruction_tool_call(self, question: str) -> Tuple[Optional[str], Optional[dict]]:
        q = question.strip().lower()
        for tool in self.available_tools:
            metadata = self._load_tool_instruction_metadata(tool.name)
            keywords = metadata.get("keywords", [])
            if not keywords:
                continue
            if not any(keyword.lower() in q for keyword in keywords):
                continue

            arguments = self._arguments_from_instruction_metadata(question, metadata)
            if not arguments:
                continue
            return tool.name, self._filter_arguments_for_tool(tool.name, arguments)

        return None, None

    def _load_tool_instruction_metadata(self, tool_name: str) -> Dict[str, List[str]]:
        instruction = self._load_tool_instruction(tool_name)
        metadata = {"keywords": [], "examples": []}
        current_section = None

        for raw_line in instruction.splitlines():
            line = raw_line.strip()
            lower = line.lower()
            if lower == "keywords:":
                current_section = "keywords"
                continue
            if lower == "examples:":
                current_section = "examples"
                continue
            if re.match(r"^[A-Za-z ].+:$", line):
                current_section = None
                continue
            if current_section and line.startswith("-"):
                metadata[current_section].append(line[1:].strip())

        return metadata

    def _arguments_from_instruction_metadata(
        self, question: str, metadata: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        arguments = {}
        pandaid = self._extract_pandaid(question)
        if pandaid is not None:
            arguments["pandaid"] = pandaid

        days = self._extract_int_before_unit(question.lower(), ["day", "days"])
        if days is not None:
            arguments["days"] = days

        limit = self._extract_limit(question.lower())
        if limit is not None:
            arguments["limit"] = limit

        status = self._extract_job_status(question.lower())
        if status:
            arguments["status"] = status

        user = self._extract_user_filter(question)
        if user:
            arguments["user"] = user

        site = self._extract_named_filter(question, ["site", "queue"])
        if site:
            arguments["site"] = site

        return arguments

    def _discover_error_summary_call(self, question: str) -> Tuple[Optional[str], Optional[dict]]:
        q = question.strip().lower()
        if not re.search(r"\berrors?\b", q):
            return None, None
        if not re.search(r"\b(summary|summarize|patterns?|counts?|top|ranked)\b", q):
            return None, None

        tool_name = self._find_tool_name(["panda_error_summary", "error_summary"])
        if not tool_name:
            return None, None

        arguments = {}
        days = self._extract_int_before_unit(q, ["day", "days"])
        if days is not None:
            arguments["days"] = days

        limit = self._extract_limit(q)
        if limit is not None:
            arguments["limit"] = limit

        user = self._extract_user_filter(question)
        if user:
            arguments["user"] = user

        site = self._extract_named_filter(question, ["site", "queue"])
        if site:
            arguments["site"] = site

        return tool_name, self._filter_arguments_for_tool(tool_name, arguments)

    def _discover_list_jobs_call(self, question: str) -> Tuple[Optional[str], Optional[dict]]:
        q = question.strip().lower()
        if self._extract_pandaid(question) is not None:
            return None, None
        if not re.search(r"\bjobs?\b", q):
            return None, None
        if not re.search(r"\b(list|show|give|find|get|return)\b", q):
            return None, None

        tool_name = self._find_tool_name(["panda_list_jobs", "list_jobs"])
        if not tool_name:
            return None, None

        arguments = {}
        status = self._extract_job_status(q)
        if status:
            arguments["status"] = status

        days = self._extract_int_before_unit(q, ["day", "days"])
        if days is not None:
            arguments["days"] = days

        limit = self._extract_limit(q)
        if limit is not None:
            arguments["limit"] = limit

        user = self._extract_user_filter(question)
        if user:
            arguments["user"] = user

        site = self._extract_named_filter(question, ["site", "queue"])
        if site:
            arguments["site"] = site

        return tool_name, self._filter_arguments_for_tool(tool_name, arguments)

    def _find_tool_name(self, candidates: List[str]) -> Optional[str]:
        available = {tool.name for tool in self.available_tools}
        for candidate in candidates:
            if candidate in available:
                return candidate
        for tool_name in available:
            if all(part in tool_name for part in candidates[-1].split("_")):
                return tool_name
        return None

    def _extract_pandaid(self, question: str) -> Optional[int]:
        pandaids = self._extract_pandaids(question)
        if pandaids:
            return pandaids[0]
        return None

    def _extract_pandaids(self, question: str) -> List[int]:
        patterns = [
            r"#(\d{5,})\b",
            r"\bpandaid\s*[:#]?\s*(\d{5,})\b",
            r"\bpanda[- ]?ids?\s*[:#]?\s*((?:\d{5,}[\s,;]*(?:and\s*)?)+)",
            r"\bjob(?:\s+id)?\s*#?\s*(\d{5,})\b",
            r"\b(\d{5,})\b",
        ]
        pandaids = []
        for pattern in patterns:
            for match in re.finditer(pattern, question, flags=re.IGNORECASE):
                for value in re.findall(r"\d{5,}", match.group(0)):
                    pandaid = int(value)
                    if pandaid not in pandaids:
                        pandaids.append(pandaid)
        return pandaids

    def _extract_job_status(self, question: str) -> Optional[str]:
        statuses = [
            "running",
            "finished",
            "failed",
            "cancelled",
            "activated",
            "defined",
            "assigned",
            "starting",
            "pending",
            "holding",
            "transferring",
        ]
        for status in statuses:
            if re.search(rf"\b{re.escape(status)}\b", question):
                return status
        return None

    def _extract_int_before_unit(self, question: str, units: List[str]) -> Optional[int]:
        unit_pattern = "|".join(re.escape(unit) for unit in units)
        match = re.search(rf"\b(\d+)\s*(?:{unit_pattern})\b", question)
        if match:
            return int(match.group(1))
        return None

    def _extract_limit(self, question: str) -> Optional[int]:
        patterns = [
            r"\blimit(?:ed)?(?:\s+the\s+list)?(?:\s+of\s+jobs)?\s+(?:to\s+)?(\d+)\b",
            r"\bfirst\s+(\d+)\b",
            r"\btop\s+(\d+)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, question)
            if match:
                return int(match.group(1))
        return None

    def _extract_user_filter(self, question: str) -> Optional[str]:
        patterns = [
            r"\bfrom+\s+(?:the\s+)?user\s+([A-Za-z][A-Za-z0-9_. -]*?)(?:\s+(?:in|on|from|for|last|limit|with)\b|[.?!,]|$)",
            r"\buser\s+([A-Za-z][A-Za-z0-9_. -]*?)(?:\s+(?:in|on|from|for|last|limit|with)\b|[.?!,]|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, question, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_named_filter(self, question: str, names: List[str]) -> Optional[str]:
        name_pattern = "|".join(re.escape(name) for name in names)
        pattern = rf"\b(?:{name_pattern})\s+([A-Za-z0-9_.%:-]+)"
        match = re.search(pattern, question, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    def _filter_arguments_for_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        schema = None
        for tool in self.available_tools:
            if tool.name == tool_name:
                schema = tool.inputSchema
                break

        if not isinstance(schema, dict):
            return arguments

        properties = schema.get("properties")
        if not isinstance(properties, dict) or not properties:
            return arguments

        aliases = {
            "user": ["user", "username", "produsername", "prod_user_name"],
            "site": ["site", "computingsite", "computing_site"],
            "status": ["status", "jobstatus", "taskstatus"],
            "pandaid": ["pandaid", "panda_id"],
        }

        filtered = {}
        for key, value in arguments.items():
            if key in properties:
                filtered[key] = value
                continue

            for alias in aliases.get(key, []):
                if alias in properties:
                    filtered[alias] = value
                    break

        return filtered

    def format_tool_result_response(
        self, tool_name: str, tool_result: Any, arguments: Optional[dict] = None
    ) -> str:
        """Render PanDA-SWF tool output as concise markdown tables where possible."""
        if tool_name == "panda_error_summary":
            return self._format_error_summary_payload(tool_result)

        jobs_payload = self._find_jobs_payload(tool_result)
        if jobs_payload:
            if tool_name == "panda_diagnose_jobs":
                return self._format_records_payload(
                    jobs_payload,
                    list_keys=["jobs", "diagnostics", "records", "items"],
                    title="Diagnosed jobs",
                    columns=[
                        ("pandaid", ["pandaid", "panda_id"]),
                        ("status", ["jobstatus", "status"]),
                        ("site", ["computingsite", "site"]),
                        ("user", ["produsername", "prod_user_name", "user"]),
                        ("task", ["jeditaskid", "panda_task_id", "taskid", "reqid"]),
                        ("source", ["source", "error_source", "diag_source"]),
                        ("code", ["error_code", "piloterrorcode", "exeerrorcode", "ddmerrorcode"]),
                        ("diagnostic", ["diagnostic", "piloterrordiag", "exeerrordiag", "ddmerrordiag", "error", "message"]),
                    ],
                )
            return self._format_jobs_payload(jobs_payload)

        if tool_name == "panda_list_tasks":
            return self._format_records_payload(
                tool_result,
                list_keys=["tasks", "jedi_tasks", "items", "results"],
                title="Tasks",
                columns=[
                    ("task", ["jeditaskid", "taskid", "panda_task_id", "reqid"]),
                    ("status", ["status", "taskstatus"]),
                    ("user", ["username", "produsername", "prod_user_name", "user"]),
                    ("site", ["site", "computingsite"]),
                    ("created", ["creationtime", "created", "creation_time"]),
                    ("jobs", ["n_jobs", "njobs", "jobs", "job_count"]),
                    ("failed", ["failed", "n_failed", "failed_jobs"]),
                ],
            )

        if tool_name in {
            "panda_list_queues",
            "panda_harvester_workers",
            "panda_resource_usage",
            "panda_get_queue",
            "panda_get_activity",
            "panda_study_job",
        }:
            return self._format_generic_structured_payload(tool_result)

        if isinstance(tool_result, (dict, list)):
            return self._format_generic_structured_payload(tool_result)
        return str(tool_result)

    def _format_error_summary_payload(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return str(payload)

        lines = self._format_scalar_summary_lines(payload)
        records = self._first_list_value(
            payload, ["errors", "error_summary", "patterns", "results", "items", "rows"]
        )
        if records:
            if lines:
                lines.append("")
            lines.extend(
                self._records_table_lines(
                    records,
                    [
                        ("error", ["error", "message", "diagnostic", "pattern", "error_pattern", "description"]),
                        ("count", ["count", "n", "total", "jobs", "job_count"]),
                        ("users", ["users", "affected_users", "produsers", "produsername"]),
                        ("sites", ["sites", "affected_sites", "computingsite", "site"]),
                        ("tasks", ["tasks", "task_count", "affected_tasks", "jeditaskids"]),
                    ],
                )
            )
            return "\n".join(lines)
        return self._format_generic_structured_payload(payload)

    def _format_records_payload(
        self,
        payload: Any,
        list_keys: List[str],
        title: str,
        columns: List[Tuple[str, List[str]]],
    ) -> str:
        if not isinstance(payload, dict):
            return str(payload)

        lines = self._format_scalar_summary_lines(payload)
        records = self._first_list_value(payload, list_keys) or []
        if records:
            lines.append("")
            lines.append(f"{title}: {len(records)}")
            lines.extend(self._records_table_lines(records, columns))
        return "\n".join(lines) if lines else json.dumps(payload, indent=2, default=str)

    def _format_generic_structured_payload(self, payload: Any) -> str:
        if isinstance(payload, list):
            if payload and all(isinstance(item, dict) for item in payload):
                return "\n".join(self._generic_records_table_lines(payload))
            return json.dumps(payload, indent=2, default=str)

        if not isinstance(payload, dict):
            return str(payload)

        lines = self._format_scalar_summary_lines(payload)
        rendered_list = False
        for key, value in payload.items():
            if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                if lines:
                    lines.append("")
                lines.append(f"{key}: {len(value)}")
                lines.extend(self._generic_records_table_lines(value))
                rendered_list = True

        if lines and rendered_list:
            return "\n".join(lines)
        if lines:
            return "\n".join(lines)
        return json.dumps(payload, indent=2, default=str)

    def _format_scalar_summary_lines(self, payload: Dict[str, Any]) -> List[str]:
        lines = []
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                continue
            lines.append(f"{key}: {self._markdown_cell(value)}")

        summary = payload.get("summary")
        if isinstance(summary, dict):
            if lines:
                lines.append("")
            lines.append("Summary:")
            lines.extend(self._dict_table_lines(summary))

        filters = payload.get("filters")
        if isinstance(filters, dict):
            if lines:
                lines.append("")
            lines.append("Filters:")
            lines.extend(self._dict_table_lines(filters))

        return lines

    def _dict_table_lines(self, data: Dict[str, Any]) -> List[str]:
        lines = ["| field | value |", "| --- | --- |"]
        for key, value in data.items():
            lines.append(f"| {self._markdown_cell(key)} | {self._markdown_cell(self._compact_value(value))} |")
        return lines

    def _first_list_value(self, payload: Dict[str, Any], keys: List[str]) -> Optional[List[Any]]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        for value in payload.values():
            if isinstance(value, dict):
                nested = self._first_list_value(value, keys)
                if nested:
                    return nested
        return None

    def _generic_records_table_lines(self, records: List[Dict[str, Any]]) -> List[str]:
        keys = []
        for record in records[: self.tool_output_row_limit]:
            for key, value in record.items():
                if isinstance(value, (dict, list)):
                    continue
                if key not in keys:
                    keys.append(key)
                if len(keys) >= 8:
                    break
            if len(keys) >= 8:
                break

        columns = [(key, [key]) for key in keys]
        return self._records_table_lines(records, columns)

    def _records_table_lines(
        self, records: List[Any], columns: List[Tuple[str, List[str]]]
    ) -> List[str]:
        visible_records = records[: self.tool_output_row_limit]
        lines = [
            "| " + " | ".join(label for label, _ in columns) + " |",
            "| " + " | ".join("---" for _ in columns) + " |",
        ]
        for record in visible_records:
            row = [
                self._markdown_cell(self._compact_value(self._first_present(record, keys)))
                for _, keys in columns
            ]
            lines.append("| " + " | ".join(row) + " |")
        if len(records) > len(visible_records):
            lines.append(f"Showing first {len(visible_records)} of {len(records)} rows.")
        return lines

    def _find_jobs_payload(self, value: Any) -> Optional[Dict[str, Any]]:
        if isinstance(value, dict):
            if isinstance(value.get("jobs"), list):
                return value
            for child in value.values():
                payload = self._find_jobs_payload(child)
                if payload:
                    return payload
        elif isinstance(value, list):
            for child in value:
                payload = self._find_jobs_payload(child)
                if payload:
                    return payload
        return None

    def _format_jobs_payload(self, payload: Dict[str, Any]) -> str:
        jobs = payload.get("jobs") or []
        total = payload.get("total_in_window", len(jobs))
        summary = payload.get("summary")
        has_more = payload.get("has_more")
        next_before_id = payload.get("next_before_id")
        visible_jobs = jobs[: self.tool_output_row_limit]

        lines = [f"Jobs returned: {len(jobs)}", f"Total in window: {total}"]
        if summary is not None:
            lines.append(f"Summary: {json.dumps(summary, default=str)}")
        if has_more is not None:
            lines.append(f"More available: {has_more}")
        if next_before_id is not None:
            lines.append(f"Next before_id: {next_before_id}")
        if len(jobs) > len(visible_jobs):
            lines.append(
                f"Showing first {len(visible_jobs)} rows. Increase tool_output_row_limit to display more."
            )

        if not visible_jobs:
            return "\n".join(lines)

        columns = [
            ("pandaid", ["pandaid", "panda_id"]),
            ("status", ["jobstatus", "status"]),
            ("site", ["computingsite", "site", "computing_site"]),
            ("user", ["produsername", "prod_user_name", "user"]),
            ("task", ["jeditaskid", "panda_task_id", "taskid", "reqid"]),
            ("start", ["starttime", "start_time"]),
            ("priority", ["priority", "currentpriority"]),
            ("runtime", ["runtime", "runtime_seconds"]),
        ]

        lines.append("")
        lines.extend(self._records_table_lines(visible_jobs, columns))
        return "\n".join(lines)

    def _format_multi_study_job_response(self, results: List[Dict[str, Any]]) -> str:
        lines = [f"Studied jobs: {len(results)}"]

        failures = [item for item in results if item["error"]]
        if failures:
            lines.append(f"Failed jobs: {len(failures)}")

        records = []
        for item in results:
            record = self._study_job_summary_record(item["pandaid"], item["result"])
            if item["error"]:
                record["error"] = self._compact_value(item["result"])
            records.append(record)

        lines.append("")
        lines.extend(
            self._records_table_lines(
                records,
                [
                    ("pandaid", ["pandaid"]),
                    ("status", ["status"]),
                    ("site", ["site"]),
                    ("user", ["user"]),
                    ("task", ["task"]),
                    ("start", ["start"]),
                    ("end", ["end"]),
                    ("files", ["files"]),
                    ("monitor_url", ["monitor_url"]),
                ],
            )
        )

        error_records = [
            record
            for record in records
            if record.get("pilot_error")
            or record.get("exe_error")
            or record.get("ddm_error")
            or record.get("error")
        ]
        if error_records:
            lines.append("")
            lines.append("Errors:")
            lines.extend(
                self._records_table_lines(
                    error_records,
                    [
                        ("pandaid", ["pandaid"]),
                        ("pilot_error", ["pilot_error"]),
                        ("exe_error", ["exe_error"]),
                        ("ddm_error", ["ddm_error"]),
                        ("error", ["error"]),
                    ],
                )
            )

        return "\n".join(lines)

    def _study_job_summary_record(self, pandaid: int, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {
                "pandaid": pandaid,
                "status": "",
                "site": "",
                "user": "",
                "task": "",
                "files": "",
            }

        job = self._find_job_record(payload) or payload
        files = self._first_list_value(payload, ["files", "file_records", "job_files"]) or []

        return {
            "pandaid": self._first_present(job, ["pandaid", "panda_id"]) or pandaid,
            "status": self._first_present(job, ["jobstatus", "status"]),
            "site": self._first_present(job, ["computingsite", "site", "computing_site"]),
            "user": self._first_present(job, ["produsername", "prod_user_name", "user"]),
            "task": self._first_present(job, ["jeditaskid", "panda_task_id", "taskid", "reqid"]),
            "start": self._first_present(job, ["starttime", "start_time"]),
            "end": self._first_present(job, ["endtime", "end_time"]),
            "files": len(files),
            "monitor_url": self._first_present(payload, ["monitor_url", "url", "job_url"]),
            "pilot_error": self._first_present(job, ["piloterrordiag", "pilot_error", "piloterrorcode"]),
            "exe_error": self._first_present(job, ["exeerrordiag", "exe_error", "exeerrorcode"]),
            "ddm_error": self._first_present(job, ["ddmerrordiag", "ddm_error", "ddmerrorcode"]),
        }

    def _find_job_record(self, value: Any) -> Optional[Dict[str, Any]]:
        if isinstance(value, dict):
            if any(key in value for key in ["pandaid", "panda_id", "jobstatus", "computingsite"]):
                return value
            for child in value.values():
                record = self._find_job_record(child)
                if record:
                    return record
        elif isinstance(value, list):
            for child in value:
                record = self._find_job_record(child)
                if record:
                    return record
        return None

    def _first_present(self, data: Any, keys: List[str]) -> Any:
        if not isinstance(data, dict):
            return ""
        for key in keys:
            value = data.get(key)
            if value is not None:
                return value
        return ""

    def _markdown_cell(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).replace("\n", " ").replace("|", "\\|")

    def _compact_value(self, value: Any) -> Any:
        if isinstance(value, list):
            if len(value) <= 4:
                return ", ".join(str(item) for item in value)
            return ", ".join(str(item) for item in value[:4]) + f", ... ({len(value)} total)"
        if isinstance(value, dict):
            return json.dumps(value, default=str)
        return value
