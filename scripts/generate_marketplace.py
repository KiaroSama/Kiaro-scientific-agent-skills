"""Regenerate the Claude Code and Codex plugin marketplaces from skills/.

This repository ships only skills (skills/<name>/SKILL.md): no agents,
commands, hooks or MCP configs. Every skill directory becomes its own plugin,
rooted at the skill directory itself, so no files are copied. Re-run after
syncing upstream:

    python scripts/generate_marketplace.py

Writes, per plugin, skills/<name>/.claude-plugin/plugin.json and
skills/<name>/.codex-plugin/plugin.json; at the repo root,
.claude-plugin/marketplace.json (Claude Code) and
.agents/plugins/marketplace.json (Codex). The root plugin.json is upstream's
Agent Plugins manifest and is left untouched.

Generated manifests carry no "version": a pinned version would keep installed
plugins on their cached copy forever, while no version makes Claude Code use
the commit SHA, so every upstream sync reaches users.
"""
import json
import os
import re
import shutil
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")
MARKETPLACE = "Kiaro-scientific-agent-skills"
OWNER = "KiaroSama"
REPO = f"https://github.com/{OWNER}/{MARKETPLACE}"
CODEX_CATEGORY = "Education & Research"
MANIFEST_DIRS = (".claude-plugin", ".codex-plugin")


def clip(s, n=300):
    s = " ".join(str(s).split()).strip()
    return s[: n - 3] + "..." if len(s) > n else s


def frontmatter(path):
    """Top-level scalar fields of a SKILL.md frontmatter, stdlib only.

    Handles plain, quoted and block (> |) scalars with indented continuation
    lines, which covers every SKILL.md in this repo.
    """
    with open(path, encoding="utf-8") as f:
        m = re.match(r"---\s*\n(.*?)\n---", f.read(), re.S)
    if not m:
        return {}
    out, key = {}, None
    for line in m.group(1).splitlines():
        top = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if top:
            key = top.group(1)
            out[key] = top.group(2)
        elif key and (line.startswith((" ", "\t")) or not line.strip()):
            out[key] += " " + line.strip()
    for k, v in out.items():
        v = re.sub(r"^[>|][+-]?\s", "", v.strip() + " ").strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1].replace('\\"', '"').replace("''", "'")
        out[k] = v
    return out


def spdx(value):
    """The frontmatter license when it is a bare identifier, else None."""
    v = re.sub(r"\s+license$", "", value or "", flags=re.I).strip()
    return v if v and v != "Unknown" and not re.search(r"[\s:/]", v) else None


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---- clean manifests left behind by skills upstream removed --------------
for d in sorted(os.listdir(SKILLS)):
    base = os.path.join(SKILLS, d)
    if os.path.isdir(base) and not os.path.isfile(os.path.join(base, "SKILL.md")):
        for m in MANIFEST_DIRS:
            shutil.rmtree(os.path.join(base, m), ignore_errors=True)
        if not os.listdir(base):
            os.rmdir(base)

# ---- one plugin per skill -------------------------------------------------
entries, seen = [], set()
for d in sorted(os.listdir(SKILLS)):
    base = os.path.join(SKILLS, d)
    skill_md = os.path.join(base, "SKILL.md")
    if not os.path.isfile(skill_md):
        continue
    fm = frontmatter(skill_md)
    slug = re.sub(r"[^a-z0-9-]+", "-", d.lower()).strip("-")
    # Two skills that slug to the same name must not share a plugin name.
    name, n = slug, 2
    while name in seen:
        name, n = f"{slug}-{n}", n + 1
    seen.add(name)
    desc = clip(fm.get("description", "")) or f"Scientific skill: {d}"

    manifest = {
        "name": name,
        "description": desc,
        "author": {"name": OWNER},
        "homepage": REPO,
        "repository": REPO,
    }
    lic = spdx(fm.get("license"))
    if lic:
        manifest["license"] = lic
    write_json(os.path.join(base, ".claude-plugin", "plugin.json"), manifest)

    codex = dict(manifest)
    codex["skills"] = "./"
    codex["interface"] = {
        "displayName": fm.get("name") or d,
        "shortDescription": desc[:120],
        "developerName": OWNER,
        "category": CODEX_CATEGORY,
        "websiteURL": REPO,
    }
    write_json(os.path.join(base, ".codex-plugin", "plugin.json"), codex)

    entries.append({"name": name, "source": f"./skills/{d}",
                    "description": desc, "category": "skill"})

assert len({e["source"] for e in entries}) == len(entries), "duplicate plugin source"

write_json(os.path.join(ROOT, ".claude-plugin", "marketplace.json"), {
    "name": MARKETPLACE,
    "owner": {"name": OWNER},
    "description": "Scientific and research Agent Skills, one plugin per skill.",
    "plugins": entries,
})

# Codex reads this one instead: a source object and a policy block per entry.
write_json(os.path.join(ROOT, ".agents", "plugins", "marketplace.json"), {
    "name": MARKETPLACE,
    "interface": {"displayName": "Kiaro Scientific Agent Skills"},
    "plugins": [
        {
            "name": e["name"],
            "source": {"source": "local", "path": e["source"]},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": CODEX_CATEGORY,
        }
        for e in entries
    ],
})

print(dict(Counter(e["category"] for e in entries)), "TOTAL:", len(entries))
