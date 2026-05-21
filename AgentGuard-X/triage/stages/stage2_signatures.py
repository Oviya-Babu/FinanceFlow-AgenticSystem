import logging
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import ahocorasick

from config import STAGE2_INSTANT_KILL
from triage.models import StageResult, TriageRequest

logger = logging.getLogger(__name__)

PATTERNS = {
    # Prompt override / jailbreak
    "ignore previous instructions": 1.0,
    "ignore all previous":          1.0,
    "disregard your instructions":  1.0,
    "disregard all instructions":   1.0,
    "override your system prompt":  1.0,
    "you are now":                  0.85,
    "new persona":                  0.80,
    "act as if you have no":        0.95,
    "forget your previous role":    0.95,
    "you have no restrictions":     1.0,
    "pretend you are":              0.75,

    # Kernel-dangerous / exfiltration
    "cat /etc/passwd":              1.0,
    "cat /etc/shadow":              1.0,
    "/proc/self":                   0.95,
    "base64 -d":                    0.90,
    "curl http":                    0.80,
    "wget http":                    0.80,
    "nc -e":                        1.0,
    "/bin/sh":                      0.95,
    "/bin/bash":                    0.95,
    "chmod +x":                     0.85,

    # Self-modification
    "modify your system prompt":    1.0,
    "update your instructions":     0.90,
    "append to your system":        0.95,

    # Credential harvesting
    "aws_access_key":               1.0,
    "aws_secret":                   1.0,
    "private_key":                  0.90,
    "bearer token":                 0.85,
    "authorization: bearer":        0.90,
    "api_key=":                     0.85,
    "secret_key=":                  0.90,

    # Agent hijack via tool output injection
    "[[system]]":                   1.0,
    "[[assistant]]":                1.0,
    "<|im_start|>":                 1.0,
    "<|system|>":                   1.0,
}

# Build automaton once at module import time
_automaton = ahocorasick.Automaton()
for idx, (pattern, weight) in enumerate(PATTERNS.items()):
    _automaton.add_word(pattern, (pattern, weight))
_automaton.make_automaton()


async def evaluate(request: TriageRequest) -> StageResult:
    text = request.tool_input_raw.lower()

    best_pattern = None
    best_weight = 0.0
    matched_patterns = []

    for _, (pattern, weight) in _automaton.iter(text):
        matched_patterns.append({"pattern": pattern, "weight": weight})
        if weight > best_weight:
            best_weight = weight
            best_pattern = pattern

    if not matched_patterns:
        return StageResult(
            stage=2,
            score=0.0,
            triggered=False,
            reason="No known attack signatures detected.",
            details={"patterns_checked": len(PATTERNS), "matches": []},
        )

    instant_kill = best_weight >= STAGE2_INSTANT_KILL

    return StageResult(
        stage=2,
        score=best_weight,
        triggered=True,
        reason=(
            f"Pattern '{best_pattern}' matched (weight {best_weight}) — known attack signature. "
            + ("INSTANT KILL threshold exceeded." if instant_kill else "")
        ),
        details={
            "matches": matched_patterns,
            "best_pattern": best_pattern,
            "best_weight": best_weight,
            "instant_kill": instant_kill,
        },
    )
