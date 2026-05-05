"""Generate THIRD_PARTY_LICENSES.md from pip-licenses and license-checker JSON output."""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent

PERMISSIVE = {"MIT", "ISC", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0",
              "BlueOak-1.0.0", "MIT-0", "CC-BY-4.0", "CC0-1.0", "Python-2.0",
              "PSF-2.0", "Unlicense", "0BSD"}

NOTES = {
    "MPL-2.0": "Modifications to this library's own source files must remain MPL-2.0.",
    "EPL-2.0": "Dual-licensed EPL-2.0 / BSD-3-Clause; used under BSD-3-Clause.",
    "LGPL-3.0": "Used as an unmodified shared library (simulator tool only).",
    "GPL-3.0": "Simulator development tool only — not part of the distributed application.",
}


def classify(license_str: str) -> str:
    s = license_str.upper().replace(" ", "-")
    for key in NOTES:
        if key.upper().replace("-", "") in s.replace("-", ""):
            return key
    for p in PERMISSIVE:
        if p.upper().replace("-", "") in s.replace("-", ""):
            return "permissive"
    return "other"


def load_backend() -> list[dict]:
    path = ROOT / "licenses-backend.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    rows = []
    for p in raw:
        name = p.get("Name", "")
        if name in ("ir2mqtt", "ir2mqtt-frontend"):
            continue
        rows.append({
            "name": name,
            "version": p.get("Version", ""),
            "license": p.get("License", ""),
            "url": p.get("URL", ""),
        })
    return sorted(rows, key=lambda x: x["name"].lower())


def load_frontend() -> list[dict]:
    path = ROOT / "licenses-frontend.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    rows = []
    for pkg, info in raw.items():
        name, _, version = pkg.rpartition("@")
        if not name:
            name, version = pkg, ""
        if name in ("ir2mqtt-frontend",):
            continue
        rows.append({
            "name": name,
            "version": version,
            "license": info.get("licenses", ""),
            "url": info.get("repository", info.get("url", "")),
        })
    return sorted(rows, key=lambda x: x["name"].lower())


def table(rows: list[dict]) -> str:
    lines = ["| Package | Version | License |", "|---|---|---|"]
    for r in rows:
        url = r["url"]
        name = f"[{r['name']}]({url})" if url else r["name"]
        lines.append(f"| {name} | {r['version']} | {r['license']} |")
    return "\n".join(lines)


def notes_section(rows: list[dict]) -> str:
    seen: dict[str, list[str]] = {}
    for r in rows:
        key = classify(r["license"])
        if key in NOTES:
            seen.setdefault(key, []).append(r["name"])
    if not seen:
        return ""
    lines = ["\n## License Notes\n"]
    for key, pkgs in seen.items():
        lines.append(f"**{key}** — {NOTES[key]}")
        lines.append(f"Affected packages: {', '.join(f'`{p}`' for p in pkgs)}\n")
    return "\n".join(lines)


def main():
    backend = load_backend()
    frontend = load_frontend()
    all_rows = backend + frontend

    out = [
        "# Third-Party Licenses\n",
        "This project uses the following open-source packages.\n",
        "## Python Dependencies\n",
        table(backend),
        "\n## Frontend Dependencies\n",
        table(frontend),
        notes_section(all_rows),
        "\n---\n",
        "_Generated automatically by `make licenses`._\n",
    ]

    (ROOT / "THIRD_PARTY_LICENSES.md").write_text("\n".join(out))


if __name__ == "__main__":
    main()
