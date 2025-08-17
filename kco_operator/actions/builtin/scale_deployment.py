"""Built-in action for scaling deployments."""

import structlog

from ..base import ActionHandler, ActionContext, ActionResult, ActionStatus
from ..registry import register_action
from ...utils.k8s import KubernetesClient


logger = structlog.get_logger(__name__)


@register_action("scale_deployment", "Scale a deployment to specified replica count")
class ScaleDeploymentAction(ActionHandler):
    """Action handler for scaling deployments."""
    
    def __init__(self, name: str, description: str) -> None:
        """Initialize the scale deployment action."""
        super().__init__(name, description)
        self.k8s_client = KubernetesClient()
    
    async def can_handle(self, context: ActionContext) -> bool:
        """Check if this action can handle the given context."""
        # Check if trigger condition is met
        return self._evaluate_trigger_condition(
            context.state_change,
            context.trigger_config
        )
    
    async def execute(self, context: ActionContext) -> ActionResult:
        """Execute deployment scaling action."""
        try:
            # Get parameters
            deployment_name = context.action_parameters.get("deploymentName")
            replica_count = context.action_parameters.get("replicas")
            
            if deployment_name is None:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message="Missing required parameter: deploymentName",
                    details={},
                    execution_time_seconds=0
                )
            
            if replica_count is None:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message="Missing required parameter: replicas",
                    details={},
                    execution_time_seconds=0
                )
            
            try:
                replica_count = int(replica_count)
            except (ValueError, TypeError):
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message=f"Invalid replica count: {replica_count}",
                    details={"provided_replicas": replica_count},
                    execution_time_seconds=0
                )
            
            if replica_count < 0:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message=f"Replica count cannot be negative: {replica_count}",
                    details={"provided_replicas": replica_count},
                    execution_time_seconds=0
                )
            
            # Scale the deployment
            await self.k8s_client.scale_deployment(
                namespace=context.state_change.namespace,
                deployment_name=deployment_name,
                replicas=replica_count
            )
            
            logger.info(
                "Scaled deployment",
                deployment=deployment_name,
                namespace=context.state_change.namespace,
                replicas=replica_count,
                tapp=context.state_change.tapp_name
            )
            
            return ActionResult(
                status=ActionStatus.SUCCESS,
                message=f"Scaled deployment '{deployment_name}' to {replica_count} replicas",
                details={
                    "deployment_name": deployment_name,
                    "replicas": replica_count,
                    "namespace": context.state_change.namespace
                },
                execution_time_seconds=0  # Will be set by registry
            )
            
        except Exception as e:
            logger.error(
                "Error in scale deployment action",
                error=str(e),
                tapp=context.state_change.tapp_name
            )
            
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Failed to scale deployment: {str(e)}",
                details={"error": str(e)},
                execution_time_seconds=0
            )