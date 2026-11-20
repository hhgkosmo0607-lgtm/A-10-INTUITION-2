"""The guideline in force, and how an uploaded one replaces it."""

from factlock.domain.models import EmphasisItem, Guideline


class GuidelineBook:
    def __init__(self, guideline: Guideline) -> None:
        self.current = guideline

    def adopt(self, uploaded: Guideline) -> Guideline:
        """Use an uploaded guideline, keeping detection terms already known for the same item number."""
        known = {item.no: item for item in self.current.emphasis}
        merged = tuple(
            EmphasisItem(item.no, item.text, known[item.no].any_of, known[item.no].terms_confirmed)
            if item.no in known and not item.any_of
            else item
            for item in uploaded.emphasis
        )
        footer = uploaded.footer or self.current.footer
        self.current = Guideline(
            uploaded.required_keywords, merged, footer, uploaded.title_keywords, self.current.targets
        )
        return self.current
