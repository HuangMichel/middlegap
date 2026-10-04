"""Configured Streamable HTTP MCP fetch bridge; no desktop-session assumptions.

The configured tool must return exact PDF bytes encoded as base64 and authoritative
provider version metadata. The adapter neither follows download links nor reads
arbitrary local paths from tool output.
"""
import base64
import binascii
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_PDF_BYTES = 32 * 1024 * 1024
MAX_RESPONSE_BYTES = 48 * 1024 * 1024
PROTOCOL_VERSION = "2025-06-18"


class ConnectorError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def connector_config(source):
    prefix = {"google_drive": "GOOGLE_DRIVE", "imanage": "IMANAGE"}.get(source)
    if not prefix:
        raise ConnectorError("Source must be google_drive or imanage", 422)
    url, tool = os.getenv(prefix + "_MCP_URL"), os.getenv(prefix + "_MCP_TOOL")
    if not url or not tool:
        raise ConnectorError("This source has no configured application MCP fetch bridge", 501)
    parsed = urlparse(url)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")):
        raise ConnectorError("Configure an HTTPS MCP endpoint or a local HTTP endpoint", 503)
    if parsed.username or parsed.password:
        raise ConnectorError("Supply bridge credentials through the server token variable", 503)
    return url, tool, os.getenv(prefix + "_MCP_TOKEN")


def connector_status():
    return {source: bool(os.getenv(prefix + "_MCP_URL") and os.getenv(prefix + "_MCP_TOOL"))
            for source, prefix in (("google_drive", "GOOGLE_DRIVE"), ("imanage", "IMANAGE"))}


class MCPClient:
    def __init__(self, url, token=None):
        self.url = url
        self.session = None
        self.version = PROTOCOL_VERSION
        self.token = token

    def call(self, method, params=None, request_id=None):
        body = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if request_id is not None:
            body["id"] = request_id
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": self.version}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        try:
            with urlopen(Request(self.url, data=json.dumps(body).encode(), headers=headers, method="POST"), timeout=90) as response:
                session = response.headers.get("Mcp-Session-Id")
                if session:
                    self.session = session
                if request_id is None:
                    return None
                if "text/event-stream" in response.headers.get("Content-Type", ""):
                    # Servers may send notifications before the matching response.
                    size, data_lines, message = 0, [], None
                    for line in response:
                        size += len(line)
                        if size > MAX_RESPONSE_BYTES:
                            raise ConnectorError("MCP response exceeds the import size limit")
                        decoded = line.decode("utf-8").rstrip("\r\n")
                        if decoded.startswith("data:"):
                            data_lines.append(decoded[5:].lstrip())
                        elif not decoded and data_lines:
                            candidate = json.loads("\n".join(data_lines))
                            data_lines = []
                            if candidate.get("id") == request_id:
                                message = candidate
                                break
                    if message is None:
                        raise ConnectorError("MCP stream ended without the requested response")
                else:
                    payload = response.read(MAX_RESPONSE_BYTES + 1)
                    if len(payload) > MAX_RESPONSE_BYTES:
                        raise ConnectorError("MCP response exceeds the import size limit")
                    message = json.loads(payload)
                if message.get("id") != request_id or "error" in message or "result" not in message:
                    raise ConnectorError("MCP fetch failed or returned an invalid response")
                return message["result"]
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            # Never return provider response bodies or credential-bearing URLs.
            raise ConnectorError("The configured MCP bridge could not be reached; check server configuration") from error
        except (ValueError, UnicodeError, AttributeError) as error:
            raise ConnectorError("MCP bridge returned an invalid JSON response") from error

    def initialize(self):
        response = self.call("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                              "clientInfo": {"name": "middlegap", "version": "0.1.0"}}, 1)
        negotiated = response.get("protocolVersion")
        if negotiated not in ("2025-03-26", PROTOCOL_VERSION):
            raise ConnectorError("Bridge protocol version is unsupported; use a Streamable HTTP adapter")
        self.version = negotiated
        if "tools" not in response.get("capabilities", {}):
            raise ConnectorError("The MCP bridge does not expose fetch tools")
        self.call("notifications/initialized")


def fetch_pdf(source, external_document_id, external_version_id=None):
    url, tool, token = connector_config(source)
    client = MCPClient(url, token)
    client.initialize()
    arguments = {"external_document_id": external_document_id}
    if external_version_id is not None:
        arguments["external_version_id"] = external_version_id
    result = client.call("tools/call", {"name": tool, "arguments": arguments}, 2)
    if result.get("isError"):
        raise ConnectorError("The configured source fetch tool could not return this document")
    payload = result.get("structuredContent")
    if payload is None:
        blocks = result.get("content", [])
        try:
            payload = json.loads(next(b["text"] for b in blocks if b.get("type") == "text"))
        except (StopIteration, ValueError, KeyError, TypeError) as error:
            raise ConnectorError("Bridge must return the documented PDF bytes and version metadata") from error
    if not isinstance(payload, dict):
        raise ConnectorError("Bridge PDF result must be a structured object")
    filename = payload.get("filename")
    fetched_id, fetched_version = payload.get("external_document_id"), payload.get("external_version_id")
    if not isinstance(filename, str) or not filename.lower().endswith(".pdf") or "/" in filename or "\\" in filename:
        raise ConnectorError("Bridge returned an invalid PDF filename")
    if fetched_id != external_document_id or not isinstance(fetched_version, str) or not fetched_version.strip():
        raise ConnectorError("Bridge must return the requested document and its exact source version")
    if external_version_id is not None and fetched_version != external_version_id:
        raise ConnectorError("Bridge returned a different document version than requested")
    encoded = payload.get("pdf_base64")
    if not isinstance(encoded, str) or len(encoded) > MAX_RESPONSE_BYTES:
        raise ConnectorError("Bridge returned invalid or oversized PDF bytes")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ConnectorError("Bridge returned invalid base64 PDF bytes") from error
    if not data.startswith(b"%PDF-") or len(data) > MAX_PDF_BYTES:
        raise ConnectorError("Bridge must return a PDF within the 32 MiB import limit")
    return {"filename": filename, "data": data, "external_document_id": fetched_id,
            "external_version_id": fetched_version}
