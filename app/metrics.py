# Prometheus Metrics for OPA Policy Decisions
# Exports real-time metrics for Grafana visualization

from prometheus_client import Counter, Histogram, Gauge
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# COUNTERS - Total counts of events
# ============================================================================

# Total OPA decisions (allow/deny) by agent role and tool
opa_decisions_total = Counter(
    'opa_decisions_total',
    'Total OPA policy decisions',
    ['verdict', 'agent_role', 'tool_name']
)

# Denials by reason (RBAC_DENIED, VELOCITY_EXCEEDED, CONTEXT_RESTRICTED, etc)
opa_denials_by_reason = Counter(
    'opa_denials_by_reason',
    'OPA denials categorized by reason',
    ['reason']
)

# Context restriction violations
opa_context_restrictions_triggered = Counter(
    'opa_context_restrictions_triggered',
    'Times context-based restrictions were triggered',
    ['agent_role', 'restriction_type']
)

# Policy evaluation errors
opa_policy_evaluation_errors_total = Counter(
    'opa_policy_evaluation_errors_total',
    'Total errors during policy evaluation',
    ['error_type']
)

# False positives (legitimate agents getting denied)
opa_false_positive_count_total = Counter(
    'opa_false_positive_count_total',
    'False positive denials (legitimate agents blocked)',
    ['agent_role', 'tool_name']
)

# ============================================================================
# HISTOGRAMS - Distribution of values
# ============================================================================

# OPA decision latency in milliseconds
opa_decision_latency_ms = Histogram(
    'opa_decision_latency_ms',
    'OPA policy decision latency (ms)',
    buckets=[1, 3, 5, 10, 20, 50, 100, 200]
)

# Policy evaluation time per rule category
opa_rule_evaluation_time_ms = Histogram(
    'opa_rule_evaluation_time_ms',
    'Time to evaluate each policy rule (ms)',
    ['rule_name'],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 50]
)

# ============================================================================
# GAUGES - Current values
# ============================================================================

# OPA server status (1=up, 0=down)
opa_up = Gauge(
    'opa_up',
    'OPA server health status (1=up, 0=down)'
)

# Policy compilation status (1=success, 0=failed)
opa_policy_compilation_status = Gauge(
    'opa_policy_compilation_status',
    'Policy compilation status (1=success, 0=failed)',
    ['policy']
)

# Current request rate per agent
agent_current_request_rate = Gauge(
    'agent_current_request_rate',
    'Current requests per second by agent role',
    ['agent_role']
)

# Current rate limit percentage (0-100)
agent_rate_limit_percentage = Gauge(
    'agent_rate_limit_percentage',
    'Current rate as percentage of limit (0-100)',
    ['agent_role', 'tool_name', 'limit_tier']  # limit_tier: per_sec, per_min, per_hour
)

# ============================================================================
# DECISION TRACKING & METRICS
# ============================================================================

class DecisionMetricsTracker:
    """
    Tracks OPA decisions and exports metrics for Grafana.
    Called by pipeline.py after each OPA decision.
    """
    
    @staticmethod
    def record_decision(
        verdict: str,  # 'allow' or 'deny'
        agent_id: str,
        agent_role: str,
        tool_name: str,
        latency_ms: float,
        reason: Optional[str] = None,
        context: Optional[Dict] = None,
        velocity_info: Optional[Dict] = None
    ):
        """
        Record an OPA decision with all metadata.
        
        Args:
            verdict: 'allow' or 'deny'
            agent_id: Unique agent identifier
            agent_role: OrchestratorAgent, ResearchAgent, AnalystAgent, ReportAgent
            tool_name: Name of tool requested
            latency_ms: Decision latency in milliseconds
            reason: Reason for deny (RBAC_DENIED, VELOCITY_EXCEEDED, CONTEXT_RESTRICTED)
            context: Tool execution context
            velocity_info: Rate limit information (per_sec, per_min, per_hour)
        """
        try:
            # Record decision verdict
            opa_decisions_total.labels(
                verdict=verdict,
                agent_role=agent_role,
                tool_name=tool_name
            ).inc()
            
            # Record latency histogram
            opa_decision_latency_ms.observe(latency_ms)
            
            # Record deny reason if denied
            if verdict == 'deny' and reason:
                opa_denials_by_reason.labels(reason=reason).inc()
            
            # Record velocity info if available
            if velocity_info:
                DecisionMetricsTracker._record_velocity_metrics(
                    agent_role, tool_name, velocity_info
                )
            
            logger.debug(
                f"Decision recorded: {verdict.upper()} | "
                f"{agent_role}/{tool_name} | {latency_ms:.2f}ms"
            )
            
        except Exception as e:
            logger.error(f"Error recording decision metrics: {e}")
            opa_policy_evaluation_errors_total.labels(
                error_type='metrics_recording_error'
            ).inc()
    
    @staticmethod
    def _record_velocity_metrics(
        agent_role: str,
        tool_name: str,
        velocity_info: Dict
    ):
        """Record rate limit metrics."""
        try:
            for tier in ['per_sec', 'per_min', 'per_hour']:
                if tier in velocity_info:
                    current = velocity_info[tier].get('current', 0)
                    hard_limit = velocity_info[tier].get('hard_limit', 1)
                    
                    # Calculate percentage
                    percentage = (current / hard_limit * 100) if hard_limit > 0 else 0
                    percentage = min(100, percentage)
                    
                    agent_rate_limit_percentage.labels(
                        agent_role=agent_role,
                        tool_name=tool_name,
                        limit_tier=tier
                    ).set(percentage)
                    
                    # Also set current rate gauge
                    if tier == 'per_sec':
                        agent_current_request_rate.labels(
                            agent_role=agent_role
                        ).set(current)
        except Exception as e:
            logger.error(f"Error recording velocity metrics: {e}")
    
    @staticmethod
    def record_policy_compilation(policy_name: str, success: bool):
        """Record policy compilation status."""
        status = 1 if success else 0
        opa_policy_compilation_status.labels(policy=policy_name).set(status)
    
    @staticmethod
    def record_context_restriction(agent_role: str, restriction_type: str):
        """Record context-based restriction trigger."""
        opa_context_restrictions_triggered.labels(
            agent_role=agent_role,
            restriction_type=restriction_type
        ).inc()
    
    @staticmethod
    def record_false_positive(agent_role: str, tool_name: str):
        """Record a false positive (legitimate agent denied)."""
        opa_false_positive_count_total.labels(
            agent_role=agent_role,
            tool_name=tool_name
        ).inc()
    
    @staticmethod
    def set_opa_status(is_up: bool):
        """Set OPA server status."""
        opa_up.set(1 if is_up else 0)


# ============================================================================
# DECISION CONSISTENCY VALIDATOR
# ============================================================================

class DecisionConsistencyValidator:
    """
    Validates OPA decisions are deterministic.
    Detects non-deterministic behavior (same input → different outputs).
    """
    
    def __init__(self):
        self.decision_cache: Dict[str, Dict] = {}
        self.consistency_check_failures = Counter(
            'decision_consistency_check_failures',
            'Times same request got different decisions',
            ['agent_role', 'tool_name']
        )
    
    def validate_consistency(
        self,
        agent_role: str,
        tool_name: str,
        tool_context: Dict,
        current_verdict: str,
        current_reason: Optional[str] = None
    ) -> bool:
        """
        Check if decision is consistent with previous identical request.
        
        Returns:
            True if consistent (or first time), False if inconsistent
        """
        try:
            # Create cache key from inputs
            cache_key = self._create_cache_key(agent_role, tool_name, tool_context)
            
            if cache_key in self.decision_cache:
                previous = self.decision_cache[cache_key]
                
                # Check if verdict matches
                if previous['verdict'] != current_verdict:
                    logger.error(
                        f"CRITICAL: Non-deterministic decision detected! "
                        f"{agent_role}/{tool_name} "
                        f"Previous: {previous['verdict']} → Current: {current_verdict}"
                    )
                    self.consistency_check_failures.labels(
                        agent_role=agent_role,
                        tool_name=tool_name
                    ).inc()
                    return False
            else:
                # Cache this decision for future checks
                self.decision_cache[cache_key] = {
                    'verdict': current_verdict,
                    'reason': current_reason,
                    'timestamp': datetime.utcnow().isoformat()
                }
            
            return True
            
        except Exception as e:
            logger.error(f"Error during consistency check: {e}")
            return True  # Don't block on error
    
    @staticmethod
    def _create_cache_key(agent_role: str, tool_name: str, tool_context: Dict) -> str:
        """Create a deterministic cache key for a decision."""
        import hashlib
        import json
        
        key_data = {
            'agent_role': agent_role,
            'tool_name': tool_name,
            'context': tool_context
        }
        key_json = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_json.encode()).hexdigest()


# Global consistency validator instance
consistency_validator = DecisionConsistencyValidator()
