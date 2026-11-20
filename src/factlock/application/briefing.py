"""Builds what a writer is allowed to see, and removes price content when prices are left out."""

from collections.abc import Sequence
from dataclasses import replace

from factlock.application.catalog import FactCatalog
from factlock.application.guidelines import GuidelineBook
from factlock.domain.models import Block, Carousel, Draft, DraftRequest, Fact, Target


class WriterBrief:
    def __init__(self, catalog: FactCatalog, guidelines: GuidelineBook) -> None:
        self._catalog = catalog
        self._guidelines = guidelines

    def price_only_ids(self, target: Target) -> set[str]:
        """Price facts, plus conditions nothing but prices needs."""
        facts = self._catalog.all()
        prices = [fact for fact in facts if fact.kind == "price"]
        other_needs = {cid for fact in facts if fact.kind != "price" for cid in fact.requires}
        needed_elsewhere = other_needs | set(target.must_conditions)
        return {fact.id for fact in prices} | ({cid for fact in prices for cid in fact.requires} - needed_elsewhere)

    def request(
        self, target: Target, include_price: bool, must: Sequence[Fact], emphasized: Sequence[Fact] = ()
    ) -> DraftRequest:
        must_ids = tuple(fact.id for fact in must)
        lead_ids = tuple(fact.id for fact in emphasized)
        picked = {*target.pains, *target.must_conditions, *must_ids, *lead_ids}
        # Only checked items reach the writer: other customer problems, and anything the marketer typed
        # but did not tick this time, stay out of sight.
        facts = tuple(
            fact
            for fact in self._catalog.writable()
            if fact.id in picked or not (fact.kind == "pain" or fact.id.startswith("USER-"))
        )
        guideline = self._guidelines.current
        if include_price:
            return DraftRequest(target, guideline, facts, True, must_ids, lead_ids)
        hidden = self.price_only_ids(target) - set(must_ids) - set(lead_ids)
        visible = tuple(fact for fact in facts if fact.id not in hidden)
        return DraftRequest(replace(target, quote_items=()), guideline, visible, False, must_ids, lead_ids)

    def draft_without_prices(self, draft: Draft, target: Target) -> Draft:
        hidden = self.price_only_ids(target)
        kept = [block for block in draft.blocks if not set(block.fact_ids) & hidden]
        blocks: list[Block] = []
        for index, block in enumerate(kept):
            following = kept[index + 1].type if index + 1 < len(kept) else "end"
            emptied_price_heading = (
                block.type == "heading" and following in ("heading", "footer", "end") and "비용" in block.text
            )
            if not emptied_price_heading:
                blocks.append(block)
        return Draft(draft.title, tuple(blocks), draft.source)

    def carousel_without_prices(self, carousel: Carousel, target: Target) -> Carousel:
        hidden = self.price_only_ids(target)
        slides = [slide for slide in carousel.slides if not set(slide.fact_ids) & hidden]
        if carousel.offer_without_price is not None and len(slides) < len(carousel.slides):
            slides.append(carousel.offer_without_price)
        caption = tuple(block for block in carousel.caption if not set(block.fact_ids) & hidden)
        return Carousel(tuple(slides), caption, carousel.hashtags, carousel.source)
