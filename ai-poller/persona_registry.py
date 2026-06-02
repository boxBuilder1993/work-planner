"""Persona registry: loads markdown+frontmatter persona definitions.

A persona is a `(prompt + tool allowlist + model + small policy bundle)`
accessed via `@ai-<persona>` mention. Defined as a markdown file with YAML
frontmatter in `ai-poller/personas/<name>.md`. Shared prompt fragments live
in `ai-poller/personas/_shared/` and are referenced via the `includes:`
frontmatter key.

Hot-reloaded on each call (no caching). Persona files are small enough that
re-reading them per dispatch is trivial.

See: docs/CHAT_DESIGN.md (Persona system).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Default on-disk location. Tests override by passing `personas_dir=` to
# `load_persona` / `route_mention`.
DEFAULT_PERSONAS_DIR = Path(__file__).parent / "personas"
DEFAULT_PERSONA_NAME = "default"

# Mention regex per design (case-insensitive). Negative lookbehind blocks
# matches inside words like `email@aibnb.com`. Trailing `\b` ensures `@ai`
# is not followed by more word characters (so `@airbnb` does not match).
MENTION_RE = re.compile(r"(?<!\w)@ai(?:-([a-z]+))?\b", re.IGNORECASE)


@dataclass
class CompiledPersona:
    """A loaded persona, ready to use in a dispatch.

    `body` is the final compiled prompt body with includes resolved (shared
    fragments prepended). `raw_body` is the original persona-file body alone,
    kept for debugging / introspection.
    """

    name: str
    description: str = ""
    model: str = "claude-sonnet-4-6"
    tools: list[str] = field(default_factory=list)
    reply_length_cap: int = 4000
    version: int = 1
    # Max agent turns per dispatch. Personas doing heavy code work
    # (engineer) need more than the default 20 to finish multi-step tasks.
    # Forwarded into work_items.prompt_context.max_turns and on to
    # `claude -p --max-turns`.
    max_turns: int = 20
    # Optional normalizer pass: after the persona produces its response, a
    # second model call extracts the canonical {reply_text, artifacts,
    # context_update} JSON from whatever shape the persona emitted. Lets
    # the persona reply naturally without strict JSON-output discipline.
    # Empty `fixer_model` disables; set to a Claude model id to enable.
    # See work_item_handler.FIXER_SYSTEM_PROMPT.
    fixer_model: str = ""
    fixer_max_turns: int = 50
    body: str = ""
    raw_body: str = ""


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_persona_file(path: Path) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter from markdown body.

    Returns `(frontmatter_dict, body)`. If the file has no frontmatter,
    returns `({}, full_content)`. Raises `ValueError` if the frontmatter
    is present but is not a YAML mapping.
    """
    content = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}, content
    fm_str, body = m.groups()
    fm = yaml.safe_load(fm_str) or {}
    if not isinstance(fm, dict):
        raise ValueError(f"frontmatter must be a YAML mapping in {path}")
    return fm, body.lstrip("\n")


def resolve_includes(
    body: str,
    includes: list[str],
    personas_dir: Path,
) -> str:
    """Prepend each include's body to `body`.

    Each entry in `includes` is a path relative to `personas_dir`. Include
    files may themselves have frontmatter — it is stripped before inclusion.
    Fragments are concatenated in order, then a blank line, then the persona
    body.
    """
    if not includes:
        return body
    fragments: list[str] = []
    for inc_path in includes:
        full = personas_dir / inc_path
        if not full.exists():
            raise FileNotFoundError(
                f"persona include not found: {inc_path} (looked for {full})"
            )
        _, inc_body = parse_persona_file(full)
        fragments.append(inc_body.strip())
    return "\n\n".join(fragments) + "\n\n" + body


def load_persona(
    name: str,
    personas_dir: Path = DEFAULT_PERSONAS_DIR,
) -> CompiledPersona:
    """Load and compile a persona by name.

    Looks for `<personas_dir>/<name>.md`. Raises `FileNotFoundError` if the
    file is missing. No caching — re-read on every call (hot reload).
    """
    path = personas_dir / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"persona not found: {name} (looked for {path})"
        )
    fm, body = parse_persona_file(path)
    compiled = resolve_includes(body, fm.get("includes", []), personas_dir)
    return CompiledPersona(
        name=fm.get("name", name),
        description=fm.get("description", ""),
        model=fm.get("model", "claude-sonnet-4-6"),
        tools=list(fm.get("tools", [])),
        reply_length_cap=fm.get("reply_length_cap", 4000),
        version=fm.get("version", 1),
        max_turns=fm.get("max_turns", 20),
        fixer_model=fm.get("fixer_model", "") or "",
        fixer_max_turns=fm.get("fixer_max_turns", 50),
        body=compiled,
        raw_body=body,
    )


def route_mention(
    persona_suffix: str | None,
    personas_dir: Path = DEFAULT_PERSONAS_DIR,
) -> CompiledPersona:
    """Resolve a mention suffix to a persona.

    - `persona_suffix=None` (bare `@ai`) → `DEFAULT_PERSONA_NAME`.
    - `persona_suffix="<name>"` → `<name>.md`, falling back to default if
      the named persona doesn't exist.

    Always returns a `CompiledPersona`; raises `FileNotFoundError` only if
    the default persona itself is missing (deployment error).
    """
    if persona_suffix is None:
        return load_persona(DEFAULT_PERSONA_NAME, personas_dir)
    suffix = persona_suffix.lower()
    try:
        return load_persona(suffix, personas_dir)
    except FileNotFoundError:
        return load_persona(DEFAULT_PERSONA_NAME, personas_dir)
