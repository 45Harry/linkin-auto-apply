# Tool discovery: job-intake stack (2026-10-14)

Source: `npx -y skills find <tool>` (install counts as reported by skills.sh) plus 6 web searches for MCP servers. Nothing was installed. Candidates are listed as found, not vetted.

## Agent Skills (installable via `npx skills add owner/repo@skill`)

### Python (service code)
- microsoft/azure-skills@python-appservice-deploy (216K installs): Azure App Service deploy, not a general Python skill
- wshobson/agents@python-testing-patterns (35.5K): pytest patterns
- wshobson/agents@python-performance-optimization (34.7K): profiling and perf
- wshobson/agents@python-design-patterns (22.3K): structure and design
- wshobson/agents@async-python-patterns (17.5K): asyncio patterns
- wshobson/agents@python-code-style (16K): style and linting
- wshobson/agents@python-configuration (11.2K): config and settings handling

### Pydantic
- pydantic/skills@pydantic (1.9K): core pydantic model guidance
- pydantic/skills@pydantic-ai-harness (2.3K): pydantic-ai, may not fit a plain service
- fastapi/fastapi@fastapi (12.2K): official FastAPI skill, only useful if FastAPI is adopted

### SQLite
- martinholovsky/claude-skills-generator@SQLite Database Expert: general SQLite guidance
- prisma/skills@prisma-orm-setup (37.3K) and giuseppe-trisciuoglio/developer-kit@drizzle-orm-patterns (5.2K): ORM skills, likely not relevant to raw sqlite3

### Gmail API (google-api-python-client)
- acedatacloud/skills@google-gmail (217): Gmail API usage
- okou-ai/okou-skills@gmail (184): Gmail API usage
- the-focus-ai/google-skill@gmail (119): Gmail skill from a Google-focused bundle
- mitsuhiko/agent-stuff@google-workspace (101): Workspace APIs
- hoodini/ai-agents-skills@google-workspace-cli (455): gws CLI, not the Python client
- Note: check each before use; none is from Google itself.

### Ollama
- yoanbernabeu/grepai-skills@grepai-ollama-setup (786) and grepai-embeddings-ollama (714): Ollama setup and embeddings
- bobmatnyc/claude-mpm-skills@local-llm-ops (441): local LLM operations
- hkuds/cli-anything@cli-anything-ollama (511): CLI wrapper for Ollama
- grafana/skills@ml-ai (3.7K): broad ML/AI, weak fit

### SearXNG
- ypares/agent-skills@searxng-search (822)
- xyenon/agents@searxng-search (53), varlabz/skills@searxng-search (48), walterra/agent-tools@searxng-search (38): same skill name, lower installs
- robbyczgw-cla/web-search-plus@web-search-plus (1.2K): multi-engine search, may overlap SearXNG
- Note: none is official. Install counts are low.

### Docker / Docker Compose
- docker/skills@docker-compose-patterns (867): official Docker publisher, compose patterns
- docker/skills@docker-project-foundations (719): official Docker publisher
- affaan-m/ecc@docker-patterns (13.2K): general Docker patterns
- ailabs-393/ai-labs-claude-skills@docker-containerization (1.1K)
- manutej/luxor-claude-marketplace@docker-compose-orchestration (2.9K)

### Anthropic SDK (likely redundant with built-in claude-api skill)
- affaan-m/ecc@claude-api (2.4K): duplicates built-in claude-api
- bobmatnyc/claude-mpm-skills@anthropic-sdk (254): SDK usage, duplicate
- Only consider if the built-in skill proves insufficient.

### OpenAI Python SDK (xAI Grok and Gemini compatible endpoints)
- openai/openai-agents-python@docs-sync (221) and implementation-strategy (127): Agents SDK, not the chat client, so weak fit
- thatjuan/agent-skills@openrouter-api (41): OpenRouter, not directly relevant
- pydantic/skills@migrating-openai-agents-sdk-to-pydantic-ai (222): migration, weak fit
- Note: no skill found for the plain openai client against xAI or Gemini endpoints.

### APScheduler
- slanycukr/riot-api-project@apscheduler (32): APScheduler usage
- davidcastagnetoa/skills@apscheduler_celery_beat (14): APScheduler vs Celery beat comparison
- Note: low install counts, treat as weak.

### Oracle Cloud (OCI)
- oracle/skills@oci (465): official Oracle publisher, the best candidate here
- dauquangthanh/hanoi-rainbow@oracle-cloud (145): generic OCI guidance
- frankxai/claude-skills-library@oci-services-expert (41), evolv3-ai/vibe-skills@oci (32): low installs
- Note: membranedev/* Oracle Fusion skills are SaaS apps, not OCI infrastructure, so skip.

## MCP servers (web search, no fetches)

### Gmail
- Google's own Gmail API MCP reference at gmailmcp.googleapis.com (Developer Preview). Sources disagree on tool count and scope, and one listing says there is no official server. Verify at developers.google.com/workspace/gmail/api/reference/mcp.
- Community servers exist (e.g. nvdpsingh/GmailMCPServer on Glama). Unvetted.

### Ollama
- NightTrek/Ollama-mcp (listed on glama.ai and mcpservers.org): model management, execution, and an OpenAI-compatible chat endpoint. Most listed. Not verified as official.
- A Python project by Kai Kogure (March 2025, playbooks.com): task decomposition for local models. Unverified.

### SearXNG
- Sacode/searxng-simple-mcp: self-hosted SearXNG search, installable via pipx, uvx, pip, or Docker
- mcp-searxng (npm, 0.3.1): searxng_web_search with pagination and filters
- searxng-mcp-ts (npm, 0.1.2): TypeScript, configured SearXNG instance
- secretiveshell/mcp-searxng (Archestra catalog): uvx install
- None is official. All require your own SearXNG instance.

### Docker
- Docker Desktop MCP Toolkit and Gateway (`docker mcp gateway run`): Docker's own route, with a catalog of servers
- Docker Hub MCP catalog listing per the search; the standalone "Docker MCP Server" entries are community projects
- Not confirmed from docs.docker.com. Verify there before use.

### SQLite
- Many unrelated community projects (Glama listings and GitHub). Examples: execute_sql/list_tables/get_table_schema (Python FastMCP), and read/write with schema tools (Bun).
- One toolradar page says the SQLite server was once in Anthropic's reference set. Unconfirmed.
- No single canonical server found.

### Oracle Cloud (OCI)
- Oracle appears to publish an official OCI MCP server suite (Compute, Networking, Object Storage, Database, Identity, Monitoring, and more). Found only on a mintlify mirror, not oracle.com. Verify in Oracle's official repo.
- Community servers: jopsis/mcp-server-oci, dockndevai/mcp-oci, and a Python OCI profile-switching server. Read-only default is common. Unvetted.

## Not found / nothing credible
- SearXNG: no official MCP server, only community servers
- Ollama: no official MCP server confirmed
- Gmail: official status conflicting
- Anthropic SDK, OpenAI Python SDK, APScheduler, pydantic, Python, Docker Compose: no MCP searches run (search budget spent on the above). Treat as not searched.
