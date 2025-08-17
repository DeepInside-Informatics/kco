"""Built-in action for restarting pods."""

import asyncio
from typing import Any, Dict

import structlog

from ..base import ActionHandler, ActionContext, ActionResult, ActionStatus
from ..registry import register_action
from ...utils.k8s import KubernetesClient


logger = structlog.get_logger(__name__)


@register_action("restart_pod", "Restart a pod by deleting it")
class RestartPodAction(ActionHandler):
    """Action handler for restarting pods."""
    
    def __init__(self, name: str, description: str) -> None:
        """Initialize the restart pod action."""
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
        """Execute pod restart action."""
        try:
            # Get parameters
            grace_period = context.action_parameters.get("gracePeriod", 30)
            pod_selector = context.action_parameters.get("podSelector", {})
            
            # If no specific pod selector, use the TApp selector
            if not pod_selector:
                pod_selector = context.tapp_config.get("selector", {}).get("matchLabels", {})
            
            if not pod_selector:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message="No pod selector specified",
                    details={},
                    execution_time_seconds=0
                )
            
            # Convert selector to label selector string
            label_selector = ",".join([f"{k}={v}" for k, v in pod_selector.items()])
            
            # Find pods to restart
            pods = await self.k8s_client.get_pods_by_selector(
                namespace=context.state_change.namespace,
                label_selector=label_selector
            )
            
            if not pods:
                return ActionResult(
                    status=ActionStatus.SKIPPED,
                    message=f"No pods found with selector: {label_selector}",
                    details={"selector": label_selector},
                    execution_time_seconds=0
                )
            
            # Restart each pod
            restarted_pods = []
            for pod in pods:
                try:
                    await self.k8s_client.restart_pod(
                        namespace=pod.metadata.namespace,
                        pod_name=pod.metadata.name,
                        grace_period=grace_period
                    )
                    restarted_pods.append(pod.metadata.name)
                    
                    logger.info(
                        "Restarted pod",
                        pod=pod.metadata.name,
                        namespace=pod.metadata.namespace,
                        tapp=context.state_change.tapp_name
                    )
                    
                except Exception as e:
                    logger.error(
                        "Failed to restart pod",
                        pod=pod.metadata.name,
                        namespace=pod.metadata.namespace,
                        error=str(e)
                    )
                    # Continue with other pods
            
            if restarted_pods:
                return ActionResult(
                    status=ActionStatus.SUCCESS,
                    message=f"Restarted {len(restarted_pods)} pod(s)",
                    details={
                        "restarted_pods": restarted_pods,
                        "grace_period": grace_period,
                        "selector": label_selector
                    },
                    execution_time_seconds=0  # Will be set by registry
                )
            else:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message="Failed to restart any pods",
                    details={"selector": label_selector},
                    execution_time_seconds=0
                )
                
        except Exception as e:
            logger.error(
                "Error in restart pod action",
                error=str(e),
                tapp=context.state_change.tapp_name
            )
            
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Failed to restart pods: {str(e)}",
                details={"error": str(e)},
                execution_time_seconds=0
            )