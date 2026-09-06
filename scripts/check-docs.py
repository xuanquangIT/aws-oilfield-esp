"""Check repository Markdown file links and unresolved citation markers offline."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
files = list(ROOT.glob("*.md"))
for directory in ("docs", "evidence", "data"):
    files.extend((ROOT / directory).rglob("*.md"))
errors = []
links = 0
for path in files:
    content = path.read_text(encoding="utf-8")
    if "\ue200" in content or "&#x20;" in content:
        errors.append(f"{path.relative_to(ROOT)}: unresolved source/HTML marker")
    for destination in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
        destination = destination.strip("<>").split("#", 1)[0]
        if not destination or re.match(r"[a-zA-Z]+:", destination):
            continue
        links += 1
        if not (path.parent / destination).exists():
            errors.append(f"{path.relative_to(ROOT)}: missing {destination}")
if errors:
    raise SystemExit("\n".join(errors))
print(f"Documentation checks passed: {len(files)} files, {links} local links.")
