"""Schema for a single app finding. One row of the research set."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Access = Literal["SS", "SSP", "REV", "SALES", "NONE"]
Buildable = Literal["yes", "yes_with_caveats", "blocked"]


class AppFinding(BaseModel):
    """What the research pass must return for each app.

    Every field that makes a claim is paired with an evidence URL. A field the
    research could not establish must come back as the literal string
    "unknown" rather than a plausible guess - refusing to fill a cell is a
    correct outcome and is scored as such in the audit.
    """

    name: str
    one_liner: str = Field(description="What the product does, one sentence, no marketing.")
    auth_primary: str = Field(
        description="The single auth method a new integration would use, e.g. "
                    "'OAuth2', 'API key', 'Basic', 'Key-pair JWT', or 'unknown'.")
    auth_all: list[str] = Field(description="Every documented auth method.")
    access: Access = Field(
        description="SS = self-serve free credentials. SSP = self-serve but a paid plan is "
                    "required. REV = self-registration then an approval/review gate before "
                    "production. SALES = partnership/enterprise contract/booked call needed. "
                    "NONE = no public API exists.")
    access_note: str = Field(description="One sentence naming the concrete gate and where the key comes from.")
    surface: str = Field(description="e.g. 'REST', 'GraphQL', 'REST + GraphQL', 'CLI / OSS', 'unknown'.")
    mcp: str = Field(description="'official', 'via Composio', 'third party', or 'none found'.")
    buildable: Buildable
    blocker: str = Field(description="The single thing stopping a toolkit today, or 'None material.'")
    evidence: list[str] = Field(
        description="1-3 URLs that directly support the claims above. Vendor documentation "
                    "is strongly preferred over blogs or aggregators.")
    confidence: Literal["high", "medium", "low"]
    conflicts: list[str] = Field(
        default_factory=list,
        description="Any place where two sources disagreed. Record the disagreement rather "
                    "than silently choosing a side.")
