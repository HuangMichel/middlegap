"""Run the isolated API/worker/UI acceptance flow, retaining diagnostic artifacts.

Run with backend/.venv/bin/python scripts/verify_integration.py from any directory.
The in-process transport is explicitly partial verification for socket restrictions.
"""

import argparse
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import ExitStack
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"


def isolated_environment():
    """Do not hand live service credentials or settings to test processes."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("SUPABASE_", "MISTRAL_", "GOOGLE_DRIVE_", "IMANAGE_", "NEXT_PUBLIC_"))
        and key not in ("DATABASE_URL", "APP_MODE", "FRONTEND_ORIGINS", "PYTHONPATH", "PYTHONOPTIMIZE")
    }
    environment["PYTHONUNBUFFERED"] = "1"
    return environment


class Processes:
    def __init__(self, artifacts, environment):
        self.artifacts = artifacts
        self.environment = environment
        self.children = []
        self.files = ExitStack()

    def start(self, name, command, cwd):
        log = self.files.enter_context((self.artifacts / (name + ".log")).open("w"))
        child = subprocess.Popen(
            command,
            cwd=cwd,
            env=self.environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=os.name == "posix",
        )
        self.children.append(child)
        return child

    def run(self, name, command, cwd, timeout=180):
        child = self.start(name, command, cwd)
        try:
            status = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"{name} timed out; see {name}.log") from None
        if status:
            raise RuntimeError(f"{name} exited with status {status}; see {name}.log")

    def close(self):
        # Signal process groups too: npm/Next and worker children must not survive.
        for child in reversed(self.children):
            if os.name == "posix":
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            elif child.poll() is None:
                child.terminate()
        for child in reversed(self.children):
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    os.killpg(child.pid, signal.SIGKILL)
                else:
                    child.kill()
                child.wait(timeout=5)
        if os.name == "posix":
            # npm can exit before its descendants. Reap remaining groups even
            # when the direct child has already returned from wait().
            for child in reversed(self.children):
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.files.close()


def free_port():
    try:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]
    except PermissionError:
        raise RuntimeError(
            "Local server binding is prohibited. Run on an unrestricted runner, "
            "or use --transport in-process for partial API/worker verification."
        ) from None


def wait_ready(url, process, *, harness=False, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Server exited before readiness; see process logs")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if harness and json.load(response).get("test_harness") is not True:
                    raise RuntimeError("Refusing to test a production API endpoint")
                return
        except (OSError, ValueError):
            time.sleep(0.2)
    raise RuntimeError("Server readiness timed out; see process logs")


def load_smoke():
    spec = importlib.util.spec_from_file_location("middlegap_smoke", REPO / "scripts/smoke_api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def socket_free(root, processes):
    # Only this explicit test runner injects fakes. Application startup stays connected-only.
    sys.path.insert(0, str(BACKEND))
    from fastapi.testclient import TestClient
    from tests import integration_server

    integration_server.configure(root)
    integration_server.seed()
    smoke = load_smoke()
    processes.start(
        "worker", [sys.executable, "-m", "tests.integration_server", "worker", "--root", str(root)], BACKEND
    )
    with TestClient(integration_server.main.app) as client:
        def call(method, path, body=None, expected=200, raw=False, content_type="application/json"):
            response = client.request(
                method, path,
                content=body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None,
                headers={"Content-Type": content_type},
            )
            allowed = expected if isinstance(expected, tuple) else (expected,)
            assert response.status_code in allowed, f"{method} {path}: expected {allowed}, got {response.status_code}"
            return response.content if raw else response.json() if response.content else None

        smoke.call = call
        return smoke.main()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("http", "in-process"), default="http")
    parser.add_argument("--artifacts", type=Path, default=REPO / "artifacts/integration")
    args = parser.parse_args()
    # Each invocation has its own evidence directory; old success artifacts cannot mask failures.
    args.artifacts.mkdir(parents=True, exist_ok=True)
    artifacts = Path(tempfile.mkdtemp(prefix="run-", dir=args.artifacts.resolve()))
    environment = isolated_environment()
    processes = Processes(artifacts, environment)
    temporary = tempfile.TemporaryDirectory(prefix="middlegap-integration-")
    record = {"status": "failed", "transport": args.transport, "providers": "synthetic", "browser": "not_run"}
    status = 1
    try:
        if sys.flags.optimize:
            raise RuntimeError("Verification requires Python assertions; do not use -O or PYTHONOPTIMIZE")
        root = Path(temporary.name)
        if args.transport == "in-process":
            record["api"] = socket_free(root, processes)
            record["status"] = "passed_api_only"
        else:
            api_port, ui_port = free_port(), free_port()
            while api_port == ui_port:
                ui_port = free_port()
            api = f"http://127.0.0.1:{api_port}"
            ui = f"http://127.0.0.1:{ui_port}"
            environment.update(
                SMOKE_API_URL=api,
                SMOKE_UI_URL=ui,
                SMOKE_ARTIFACT_DIR=str(artifacts / "browser"),
                NEXT_PUBLIC_API_URL=api,
                FRONTEND_ORIGINS=ui,
            )
            harness = [sys.executable, "-m", "tests.integration_server"]
            processes.run("seed", [*harness, "seed", "--root", str(root)], BACKEND)
            processes.run("frontend-build", ["npm", "run", "build"], FRONTEND, timeout=300)
            api_process = processes.start("api", [*harness, "api", "--root", str(root), "--port", str(api_port)], BACKEND)
            processes.start("worker", [*harness, "worker", "--root", str(root)], BACKEND)
            ui_process = processes.start("frontend", ["npm", "run", "start", "--", "--port", str(ui_port)], FRONTEND)
            wait_ready(api + "/health", api_process, harness=True)
            wait_ready(ui, ui_process)
            processes.run("api-smoke", [sys.executable, str(REPO / "scripts/smoke_api.py")], BACKEND)
            processes.run("browser-smoke", ["node", "scripts/smoke_browser.mjs"], REPO, timeout=240)
            record.update(status="passed", api="passed_over_http", browser="passed")
        status = 0
    except Exception as error:
        # Errors mention commands/checks only; live configuration is never logged.
        record["error"] = str(error)
        print(str(error), file=sys.stderr)
    finally:
        processes.close()
        temporary.cleanup()
        (artifacts / "verification.json").write_text(json.dumps(record, indent=2) + "\n")
        print(f"Integration evidence: {artifacts}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
