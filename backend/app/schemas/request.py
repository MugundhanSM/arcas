from enum import Enum

from pydantic import BaseModel, Field


class ReviewIntent(str, Enum):
    """User intent that drives conditional orchestration."""

    AUTO = "auto"
    FULL_REVIEW = "full_review"
    SECURITY_AUDIT = "security_audit"
    REFACTOR = "refactor"
    DOCUMENTATION = "documentation"
    TEST_GENERATION = "test_generation"
    METRICS = "metrics"


class ReviewRequest(BaseModel):
    code: str = Field(
        ...,
        min_length=1,
        description="The source code to review.",
    )
    language: str = Field(
        default="python",
        description="Programming language of the submitted code.",
    )
    intent: ReviewIntent = Field(
        default=ReviewIntent.FULL_REVIEW,
        description=(
            "Desired analysis. Drives conditional routing in the "
            "orchestration layer; 'full_review' runs every agent. Use "
            "'auto' to let the intent classifier infer it from "
            "'request_text' and the code."
        ),
    )
    request_text: str | None = Field(
        default=None,
        description=(
            "Optional free-text instruction (e.g. 'find the security bugs'). "
            "Used by the heuristic intent classifier when intent='auto'."
        ),
    )
    session_id: str | None = Field(
        default=None,
        description=(
            "Optional client session id to correlate multi-turn requests "
            "in session memory."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "language": "python",
                "intent": "full_review",
                "code": (
                    "import subprocess\n"
                    "user_input = input()\n"
                    "subprocess.call(user_input, shell=True)\n"
                ),
            }
        }
    }
