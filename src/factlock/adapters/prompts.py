"""Prompts and JSON schemas for the three AI steps: draft, target plan, meaning review."""

import json
from collections.abc import Sequence
from typing import Any

from factlock.domain.models import DraftRequest, Fact, FactStatus

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
- Product facts list "trigger_words". Any sentence or heading containing one of those words must carry
  that product fact's id, otherwise the rule engine deletes it.
- Copy numbers and prices exactly as the fact states them. Do not round, convert or add them up.
- Facts with status "claim" are the company's own claims. Only use them with wording such as
  "회사 설명에 따르면".
- When you use a fact that lists "requires", include the sentence for each required condition somewhere in
  the draft, with that condition's id attached.
- Use "heading" blocks for section titles, following the company's blog style: a greeting, the reader's
  problem, what the product bundle does, price, then a closing.
- Cover every guideline emphasis item: for each item, the draft must contain at least one word from each
  of its word groups. The title and the body must each contain every required keyword.
- Start with one sentence saying the post was written from materials the company provided (협찬 표시).
- End with exactly one "footer" block with empty text. The contact lines are added by the server.
- Aim for a complete post a marketer could publish after filling the experience slot: roughly 25 to 40
  sentence blocks.
- Tone: polite 해요체/합니다체, plain words, no exclamation marks, no superlatives.

Write like a good human copywriter, not like a fact sheet
- Do not paste fact statements one per line. Rephrase them in natural Korean, speak to the reader's own
  situation, and combine related facts into one flowing sentence (attach all the ids it relies on).
  Rephrasing is safe as long as numbers, prices and product names stay exactly as the facts give them.
- Open with the reader's problem, then show how the bundle changes their day, then the price and the
  conditions, then a short closing. Each section should read as a paragraph of connected sentences.
- Stay on this target. Use the bundle's products and the facts that matter to this customer. Leave out
  facts that do not help them (company trivia, products for other kinds of customers).
- Keep the title short, at most about 40 Korean characters, and natural. If "title_keywords" is empty,
  do not force other product names into the title."""

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
            **({"trigger_words": list(fact.anchors)} if fact.kind == "product" and fact.anchors else {}),
            **({"scope": fact.scope} if fact.scope else {}),
        }
        for fact in request.facts
        if fact.status in (FactStatus.CONFIRMED, FactStatus.CLAIM)
    ]
    applies = not request.guideline.targets or request.target.id in request.guideline.targets
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
            "title_keywords": list(request.guideline.title_keywords) if applies else [],
            "emphasis": [
                {
                    "no": item.no,
                    "text": item.text,
                    "must_include_one_word_from_each_group": [list(g) for g in item.any_of],
                }
                for item in request.guideline.emphasis
            ]
            if applies
            else [],
        },
        "facts": facts,
    }
    return "Write one blog draft for the target below, using only these facts.\n\n" + json.dumps(
        payload, ensure_ascii=False, indent=1
    )


PLAN_SYSTEM = """You help a small B2B company's marketer decide which of the company's products to present
to one kind of customer. You may only choose from the fact list in the request.

- Pick the product facts (kind "product") that fit this customer, at most four.
- Pick pain facts (kind "pain") this customer would recognise, at most three. If none fit, pick none.
- Pick price facts (kind "price") for the picked products, so an example quote can be calculated.
- Pick condition facts (kind "condition") the customer must be told about.
- Give a short Korean display name for the target and one or two Korean sentences explaining the choice.
  The explanation must not contain numbers or claims that are not in the facts.
- If the company's facts offer nothing for this customer, return empty lists and say so in the reason."""

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "product_ids": {"type": "array", "items": {"type": "string"}},
        "pain_ids": {"type": "array", "items": {"type": "string"}},
        "price_ids": {"type": "array", "items": {"type": "string"}},
        "condition_ids": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["name", "product_ids", "pain_ids", "price_ids", "condition_ids", "reason"],
    "additionalProperties": False,
}

REVIEW_SYSTEM = """You check a Korean marketing text against a company's fact list. A rule engine has already
checked numbers, keywords and required conditions, so do not repeat those. Look for what rules cannot see:

- a sentence whose meaning contradicts a fact (for example it says a feature works on a device the facts
  say is unsupported, or presents an add-on as included);
- a sentence that states something about the company or product as fact when no fact supports it
  (an invented feature, customer, award, guarantee, comparison with competitors);
- a first-person experience claim that reads as invented rather than as a placeholder.

Ignore style, tone, greetings, transitions and opinions that are clearly framed as opinions.
Report at most eight findings, most serious first. For each, quote the sentence exactly as written,
explain the problem in one plain Korean sentence, and give the id of the most relevant fact, or an empty
string when no fact covers the topic. If the text has no such problems, return an empty list."""

REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sentence": {"type": "string"},
                    "problem": {"type": "string"},
                    "fact_id": {"type": "string"},
                },
                "required": ["sentence", "problem", "fact_id"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}


def fact_table(facts: Sequence[Fact]) -> list[dict[str, str]]:
    return [
        {"id": f.id, "kind": f.kind, "statement": f.statement, "status": f.status.value}
        for f in facts
        if f.status in (FactStatus.CONFIRMED, FactStatus.CLAIM)
    ]


def plan_prompt(description: str, facts: Sequence[Fact]) -> str:
    payload = {"customer": description, "facts": fact_table(facts)}
    return "Plan a product bundle for this customer.\n\n" + json.dumps(payload, ensure_ascii=False, indent=1)


def review_prompt(title: str, body: str, facts: Sequence[Fact]) -> str:
    payload = {"facts": fact_table(facts), "text": {"title": title, "body": body}}
    return "Check this text against the facts.\n\n" + json.dumps(payload, ensure_ascii=False, indent=1)


EXTRACT_SYSTEM = """You read a company's internal documents and list the facts a marketer could later use
in advertising copy. A rule engine checks every fact you return against the document text and discards
any fact whose quote is not found there, so quoting exactly is what makes your work usable.

For each fact
- "statement": one plain Korean sentence stating the fact, self-contained (name the product or subject).
  Keep numbers, prices and names exactly as the document gives them.
- "quote": the exact words copied from the document that support it, a short continuous span from one
  page. Do not paraphrase, join separate spans or fix typos in the quote.
- "locator": the locator of the page the quote is on, exactly as given.
- "kind": product (what a product is), feature (what it does), number (a count, rate or track record),
  price (a price or fee), condition (a limit or requirement customers must be told), company.
- "subject_words": one or two words from the statement that name what the fact is about.

Leave out greetings, navigation text, slogans, opinions, instructions to staff, and anything about named
private individuals (names, phone numbers, emails of people). At most 15 facts per request, most useful
for advertising first. Return an empty list if the pages hold nothing usable."""

EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "quote": {"type": "string"},
                    "locator": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": ["product", "feature", "number", "price", "condition", "company"],
                    },
                    "subject_words": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["statement", "quote", "locator", "kind", "subject_words"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}


def extract_prompt(pages: Sequence[tuple[str, str]]) -> str:
    payload = [{"locator": locator, "text": text} for locator, text in pages]
    return "List the usable facts in these pages.\n\n" + json.dumps(payload, ensure_ascii=False, indent=1)
