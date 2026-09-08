"""Bounded import of the propositional notation shown by the ASPIC- viewer."""

from __future__ import annotations

import re

from app.scenario.materials import MaterialError, apply_glossary, parse_glossary

_ID = r"[A-Za-z_][A-Za-z0-9_]{0,99}"
_LIT = rf"-?{_ID}"
_RULE = re.compile(rf"\s*(.*?)\s*(->|=>)\s*({_LIT})\s*(?:\[({_ID})\])?\s*\Z")


def import_aspic(title: str, text: str, glossary: str, conclusions: str) -> tuple[dict, list[str]]:
    if not 1 <= len(title.strip()) <= 120 or len(text.encode("utf-8")) > 100_000:
        raise MaterialError("Provide a title and at most 100 KB of ASPIC- rules.")
    parsed, embedded = [], []
    block = 1
    # Explicit viewer markers take precedence over visual blank lines. Native
    # ABDA files separate successive defeasible preference blocks with blanks.
    explicit_blocks = bool(re.search(r"^\s*#\s*Block \d+", text, re.MULTILINE))
    defeasible_seen = False
    separator = False
    for index, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            separator = defeasible_seen
            continue
        active = not line.startswith("# [suspended]")
        if not active:
            line = line[len("# [suspended]") :].strip()
        elif line.startswith("#"):
            comment = line[1:].strip()
            if re.match(rf"-?{_ID}\s*=", comment):
                embedded.append(comment)
            elif match := re.match(r"Block (\d+)(?:\s|$)", comment):
                block = int(match[1])
                if not 1 <= block <= 1000:
                    raise MaterialError("Rule blocks must be between 1 and 1000.")
            continue
        match = _RULE.fullmatch(line)
        if not match:
            raise MaterialError(
                f"Check ASPIC- line {index}. Use premises -> conclusion or premises => conclusion [rule_id]."
            )
        left, arrow, right, name = match.groups()
        if arrow == "=>":
            if separator and not explicit_blocks:
                block += 1
            defeasible_seen = True
            separator = False
            if block > 1000:
                raise MaterialError("Rule blocks must be between 1 and 1000.")
        premises = [p.strip() for p in left.split(",")] if left.strip() else []
        if len(premises) > 50 or any(not re.fullmatch(_LIT, p) for p in premises):
            raise MaterialError(
                f"Use comma-separated propositional symbols on ASPIC- line {index}."
            )
        if not active and arrow == "->":
            raise MaterialError("Strict rules cannot be suspended.")
        parsed.append((premises, arrow, right, name, active, block))
        if len(parsed) > 250:
            raise MaterialError("Use at most 250 ASPIC- lines.")
    if not parsed:
        raise MaterialError("Enter at least one ASPIC- fact, assumption, or rule.")
    all_literals = {x.removeprefix("-") for row in parsed for x in [*row[0], row[2]]}
    explicit_names = [r[3] for r in parsed if r[3]]
    if len(explicit_names) != len(set(explicit_names)):
        raise MaterialError("Each named rule or assumption must have a distinct identifier.")
    reserved = all_literals | set(explicit_names)
    result = {
        "title": title.strip(),
        "facts": {},
        "assumptions": {},
        "propositions": {},
        "conclusions": {},
        "rules": {},
    }
    counter = 1
    for premises, arrow, conclusion, name, active, strength in parsed:
        if not premises and not conclusion.startswith("-") and name in {None, conclusion}:
            section = "facts" if arrow == "->" else "assumptions"
            if conclusion in result["facts"] or conclusion in result["assumptions"]:
                raise MaterialError("A fact or assumption is declared more than once.")
            result[section][conclusion] = {"description": conclusion}
            if section == "assumptions":
                result[section][conclusion].update(active=active, block=strength)
            continue
        if not name:
            while f"r{counter}" in reserved:
                counter += 1
            name = f"r{counter}"
            reserved.add(name)
        result["rules"][name] = {
            "type": "strict" if arrow == "->" else "defeasible",
            "premises": premises,
            "conclusion": conclusion,
            "block": strength,
        }
        if arrow == "=>":
            result["rules"][name]["active"] = active
    atom_ids = all_literals - set(result["rules"])
    requested = {c.strip() for c in conclusions.split(",") if c.strip()}
    if requested and (
        not requested <= atom_ids or any(not re.fullmatch(_ID, c) for c in requested)
    ):
        raise MaterialError(
            "Key conclusions must name positive statement symbols used by the rules."
        )
    heads = {r["conclusion"].removeprefix("-") for r in result["rules"].values()} - set(
        result["rules"]
    )
    premises = {p.removeprefix("-") for r in result["rules"].values() for p in r["premises"]}
    focus = requested or (heads - premises) or heads
    for identifier in sorted(atom_ids - set(result["facts"]) - set(result["assumptions"])):
        result["conclusions" if identifier in focus else "propositions"][identifier] = {
            "description": identifier
        }
    if requested & (set(result["facts"]) | set(result["assumptions"])):
        raise MaterialError("Choose a derived claim as a key conclusion, not a fact or assumption.")
    definitions = parse_glossary("\n".join(embedded))
    definitions.update(parse_glossary(glossary))
    result = apply_glossary(result, definitions)
    missing = sorted(atom_ids - definitions.keys())
    warnings = []
    if missing:
        warnings.append(
            "No glossary meaning for: "
            + ", ".join(missing[:20])
            + ". Their symbols are used as labels; edit their meanings in Statements & glossary."
        )
    if not requested:
        warnings.append(
            "Key conclusions were inferred from rule heads. Check the preview before importing."
        )
    return result, warnings
