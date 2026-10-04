"""Start API and worker using the repository .env and server environment."""

import argparse
import os
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from env_file import read_env_file

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_SETTINGS = ("DATABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "MISTRAL_API_KEY")


def runtime_environment(environ, project, file_values=None):
    values = dict(file_values or {})
    values.update(environ)
    values.setdefault("SUPABASE_URL", project["supabase"]["url"])
    values.setdefault("SUPABASE_STORAGE_BUCKET", project["supabase"]["storage_bucket"])
    if values.get("APP_MODE"):
        raise ValueError("Unset the obsolete APP_MODE setting before starting.")
    missing = [name for name in PRIVATE_SETTINGS if not values.get(name, "").strip()]
    if missing:
        raise ValueError("Fill these settings in the root .env file: " + ", ".join(missing))
    for name in PRIVATE_SETTINGS:
        if any(ord(character) < 32 or ord(character) == 127 for character in values[name]):
            raise ValueError("Remove control characters from .env setting: " + name)
    return values


def initialize_env(path, template):
    # Exclusive creation preserves an existing file without reading its keys.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as destination:
        destination.write(template)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init-env", action="store_true", help="Create a blank .env without overwriting an existing file")
    args = parser.parse_args()
    if args.init_env:
        try:
            initialize_env(ROOT / ".env", (ROOT / "config" / "credentials.example").read_text())
        except FileExistsError:
            print("The root .env already exists; it was left unchanged.")
            return 0
        except OSError:
            print("Could not create the root .env file.", file=sys.stderr)
            return 1
        print("Created root .env with blank credentials. Fill it locally before starting.")
        return 0
    python = ROOT / "backend" / ".venv" / "bin" / "python"
    if not python.exists():
        print("Install backend dependencies first: cd backend && uv sync", file=sys.stderr)
        return 1
    project = tomllib.loads((ROOT / "config" / "project.toml").read_text())

    children = []
    try:
        env = runtime_environment(os.environ, project, read_env_file(ROOT / ".env"))
        # Shared validation happens before either process starts; values never print.
        sys.path.insert(0, str(ROOT / "backend"))
        from app.config import settings

        settings(env)
        for args in (
            ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
            ["-m", "app.worker"],
        ):
            children.append(subprocess.Popen([str(python), *args], cwd=ROOT / "backend", env=env))
        print("API and assessment worker started. Press Ctrl+C to stop both.")
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        print("A backend process stopped. Check its service configuration.", file=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, EOFError):
        print("Could not read root .env or start backend processes.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
