"""Standalone connector protocol/immutable-artifact tests, runnable without services."""
import base64
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.connectors import ConnectorError, MCPClient, fetch_pdf


class Response(io.BytesIO):
    def __init__(self, value, headers=None):
        super().__init__(json.dumps(value).encode() if not isinstance(value, bytes) else value)
        self.headers = headers or {"Content-Type": "application/json"}


class ConnectorTests(unittest.TestCase):
    def result(self, **changes):
        payload = dict(filename="Employee Notice.pdf", external_document_id="notice-7", external_version_id="v2",
                       pdf_base64=base64.b64encode(b"%PDF-1.7 exact-original-bytes").decode())
        payload.update(changes)
        return {"structuredContent": payload}

    def fetch(self, result, source="google_drive", version="v2"):
        with patch.dict("os.environ", {"GOOGLE_DRIVE_MCP_URL": "https://bridge.example.test/mcp",
                                       "GOOGLE_DRIVE_MCP_TOOL": "fetch_pdf"}, clear=True), \
             patch.object(MCPClient, "initialize"), patch.object(MCPClient, "call", return_value=result):
            return fetch_pdf(source, "notice-7", version)

    def test_exact_bytes_and_version_preserved(self):
        imported = self.fetch(self.result())
        self.assertEqual(imported["data"], b"%PDF-1.7 exact-original-bytes")
        self.assertEqual(imported["external_version_id"], "v2")

    def test_version_mismatch_rejected(self):
        with self.assertRaises(ConnectorError):
            self.fetch(self.result(external_version_id="v3"))

    def test_wrong_document_and_non_pdf_rejected(self):
        for result in (self.result(external_document_id="wrong"), self.result(pdf_base64="bm90IGEgcGRm"), self.result(filename="../notice.pdf")):
            with self.subTest(result=result), self.assertRaises(ConnectorError):
                self.fetch(result)

    def test_missing_bridge_explicitly_unavailable(self):
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(ConnectorError) as error:
            fetch_pdf("imanage", "notice-7")
        self.assertEqual(error.exception.status_code, 501)

    def test_initialize_session_and_tool_protocol(self):
        calls = []
        responses = [Response({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}}},
                              {"Content-Type": "application/json", "Mcp-Session-Id": "session-7"}), Response(b""),
                     Response({"jsonrpc": "2.0", "id": 2, "result": self.result()})]
        def transport(request, timeout):
            calls.append((json.loads(request.data), dict(request.header_items())))
            return responses.pop(0)
        with patch("app.connectors.urlopen", side_effect=transport):
            client = MCPClient("https://bridge.example.test/mcp")
            client.initialize()
            client.call("tools/call", {"name": "fetch_pdf", "arguments": {"external_document_id": "notice-7"}}, 2)
        self.assertEqual(calls[1][0]["method"], "notifications/initialized")
        self.assertEqual(calls[2][1]["Mcp-session-id"], "session-7")
        self.assertEqual(calls[2][1]["Mcp-protocol-version"], "2025-06-18")

    def test_sse_notifications_and_matching_response(self):
        body = b'data: {"jsonrpc":"2.0","method":"notifications/progress"}\n\ndata: {"jsonrpc":"2.0","id":2,"result":{"ok":true}}\n\n'
        with patch("app.connectors.urlopen", return_value=Response(body, {"Content-Type": "text/event-stream"})):
            self.assertEqual(MCPClient("https://bridge.example.test/mcp").call("tools/call", {}, 2), {"ok": True})


if __name__ == "__main__":
    unittest.main()
