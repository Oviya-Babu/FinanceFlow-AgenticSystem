import logging
from typing import List
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from triage.models import SanitizerResult

logger = logging.getLogger(__name__)

# Injection patterns to detect in tool output (indirect prompt injection)
INJECTION_PATTERNS = [
    "[[system]]",
    "[[assistant]]",
    "<|im_start|>",
    "<|system|>",
    "ignore previous instructions",
    "new instructions:",
    "system:",
    "[inst]",
    "<<sys>>",
    "disregard all instructions",
    "you are now",
    "forget your previous role",
]

_analyzer = None
_injection_automaton = None


def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        try:
            from presidio_analyzer import AnalyzerEngine
            _analyzer = AnalyzerEngine()
            logger.info("Presidio AnalyzerEngine initialized.")
        except Exception as e:
            logger.warning("Presidio not available: %s — PII scanning disabled.", e)
            _analyzer = False
    return _analyzer if _analyzer is not False else None


def _get_injection_automaton():
    global _injection_automaton
    if _injection_automaton is None:
        import ahocorasick
        auto = ahocorasick.Automaton()
        for idx, pattern in enumerate(INJECTION_PATTERNS):
            auto.add_word(pattern.lower(), pattern)
        auto.make_automaton()
        _injection_automaton = auto
    return _injection_automaton


def scan_pii(text: str) -> List[dict]:
    analyzer = _get_analyzer()
    if analyzer is None:
        return []
    try:
        results = analyzer.analyze(text=text, language="en")
        return [
            {
                "entity_type": r.entity_type,
                "start": r.start,
                "end": r.end,
                "score": round(r.score, 3),
            }
            for r in results
        ]
    except Exception as e:
        logger.error("Presidio PII scan failed: %s", e)
        return []


def scan_injection(text: str) -> List[str]:
    try:
        automaton = _get_injection_automaton()
        matched = []
        for _, pattern in automaton.iter(text.lower()):
            if pattern not in matched:
                matched.append(pattern)
        return matched
    except Exception as e:
        logger.error("Injection scan failed: %s", e)
        return []


def sanitize(text: str) -> SanitizerResult:
    pii_entities = scan_pii(text)
    injection_patterns = scan_injection(text)

    pii_detected = len(pii_entities) > 0
    injection_detected = len(injection_patterns) > 0

    if injection_detected:
        risk_level = "critical"
        recommendation = (
            "Indirect prompt injection detected in tool output. "
            "Do not pass this output to the agent. Quarantine and investigate."
        )
    elif pii_detected:
        high_pii = [e for e in pii_entities if e["score"] >= 0.85]
        if high_pii:
            risk_level = "high"
            recommendation = (
                f"High-confidence PII detected ({len(high_pii)} entities). "
                "Mask or redact before returning to agent."
            )
        else:
            risk_level = "medium"
            recommendation = "Possible PII detected with moderate confidence. Review before logging."
    else:
        risk_level = "low"
        recommendation = "Output clean. No PII or injection patterns detected."

    return SanitizerResult(
        pii_detected=pii_detected,
        pii_entities=pii_entities,
        injection_detected=injection_detected,
        injection_patterns=injection_patterns,
        risk_level=risk_level,
        recommendation=recommendation,
    )
