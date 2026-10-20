
import re


def check_posting_rules(
    content: str,
    allow_self_promotion: bool = True,
    allow_links: bool = True,
    require_ai_disclosure: bool = False,
    is_self_promotional: bool = False,
    is_ai_generated: bool = False,
):
    reasons = []

    # Rule 1: Self-promotion
    if is_self_promotional and not allow_self_promotion:
        reasons.append("SELF_PROMOTION_NOT_ALLOWED")

    # Rule 2: Links
    has_link = bool(
        re.search(r"https?://\S+|www\.\S+", content, re.IGNORECASE)
    )
    if has_link and not allow_links:
        reasons.append("LINKS_NOT_ALLOWED")

    # Rule 3: AI disclosure
    has_ai_disclosure = bool(
        re.search(
            r"\bAI[- ]generated\b|\bwritten with AI\b",
            content,
            re.IGNORECASE,
        )
    )

    if is_ai_generated and require_ai_disclosure and not has_ai_disclosure:
        reasons.append("AI_DISCLOSURE_REQUIRED")

    return {
        "allowed": len(reasons) == 0,
        "reasons": reasons,
    }
