"""Draft writer backed by the Claude API. Sends only the fact list and the guideline, never user text."""

import json
from typing import Any

import anthropic

from factlock.adapters.stored_writer import draft_from_json
from factlock.domain.models import Draft, DraftRequest, FactStatus
from factlock.ports import DraftWriterError

MODEL = "claude-opus-5-5"

SYSTEM = """You write Korean blog drafts for a B2B company's marketing manager.

The one rule that matters: every factual statement must come from the fact list in the request.
A separate rule engine checks each sentence after you: it compares the numbers, prices and product names
in the sentence with the facts whose ids you attached, and it deletes any sentence that does not match.
So the useful thing you can do is attach the right ids and stay inside the facts.

How to write
- Output blocks. A "sentence" block is one or two Korean sentences with the ids of the facts it relies on.
- A sentence with no fact ids must contain no number, price, product name or superlative. Use those for
  transitions only.
- Do not invent customer stories, statistics, test results or personal experience. Where the guideline
  asks for a hands-on review, add one "experience_slot" block whose text tells the human reviewer what to
  write there. A person fills it in later.
- Facts with status "claim" are the company's own claims. Only use them with wording such as
  "회사 설명에 따르면".
- When you use a fact that lists "requires", include the sentence for each required condition somewhere in
  the draft, with that condition's id attached.
- Use "heading" blocks for section titles, following the company's blog style: a greeting, the reader's
  problem, what the product bundle does, price, then a closing.
- Cover the guideline's emphasis items and required keywords naturally. The title must contain every
  required keyword.
- End with exactly one "footer" block with empty text. The contact lines are added by the server.
- Tone: polite 해요체/합니다체, plain words, no exclamation marks, no superlatives."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["heading", "sentence", "experience_slot", "footer"]},
                    "text": {"type": "string"},
                    "fact_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["type", "text", "fact_ids"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "blocks"],
    "additionalProperties": False,
}


def build_prompt(request: DraftRequest) -> str:
    facts = [
        {
            "id": fact.id,
            "kind": fact.kind,
            "statement": fact.statement,
            "status": fact.status.value,
            **({"requires": list(fact.requires)} if fact.requires else {}),
            **({"scope": fact.scope} if fact.scope else {}),
        }
        for fact in request.facts
        if fact.status is not FactStatus.CONFLICT
    ]
    payload = {
        "target": {
            "name": request.target.name,
            "pain_fact_ids": list(request.target.pains),
            "bundle_fact_ids": list(request.target.bundle),
            "price_fact_ids": list(request.target.quote_items),
            "must_condition_ids": list(request.target.must_conditions),
        },
        "guideline": {
            "required_keywords": list(request.guideline.required_keywords),
            "title_keywords": list(request.guideline.title_keywords),
            "emphasis": [{"no": item.no, "text": item.text} for item in request.guideline.emphasis],
        },
        "facts": facts,
    }
    return "Write one blog draft for the target below, using only these facts.\n\n" + json.dumps(
        payload, ensure_ascii=False, indent=1
    )


class ClaudeDraftWriter:
    def __init__(self, client: anthropic.Anthropic, model: str = MODEL) -> None:
        self._client = client
        self._model = model

    def write(self, request: DraftRequest) -> Draft:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=16000,
                system=SYSTEM,
                messages=[{"role": "user", "content": build_prompt(request)}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            )
        except anthropic.AuthenticationError:
            raise DraftWriterError("claude_auth_failed") from None
        except anthropic.RateLimitError:
            raise DraftWriterError("claude_rate_limited") from None
        except anthropic.APIStatusError:
            raise DraftWriterError("claude_api_error") from None
        except anthropic.APIConnectionError:
            raise DraftWriterError("claude_unreachable") from None
        if response.stop_reason == "refusal":
            raise DraftWriterError("claude_refused")
        if response.stop_reason == "max_tokens":
            raise DraftWriterError("claude_truncated")
        text = next((block.text for block in response.content if block.type == "text"), "")
        try:
            return draft_from_json(json.loads(text), "claude")
        except (ValueError, KeyError, TypeError):
            raise DraftWriterError("claude_bad_output") from None
