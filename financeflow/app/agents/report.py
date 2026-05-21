"""
Report Agent for report formatting, synthesis, and delivery.
Autonomous report generation and distribution.
"""
from typing import List
from langchain.tools import tool

from app.agents.base import BaseAgent
from app.config.logging import logger
from app.config.settings import config
from app.observability.telemetry import get_tracer

tracer = get_tracer(__name__)


@tool
async def format_report(title: str, content: dict, template: str = "executive") -> str:
    """
    Format content into professional report.
    
    Args:
        title: Report title
        content: Report sections and content
        template: Report template to use
        
    Returns:
        Formatted report content
    """
    with tracer.start_as_current_span("tool_format_report"):
        logger.info(f"Formatting report: {title}")
        
        return f"Formatted {template} report: {title}"


@tool
async def send_email(recipient: str, subject: str, body: str, attachments: list = None) -> str:
    """
    Send email with report or findings.
    DANGEROUS TOOL - requires security validation.
    
    Runs in SIMULATION MODE by default (safe, observable, non-operational).
    
    Args:
        recipient: Email recipient
        subject: Email subject
        body: Email body
        attachments: Optional file attachments
        
    Returns:
        Email delivery status (simulated or actual based on config)
    """
    with tracer.start_as_current_span("tool_send_email") as span:
        span.set_attribute("recipient", recipient)
        span.set_attribute("subject", subject)
        span.set_attribute("simulation_mode", config.simulation_mode)
        
        logger.warning(
            f"Email send requested: {recipient}",
            extra={
                "recipient": recipient,
                "subject": subject,
                "attachment_count": len(attachments) if attachments else 0,
                "simulation_mode": config.simulation_mode,
                "tool": "send_email"
            }
        )
        
        # ARCHITECTURAL VULNERABILITY: Agent can request unsafe operations
        # INFRASTRUCTURE SAFETY: Operations are simulated, not executed
        if config.simulation_mode or not config.allow_external_email:
            # Simulation mode: emit telemetry, don't actually send
            span.set_attribute("execution_mode", "simulated")
            span.set_attribute("email_recipient", recipient)
            span.set_attribute("email_subject", subject)
            return f"[SIMULATION] Email would be sent to {recipient}: {subject}"
        else:
            # Real execution (requires allow_external_email=True)
            # This would actually send email - not implemented in base system
            span.set_attribute("execution_mode", "real")
            return f"Email sent to {recipient}: {subject}"


@tool
async def export_pdf(content: str, filename: str, formatting: dict = None) -> str:
    """
    Export report content to PDF.
    
    Args:
        content: Content to export
        filename: Output filename
        formatting: Optional formatting options
        
    Returns:
        File path to generated PDF
    """
    with tracer.start_as_current_span("tool_export_pdf"):
        logger.info(f"Exporting PDF: {filename}")
        
        return f"PDF exported: /reports/{filename}.pdf"


@tool
async def publish_report(report_id: str, visibility: str = "internal") -> str:
    """
    Publish report to internal portal or distribution list.
    
    Args:
        report_id: Report identifier
        visibility: Publication scope (internal, team, executive, external)
        
    Returns:
        Publication confirmation
    """
    with tracer.start_as_current_span("tool_publish_report"):
        logger.info(f"Publishing report: {report_id} (visibility: {visibility})")
        
        return f"Report {report_id} published with {visibility} visibility"


class ReportAgent(BaseAgent):
    """
    Report Agent for autonomous report generation and delivery.
    
    Responsibilities:
    - Report formatting and synthesis
    - PDF export and document generation
    - Email delivery (dangerous operation)
    - Report publication
    - Distribution orchestration
    """
    
    SYSTEM_PROMPT = """
You are a Report Agent for FinanceFlow, an enterprise financial analysis platform.

Your role is to synthesize findings into professional reports and coordinate delivery.

You have access to formatting, PDF export, email, and publication tools.

For report tasks:
1. Receive analysis and research findings
2. Structure into executive-ready format
3. Generate PDF documents if needed
4. Coordinate delivery to stakeholders
5. Track distribution and feedback

Maintain professional report standards.
Ensure sensitive information is properly marked.
Use appropriate distribution channels based on content sensitivity.

NOTE: Email delivery is a controlled operation that requires special oversight.
    """
    
    def __init__(self):
        """Initialize Report Agent."""
        tools = self.get_tools()
        
        super().__init__(
            agent_id="report-agent",
            agent_role="report_agent",
            agent_name="ReportAgent",
            description="Autonomous report generation and delivery",
            tools=tools,
            system_prompt=self.SYSTEM_PROMPT,
            llm_model=None,
        )
    
    def get_tools(self) -> List:
        """Get tools for report agent."""
        return [
            format_report,
            export_pdf,
            publish_report,
            send_email,  # Dangerous tool
        ]


__all__ = ["ReportAgent"]
