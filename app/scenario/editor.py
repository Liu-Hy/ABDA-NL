"""One scenario draft, with optional rule-text edits and linked glossary."""

from copy import deepcopy

from app.scenario.aspic_import import import_aspic
from app.scenario.materials import apply_glossary, parse_glossary

ATOM_SECTIONS = ("facts", "assumptions", "propositions", "conclusions")


def edit_scenario(base: dict, rules: str | None, glossary: str) -> tuple[dict, list[str]]:
    """Keep metadata for surviving identifiers, never overwrite new logic."""
    result = deepcopy(base)
    warnings = []
    if rules is not None:
        result, warnings = import_aspic(base.get("title", ""), rules, "", "")
        atoms = {key: value for section in ATOM_SECTIONS for key, value in base.get(section, {}).items()}
        for section in ATOM_SECTIONS:
            for key, value in result[section].items():
                previous = atoms.get(key, {})
                # Only display metadata transfers across statement kinds.
                for field in ("description", "negated_description", "category", "source"):
                    if field in previous and (field != "source" or section in ("facts", "assumptions")):
                        value[field] = previous[field]
        # Key conclusions are an explicit display choice, not a rule-text side effect.
        for section in ("propositions", "conclusions"):
            for key in list(result[section]):
                target = "conclusions" if key in base.get("conclusions", {}) else "propositions"
                if key not in atoms:
                    target = section  # Infer only newly introduced claims.
                if target != section:
                    result[target][key] = result[section].pop(key)
        mentioned_before = {literal.removeprefix("-") for rule in base.get("rules", {}).values()
                            for literal in [*rule["premises"], rule["conclusion"]]}
        mentioned_after = {key for section in ATOM_SECTIONS for key in result[section]}
        for section in ("propositions", "conclusions"):
            for key, value in base.get(section, {}).items():
                if key not in mentioned_before and key not in mentioned_after:
                    result[section][key] = deepcopy(value)
        for key, value in result["rules"].items():
            for field in ("negated_description", "category", "source"):
                previous = base.get("rules", {}).get(key, {})
                if field in previous:
                    value[field] = previous[field]
        for field in ("description", "corpus", "sources"):
            if field in base:
                result[field] = deepcopy(base[field])
        # The importer has not seen the preserved glossary yet.
        warnings = [message for message in warnings if not message.startswith(("No glossary", "Key conclusions"))]
    result = apply_glossary(result, parse_glossary(glossary))
    missing = [key for section in ATOM_SECTIONS for key, value in result.get(section, {}).items()
               if value.get("description", key) == key]
    if missing:
        warnings.append("Add natural-language meanings for: " + ", ".join(missing[:20]) + ".")
    return result, warnings
