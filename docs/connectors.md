# Document input and MCP scope

The current product accepts uploaded text PDFs only. Google Drive and iManage are deferred at the user’s request. Their controls, discovery calls and runtime import/fetch routes are absent. Historical source metadata remains stored for existing records.

Supabase MCP is a development/provisioning connection, not document import or application credential delivery. See [service setup](setup.md).

`backend/app/connectors.py` and `scripts/test_connectors.py` retain an isolated adapter contract for future use. No active API endpoint exposes it. Tests cover simulated MCP initialization, JSON/SSE responses, exact PDF bytes and version checks; they do not establish a live document connection. Re-enabling a source requires a separate scope decision and known-file/version acceptance.
