"""Exercise the API + separate worker with an isolated test harness.

Run from backend with `.venv/bin/python ../scripts/smoke_api.py` while API/worker run.
Only uses public API; refuses to mutate a normal application endpoint.
"""
import io
import json
import os
import time
import urllib.error
import urllib.request
import pymupdf
from reportlab.pdfgen import canvas

BASE = os.environ.get("SMOKE_API_URL", "http://127.0.0.1:8000")


def call(method, path, body=None, expected=200, raw=False, content_type="application/json"):
    data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            status, payload = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, payload = error.code, error.read()
    allowed = expected if isinstance(expected, tuple) else (expected,)
    assert status in allowed, f"{method} {path}: {status}, expected {allowed}: {payload[:400]!r}"
    return payload if raw else json.loads(payload) if payload else None


def upload(workspace_id, filename, lines):
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    for index, line in enumerate(lines):
        pdf.drawString(50, 760 - index * 24, line)
    pdf.save()
    boundary = "middlegap-smoke-boundary"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            "Content-Type: application/pdf\r\n\r\n").encode() + output.getvalue() + f"\r\n--{boundary}--\r\n".encode()
    return call("POST", f"/workspaces/{workspace_id}/documents", body, (200, 201),
                content_type=f"multipart/form-data; boundary={boundary}")


def main():
    health = call("GET", "/health")
    assert health.get("test_harness") is True, "Integration checks require the isolated test harness"
    workspace = call("POST", "/workspaces", {"name": f"Integration check {int(time.time())}"}, (200, 201))
    wid = workspace["id"]
    complete = ["Privacy Notice", "Legal basis: consent.", "Purpose of processing: customer services.",
                "Retention period: records are retained for seven years.", "Controller contact: privacy@example.test."]
    customer = upload(wid, "Customer Privacy Notice.pdf", complete)
    employee = upload(wid, "Employee Privacy Notice.pdf", [complete[0], complete[1], complete[2], complete[4]])
    templates = call("GET", "/checklist-templates")
    template = next(t for t in templates if t["id"] == "sample-privacy")
    checklist = call("POST", f"/workspaces/{wid}/checklists", {"template_id": template["id"]}, (200, 201))
    run = call("POST", f"/checklists/{checklist['id']}/assessment-runs", {}, (200, 201, 202))
    rid = run["id"]
    # Freeze at request time: a subsequent upload/removal must not change this run.
    upload(wid, "Later Privacy Notice.pdf", complete)
    call("DELETE", f"/workspaces/{wid}/documents/{employee['id']}", expected=(200, 204))
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        run = call("GET", f"/assessment-runs/{rid}")
        if run["status"] in ("completed", "completed_with_errors", "failed"):
            break
        time.sleep(0.25)
    assert run["status"] == "completed", f"Worker did not complete: {run['status']}"
    assert run["processed_criteria"] == template["criterion_count"]
    assert {d["document_id"] for d in run["snapshot_documents"]} == {customer["id"], employee["id"]}
    assert call("GET", f"/documents/{employee['id']}/file", raw=True).startswith(b"%PDF")
    results = call("GET", f"/assessment-runs/{rid}/results")
    assert len(results) == template["criterion_count"]
    retention = next(r for r in results if "Retention" in r["criterion_text"])
    assert retention["ai_state"] == "gap", "Expected missing Employee retention clause"
    assert {r["document_id"]: r["ai_state"] for r in retention["document_results"]} == {
        customer["id"]: "fulfilled", employee["id"]: "gap"
    }
    cited = next(r for r in results if r["evidence"])
    call("PUT", f"/criterion-results/{cited['id']}/review",
         {"final_value": "Yes", "decision_type": "verified_ai"}, expected=(400, 409, 422))
    first_report = call("POST", f"/assessment-runs/{rid}/reports", {}, (200, 201))
    call("POST", f"/reports/{first_report['id']}/export", {"draft": False, "confirm_incomplete": False}, expected=(400, 409, 422))
    call("POST", f"/reports/{first_report['id']}/export", {"draft": True, "confirm_incomplete": False}, expected=(400, 409, 422))
    draft = call("POST", f"/reports/{first_report['id']}/export", {"draft": True, "confirm_incomplete": True}, raw=True)
    assert draft.startswith(b"%PDF")
    with pymupdf.open(stream=draft, filetype="pdf") as pdf:
        assert "DRAFT" in "".join(page.get_text() for page in pdf)
    for result in results:
        for evidence in result["evidence"]:
            call("PATCH", f"/evidence/{evidence['id']}/review", {"review_status": "accepted"})
            assert evidence["anchors"], "Citation has no source anchors"
            for anchor in evidence["anchors"]:
                assert 0 <= anchor["x0"] <= anchor["x1"] <= 1
                assert 0 <= anchor["y0"] <= anchor["y1"] <= 1
        value = "No" if result["ai_state"] == "gap" else "Yes"
        call("PUT", f"/criterion-results/{result['id']}/review", {"final_value": value, "decision_type": "verified_ai"})
    reviewed = call("GET", f"/assessment-runs/{rid}")
    assert reviewed["reviewed_criteria"] == template["criterion_count"]
    assert reviewed["score"]["provisional"] is False
    assert reviewed["score"]["total_score"] == 7.5
    assert reviewed["score"]["max_score"] == 10
    report = call("POST", f"/assessment-runs/{rid}/reports", {}, (200, 201))
    gaps = {r["gap_id"] for r in call("GET", f"/assessment-runs/{rid}/results") if r["review"]["final_value"] == "No"}
    assert {gid for item in report["items"] for gid in item["gap_ids"]} == gaps
    final = call("POST", f"/reports/{report['id']}/export", {"draft": False, "confirm_incomplete": False}, raw=True)
    assert final.startswith(b"%PDF")
    with pymupdf.open(stream=final, filetype="pdf") as pdf:
        text = "".join(page.get_text() for page in pdf)
        assert "DRAFT" not in text
        assert all(gap in text for gap in gaps)
    # Changing an inspected citation invalidates final review and stale exports.
    evidence = cited["evidence"][0]
    call("PATCH", f"/evidence/{evidence['id']}/review", {"review_status": "rejected"})
    after = call("GET", f"/assessment-runs/{rid}/results")
    changed = next(r for r in after if r["id"] == cited["id"])
    assert changed["review"] is None and changed["ai_state"] == cited["ai_state"]
    assert call("GET", f"/assessment-runs/{rid}")["score"]["provisional"] is True
    call("POST", f"/reports/{report['id']}/export", {"draft": False, "confirm_incomplete": False}, expected=(400, 409, 422))
    summary = {"status": "passed", "workspace_id": wid, "run_id": rid, "criteria": len(results),
                      "confirmed_gaps": len(gaps), "checks": ["separate worker", "frozen snapshot", "retained original PDF",
                      "citation gate", "draft confirmation", "normalized anchors", "deterministic score", "exact gap coverage",
                      "final PDF", "review invalidation", "immutable AI", "stale export rejection"]}
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
