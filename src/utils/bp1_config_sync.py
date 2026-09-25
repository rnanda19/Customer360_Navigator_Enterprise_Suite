"""
src/utils/bp1_config_sync.py — Customer360 Navigator

Order-independent, marker-based read/patch helpers for the shared per-BP config file
(configs/bp1_customer_intent_classification.yaml). Replaces the fragile inline patch logic each
gate notebook previously duplicated (Gate 1 did a blind full-file overwrite; Gates 3/4/5 each did
`text.split(own_marker)[0]`, which silently discards any block appended AFTER their own marker -
safe only if gates are always re-run in strict ascending order and never re-run once a later gate
has already appended its own block). See LESSONS_LEARNED_APPLIED.md #20 for the real incident this
fixes: re-running Gate 1 after Gates 3/4/5 had already appended their blocks wiped all three.

Design: the file has two kinds of content -
  1. "Front matter" - Gate 1's own fields (bp_id, bp_name, status, target_definition,
     leakage_rules, assumptions, random_state). Owned exclusively by Gate 1.
  2. Zero or more "gate blocks" - each begins with its own single-line marker
     (`# --- Gate N (...) results (appended, idempotent overwrite) ---`) and runs until the next
     marker or end of file. One per gate 2-6. Owned exclusively by the gate that wrote it.

`write_front_matter` replaces ONLY the front matter, preserving every existing gate block
verbatim regardless of position or which gates they belong to.
`write_gate_block` replaces (or appends) ONLY the one block whose marker matches, preserving the
front matter and every OTHER gate block verbatim regardless of position.

Neither function ever touches a block it doesn't own. Both are safe to call in any order, any
number of times.
"""

from __future__ import annotations

import re
from pathlib import Path

_MARKER_RE = re.compile(r"^# --- .+ ---$", flags=re.MULTILINE)


def _split_front_matter_and_blocks(text: str) -> tuple[str, dict[str, str], list[str]]:
    """Return (front_matter_text, {marker_line: full_block_text}, [marker_lines_in_order])."""
    positions = [m.start() for m in _MARKER_RE.finditer(text)]
    if not positions:
        return text.rstrip("\n") + "\n", {}, []

    front_matter = text[: positions[0]].rstrip("\n") + "\n"
    blocks: dict[str, str] = {}
    order: list[str] = []
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        segment = text[pos:end].rstrip("\n") + "\n"
        marker_line = segment.split("\n", 1)[0]
        blocks[marker_line] = segment
        order.append(marker_line)
    return front_matter, blocks, order


def _reassemble(front_matter: str, blocks: dict[str, str], order: list[str]) -> str:
    parts = [front_matter.rstrip("\n")]
    for marker in order:
        parts.append(blocks[marker].rstrip("\n"))
    return "\n\n".join(parts) + "\n"


def read_existing_gate_block_markers(config_path: str | Path) -> list[str]:
    """Return the list of gate-block marker lines currently present in the config file (empty
    list if the file doesn't exist yet or has no gate blocks). Used by Gate 1 to derive which
    gateN_confirmed suffixes belong in the status line without guessing."""
    config_path = Path(config_path)
    if not config_path.exists():
        return []
    _, _, order = _split_front_matter_and_blocks(config_path.read_text(encoding="utf-8"))
    return order


def write_front_matter(config_path: str | Path, front_matter_text: str) -> None:
    """Replace ONLY the front-matter section (Gate 1's own fields), preserving every existing
    gate block verbatim, regardless of position or which gate owns it. `front_matter_text` must
    end with a single trailing newline and must not itself contain a `# --- ... ---` marker
    line (that would be misparsed as a gate block boundary on the next read)."""
    config_path = Path(config_path)
    if _MARKER_RE.search(front_matter_text):
        raise ValueError(
            "front_matter_text must not contain a '# --- ... ---' marker line - "
            "that is reserved for gate-block boundaries."
        )
    existing_blocks: dict[str, str] = {}
    existing_order: list[str] = []
    if config_path.exists():
        _, existing_blocks, existing_order = _split_front_matter_and_blocks(
            config_path.read_text(encoding="utf-8")
        )
    config_path.write_text(
        _reassemble(front_matter_text, existing_blocks, existing_order),
        encoding="utf-8",
    )


def write_gate_block(config_path: str | Path, marker: str, block_lines: list[str]) -> None:
    """Replace (if `marker` already exists) or append (if it doesn't) ONE named gate block,
    preserving the front matter and every OTHER gate block verbatim. `marker` must be the
    single-line `# --- ... ---` marker string that begins the block; `block_lines` is the
    block's own body lines (not including the marker line itself)."""
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"{config_path} does not exist - Gate 1 must run first to create the front matter."
        )
    front_matter, blocks, order = _split_front_matter_and_blocks(config_path.read_text(encoding="utf-8"))
    new_segment = marker + "\n" + "\n".join(block_lines) + "\n"
    if marker not in blocks:
        order.append(marker)
    blocks[marker] = new_segment
    config_path.write_text(_reassemble(front_matter, blocks, order), encoding="utf-8")
