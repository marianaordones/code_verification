from typing import Protocol


class FeedbackProvider(Protocol):
    def extract(self, verification: dict) -> str: ...


class ConventionalFeedbackProvider:
    """No solver API, traces, models, statistics or counterexamples."""

    def extract(self, verification):
        return verification["stdout"] + "\n" + verification["stderr"]

# Future RawSMTFeedbackProvider / StructuredSMTFeedbackProvider implement this
# same interface. They are deliberately not implemented in this baseline.
