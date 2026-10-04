"""Read literal .env assignments without executing or expanding their contents."""

import re
from pathlib import Path

MAX_BYTES = 64 * 1024
QUOTED = re.compile(r"(['\"])((?:\\.|(?!\1).)*)\1[ \t]*(?:#.*)?")


def read_env_file(path: Path) -> dict[str, str]:
    try:
        with path.open("rb") as source:
            data = source.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return {}
    if len(data) > MAX_BYTES:
        raise ValueError("The .env file exceeds the 64 KiB configuration limit.")
    try:
        lines = data.decode("utf-8-sig").splitlines()
    except UnicodeError:
        raise ValueError("The .env file must use UTF-8 text.") from None
    values = {}
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
        if not match:
            raise ValueError(f"Invalid .env assignment at line {number}.")
        name, raw = match.groups()
        if raw.startswith(("'", '"')):
            quoted = QUOTED.fullmatch(raw)
            if not quoted:
                raise ValueError(f"Invalid .env quoted value at line {number}.")
            quote, value = quoted.groups()
            escapes = {"\\": "\\", quote: quote}
            if quote == '"':
                escapes.update(n="\n", r="\r", t="\t")
            value = re.sub(r"\\(.)", lambda item: escapes.get(item[1], item[0]), value)
        else:
            value = "" if raw.startswith("#") else re.split(r"\s+#", raw, maxsplit=1)[0].rstrip()
        if "\x00" in value:
            raise ValueError(f"Invalid .env value at line {number}.")
        values[name] = value
    return values
