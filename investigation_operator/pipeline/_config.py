"""Settings the extraction passes have to agree on. Each pass keeps its own
prompt, but the vocabulary and the row shape live here so the outputs stay
comparable.
"""

import json
import os
from pathlib import Path

INVESTIGATION = Path(__file__).resolve().parent.parent   # investigation_operator/
REPO = INVESTIGATION.parent                              # repository root

MODEL = "claude-sonnet-5"
MAX_TOKENS = 32000
EFFORT = "high"


def load_env() -> None:
    """Load KEY=VALUE lines from .env, without overriding a real env var."""
    env_file = REPO / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def require_api_key() -> bool:
    load_env()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    print("error: ANTHROPIC_API_KEY not set. Put it in .env as:\n"
          "  ANTHROPIC_API_KEY=sk-ant-...")
    return False


def parse_json_response(response) -> dict:
    """Parse a structured response, failing loudly if it was cut short.

    Without this a truncated or refused response surfaces as a bare
    JSONDecodeError, after the call has already been paid for.
    """
    if response.stop_reason not in (None, "end_turn", "stop_sequence"):
        raise SystemExit(
            f"error: the model stopped early (stop_reason="
            f"{response.stop_reason!r}), so the response is incomplete.\n"
            f"       If that is max_tokens, raise MAX_TOKENS in _config.py "
            f"(currently {MAX_TOKENS:,}).")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise SystemExit("error: the response carried no text block.")
    return json.loads(text)


# Given to the frames pass and the reconcile pass, withheld from the narrated
# pass. How a technician describes their own work is evidence worth keeping.

VOCABULARY = """\
CANONICAL VOCABULARY

Use these exact nouns for the objects involved, even where another word would
read more naturally. Consistent naming is what makes different operators
comparable to each other.

  apple        the whole fruit
  section      a large piece cut from the whole apple alongside the core
               (not: cheek, lobe, chunk, side)
  core piece   the central remainder holding the core, seeds and stem
               (not: apple body, core-bearing piece, middle)
  slice        a piece cut from a section, kept as product
               (not: wedge, wedge slice)
  scrap        material set aside as not usable product
               (not: sliver, trim, offcut, skin scrap)
  core, seeds, stem, skin   parts of the apple itself
  board, knife              equipment

Use "cuts" as the verb rather than "slices", so that "slice" always refers to
the object: "The operator cuts a slice from the section."\
"""


# Every pass emits the same row shape, so the field names live here rather than
# being restated three times. The action wording is a parameter because that is
# the one thing the passes differ on.


def steps_schema(action_description: str,
                 extra_properties: dict | None = None) -> dict:
    """JSON schema for a list of action rows, for output_config.format."""
    properties = {
        "step": {"type": "string",
                 "description": "Major phase of the process."},
        "task": {"type": "string",
                 "description": "Purposeful unit of work within the step."},
        "action": {"type": "string", "description": action_description},
        "start_sec": {"type": "number"},
        "end_sec": {"type": "number"},
        "condition": {
            "type": ["string", "null"],
            "description": "What the operator was responding to, or null if this "
                           "is a routine action.",
        },
        "condition_response": {
            "anyOf": [
                {"type": "string", "enum": ["adjusted", "dismissed"]},
                {"type": "null"},
            ],
            "description": "Whether the condition changed the behavior.",
        },
    }
    properties.update(extra_properties or {})

    return {
        "type": "object",
        "properties": {
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": properties,
                    # Every field is required, so the model cannot skip one.
                    # Null is expressed by type instead.
                    "required": list(properties),
                    "additionalProperties": False,
                },
            }
        },
        "required": ["actions"],
        "additionalProperties": False,
    }
