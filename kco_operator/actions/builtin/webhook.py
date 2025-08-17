"""Built-in action for sending webhooks."""

import json
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import aiohttp
import structlog

from ..base import ActionHandler, ActionContext, ActionResult, ActionStatus
from ..registry import register_action


logger = structlog.get_logger(__name__)


@register_action("webhook", "Send HTTP webhook notifications")
class WebhookAction(ActionHandler):
    """Action handler for sending webhook notifications."""
    
    def __init__(self, name: str, description: str) -> None:
        """Initialize the webhook action."""
        super().__init__(name, description)
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def can_handle(self, context: ActionContext) -> bool:
        """Check if this action can handle the given context."""
        # Check if trigger condition is met
        return self._evaluate_trigger_condition(
            context.state_change,
            context.trigger_config
        )
    
    async def execute(self, context: ActionContext) -> ActionResult:
        """Execute webhook action."""
        try:
            # Get parameters
            url = context.action_parameters.get("url")
            method = context.action_parameters.get("method", "POST").upper()
            headers = context.action_parameters.get("headers", {})
            payload_template = context.action_parameters.get("payload", {})
            timeout = context.action_parameters.get("timeout", 30)
            verify_ssl = context.action_parameters.get("verifySSL", True)
            
            if not url:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message="Missing required parameter: url",
                    details={},
                    execution_time_seconds=0
                )
            
            # Prepare payload with state change data
            payload = self._prepare_payload(payload_template, context)
            
            # Prepare headers
            request_headers = {
                "Content-Type": "application/json",
                "User-Agent": "KCO-Operator/0.1.0",
                **headers
            }
            
            session = await self._get_session()
            
            logger.info(
                "Sending webhook",
                url=url,
                method=method,
                tapp=context.state_change.tapp_name,
                namespace=context.state_change.namespace
            )
            
            # Send webhook
            async with session.request(
                method=method,
                url=url,
                json=payload,
                headers=request_headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
                ssl=verify_ssl
            ) as response:
                response_text = await response.text()
                
                if response.status >= 200 and response.status < 300:
                    logger.info(
                        "Webhook sent successfully",
                        url=url,
                        status=response.status,
                        tapp=context.state_change.tapp_name
                    )
                    
                    return ActionResult(
                        status=ActionStatus.SUCCESS,
                        message=f"Webhook sent successfully (HTTP {response.status})",
                        details={
                            "url": url,
                            "method": method,
                            "status_code": response.status,
                            "response_body": response_text[:500]  # Truncate response
                        },
                        execution_time_seconds=0  # Will be set by registry
                    )
                else:
                    logger.warning(
                        "Webhook returned error status",
                        url=url,
                        status=response.status,
                        response=response_text[:200],
                        tapp=context.state_change.tapp_name
                    )
                    
                    return ActionResult(
                        status=ActionStatus.FAILED,
                        message=f"Webhook failed with HTTP {response.status}",
                        details={
                            "url": url,
                            "status_code": response.status,
                            "response_body": response_text[:500]
                        },
                        execution_time_seconds=0
                    )
                    
        except aiohttp.ClientError as e:
            logger.error(
                "HTTP error sending webhook",
                url=url,
                error=str(e),
                tapp=context.state_change.tapp_name
            )
            
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"HTTP error: {str(e)}",
                details={"error": str(e), "url": url},
                execution_time_seconds=0
            )
            
        except Exception as e:
            logger.error(
                "Unexpected error sending webhook",
                error=str(e),
                tapp=context.state_change.tapp_name
            )
            
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Unexpected error: {str(e)}",
                details={"error": str(e)},
                execution_time_seconds=0
            )
    
    def _prepare_payload(self, template: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Prepare webhook payload from template and context."""
        # Base payload with state change information
        payload = {
            "timestamp": context.state_change.new_snapshot.timestamp.isoformat(),
            "targetApp": {
                "name": context.state_change.tapp_name,
                "namespace": context.state_change.namespace
            },
            "stateChange": {
                "isInitial": context.state_change.is_initial,
                "changedFields": list(context.state_change.changed_fields),
                "newState": context.state_change.new_snapshot.data
            },
            "trigger": context.trigger_config,
            "action": "webhook"
        }
        
        # Add old state if not initial
        if not context.state_change.is_initial:
            payload["stateChange"]["oldState"] = context.state_change.old_snapshot.data
        
        # Merge with custom template
        if template:
            payload.update(template)
        
        # Support simple template variables
        payload_str = json.dumps(payload)
        payload_str = payload_str.replace("{{tapp_name}}", context.state_change.tapp_name)
        payload_str = payload_str.replace("{{namespace}}", context.state_change.namespace)
        payload_str = payload_str.replace("{{timestamp}}", payload["timestamp"])
        
        return json.loads(payload_str)
    
    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None