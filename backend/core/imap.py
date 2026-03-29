from __future__ import annotations

import enum
import logging
import re
from dataclasses import dataclass

log = logging.getLogger("incognito.imap")

_REF_PATTERN = re.compile(r"\[REF-([A-Z0-9]{8})\]")


class MatchTier(enum.StrEnum):
    MESSAGE_ID = "message_id"
    REFERENCE_CODE = "reference_code"
    DOMAIN_ONLY = "domain_only"


@dataclass(frozen=True)
class MatchResult:
    request_id: str
    tier: MatchTier


def _extract_domain(email_address: str) -> str:
    """Extract domain from an email address."""
    return email_address.rsplit("@", 1)[-1].lower()


def match_reply(
    in_reply_to: str,
    references: str,
    subject: str,
    from_address: str,
    outbound_message_ids: dict[str, str],
    broker_domains: set[str],
    ref_code_map: dict[str, str] | None = None,
    domain_request_map: dict[str, str] | None = None,
) -> MatchResult | None:
    # Tier 1: Message-ID threading
    if in_reply_to and in_reply_to.strip() in outbound_message_ids:
        return MatchResult(
            request_id=outbound_message_ids[in_reply_to.strip()],
            tier=MatchTier.MESSAGE_ID,
        )

    if references:
        for ref_id in references.split():
            ref_id = ref_id.strip()
            if ref_id in outbound_message_ids:
                return MatchResult(
                    request_id=outbound_message_ids[ref_id],
                    tier=MatchTier.MESSAGE_ID,
                )

    # Tier 2: Subject reference code + domain validation
    if ref_code_map:
        match = _REF_PATTERN.search(subject)
        if match:
            code = match.group(1)
            if code in ref_code_map:
                sender_domain = _extract_domain(from_address)
                if sender_domain in broker_domains:
                    return MatchResult(
                        request_id=ref_code_map[code],
                        tier=MatchTier.REFERENCE_CODE,
                    )

    # Tier 3: Sender domain match (low confidence)
    if domain_request_map:
        sender_domain = _extract_domain(from_address)
        if sender_domain in domain_request_map:
            return MatchResult(
                request_id=domain_request_map[sender_domain],
                tier=MatchTier.DOMAIN_ONLY,
            )

    return None
