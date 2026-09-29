from .jev import JevError, REASONS
from .models import Decision, Outcome
from .rules import inspect


def triage(record, row=1, seen=None, provider=None, threshold=0.85):
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between zero and one")
    check = inspect(record, seen)
    reasons = [f"{f.code}: {f.reason}" for f in check.findings]
    decision = Decision.REPAIR if check.changes else Decision.ACCEPT
    source, confidence, verdict = "deterministic", 1.0, None
    if check.has("hard"):
        decision = Decision.QUARANTINE
    elif check.has("soft"):
        if provider is None:
            decision, confidence, source = Decision.QUARANTINE, None, "offline_fallback"
            reasons.append("AI_DISABLED: Ambiguous records require review in offline mode.")
        else:
            try:
                verdict = provider.decide(check)
                decision, confidence, source = verdict.decision, verdict.confidence, "jev"
                reasons.append(f"{verdict.reason_code}: {REASONS[verdict.reason_code]}")
                if min(confidence, verdict.reason_confidence) < threshold:
                    decision = Decision.QUARANTINE
                    reasons.append("LOW_CONFIDENCE: Model decision or reason is below threshold.")
                elif verdict.reason_code in {"CONTRADICTION", "INSUFFICIENT_EVIDENCE"}:
                    decision = Decision.QUARANTINE
                    reasons.append("REASON_GATE: Adverse reason requires human review.")
                elif decision == Decision.REPAIR and not check.changes:
                    decision = Decision.QUARANTINE
                    reasons.append("NO_SAFE_REPAIR: No deterministic transformation is available.")
                elif decision == Decision.ACCEPT and check.changes:
                    decision = Decision.REPAIR
                    reasons.append("NORMALIZED: Approved canonicalization was applied.")
            except JevError as error:
                decision, confidence, source = Decision.QUARANTINE, None, "provider_fallback"
                reasons.append(str(error))
    if not reasons:
        reasons.append("RULES_PASSED: Record satisfies the customer-v1 contract.")
    if check.changes:
        reasons.append("NORMALIZATION_PROPOSED: " + ", ".join(sorted(check.changes)))
    # Recheck the actual candidate immediately before it can be written as validated.
    if decision != Decision.QUARANTINE and inspect(check.candidate).has("hard"):
        decision = Decision.QUARANTINE
        reasons.append("REVALIDATION_FAILED: Candidate violates the hard contract.")
    return Outcome(row, decision, source, confidence, reasons, check.original,
                   check.candidate if decision != Decision.QUARANTINE else None,
                   check.findings, check.changes, verdict)
