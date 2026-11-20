"""One folder for every cog.

Older versions saved welcome + activity in /data/config.json and everything
else in ./data/config.json. Commands succeeded and then never saw the file
they just wrote. DATA_DIR wins, then an existing /data volume, then ./data.
"""

import asyncio
import json
import logging
import os
from copy import deepcopy
from pathlib import Path

log = logging.getLogger("storage")

ROOT = Path(__file__).resolve().parent
lock = asyncio.Lock()


class DataError(Exception):
    pass


def data_dir() -> Path:
    env = os.getenv("DATA_DIR", "").strip()
    if env:
        path = Path(env)
    else:
        volume = Path("/data")
        if volume.is_dir() and os.access(volume, os.W_OK):
            path = volume
        else:
            path = ROOT / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def path(name: str) -> Path:
    return data_dir() / name


def load(name: str, default=None):
    if default is None:
        default = {}
    file = path(name)
    if not file.exists():
        return deepcopy(default)
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DataError(f"{file} is corrupt ({exc}). I did not overwrite it.") from exc
    except OSError as exc:
        raise DataError(f"Couldn't read {file}: {exc}") from exc


def load_obj(name: str) -> dict:
    data = load(name, {})
    if not isinstance(data, dict):
        raise DataError(f"{path(name)} is not a JSON object.")
    return data


def save(name: str, data) -> None:
    file = path(name)
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        tmp = file.with_name(file.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(file)
    except OSError as exc:
        raise DataError(f"Couldn't save {file}: {exc}") from exc


def _overlay(base, newer):
    """Newer file wins conflicts. Keys only the older file has are kept."""
    if not isinstance(base, dict) or not isinstance(newer, dict):
        return newer
    out = dict(base)
    for key, value in newer.items():
        if key in out:
            out[key] = _overlay(out[key], value)
        else:
            out[key] = value
    return out


def _read_json(file: Path):
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("skipped unreadable %s", file)
        return None


def migrate() -> None:
    """Pull configs that used to live in the other folder. Once."""
    try:
        target_dir = data_dir()
    except OSError:
        log.exception("no writable data folder")
        raise

    marker = target_dir / ".migrated-v1"
    if marker.exists():
        return

    names = ("config.json", "panels.json", "stickies.json", "sent.json")
    for name in names:
        target = target_dir / name
        files = []
        if target.exists():
            files.append(target)
        for folder in (ROOT / "data", Path("/data")):
            if not folder.is_dir():
                continue
            try:
                if folder.resolve() == target_dir.resolve():
                    continue
            except OSError:
                continue
            src = folder / name
            if src.exists():
                files.append(src)
        # unique, oldest first so the newest write wins
        seen = set()
        ordered = []
        for file in files:
            try:
                key = str(file.resolve())
            except OSError:
                key = str(file)
            if key in seen:
                continue
            seen.add(key)
            ordered.append(file)
        ordered.sort(key=lambda item: item.stat().st_mtime)

        if target.exists():
            current = _read_json(target)
            if not isinstance(current, dict):
                # Don't replace a broken file with an older copy. Fixing it by hand
                # is safer than silently throwing away whatever was half-written.
                log.error("refusing to overwrite corrupt %s", target)
                continue
        else:
            current = None

        merged = None
        for file in ordered:
            incoming = _read_json(file)
            if not isinstance(incoming, dict):
                continue
            merged = incoming if merged is None else _overlay(merged, incoming)
        if merged is None:
            continue
        if current != merged:
            save(name, merged)
            log.info("merged %s from %s", name, ", ".join(str(item) for item in ordered))

    try:
        marker.write_text("ok\n", encoding="utf-8")
    except OSError:
        log.exception("couldn't write migration marker")
