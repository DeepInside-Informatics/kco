"""Built-in action for patching Kubernetes resources."""

import json

import structlog
from kubernetes_asyncio import client

from ...utils.k8s import KubernetesClient
from ..base import ActionContext, ActionHandler, ActionResult, ActionStatus
from ..registry import register_action

logger = structlog.get_logger(__name__)


@register_action("patch_resource", "Patch a Kubernetes resource with specified changes")
class PatchResourceAction(ActionHandler):
    """Action handler for patching Kubernetes resources."""

    def __init__(self, name: str, description: str) -> None:
        """Initialize the patch resource action."""
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
        """Execute resource patching action."""
        try:
            # Get parameters
            resource_type = context.action_parameters.get("resourceType")
            resource_name = context.action_parameters.get("resourceName")
            patch_data = context.action_parameters.get("patchData")
            # Note: apiVersion parameter available but not currently used in this implementation

            if not resource_type:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message="Missing required parameter: resourceType",
                    details={},
                    execution_time_seconds=0
                )

            if not resource_name:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message="Missing required parameter: resourceName",
                    details={},
                    execution_time_seconds=0
                )

            if not patch_data:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message="Missing required parameter: patchData",
                    details={},
                    execution_time_seconds=0
                )

            # Determine which API client to use based on resource type
            namespace = context.state_change.namespace

            try:
                if resource_type.lower() in ["pod", "service", "configmap", "secret"]:
                    # Core API resources
                    api_client = self.k8s_client.core_v1

                    if resource_type.lower() == "pod":
                        await api_client.patch_namespaced_pod(
                            name=resource_name,
                            namespace=namespace,
                            body=patch_data
                        )
                    elif resource_type.lower() == "service":
                        await api_client.patch_namespaced_service(
                            name=resource_name,
                            namespace=namespace,
                            body=patch_data
                        )
                    elif resource_type.lower() == "configmap":
                        await api_client.patch_namespaced_config_map(
                            name=resource_name,
                            namespace=namespace,
                            body=patch_data
                        )
                    elif resource_type.lower() == "secret":
                        await api_client.patch_namespaced_secret(
                            name=resource_name,
                            namespace=namespace,
                            body=patch_data
                        )

                elif resource_type.lower() in ["deployment", "replicaset", "daemonset", "statefulset"]:
                    # Apps API resources
                    api_client = self.k8s_client.apps_v1

                    if resource_type.lower() == "deployment":
                        await api_client.patch_namespaced_deployment(
                            name=resource_name,
                            namespace=namespace,
                            body=patch_data
                        )
                    elif resource_type.lower() == "replicaset":
                        await api_client.patch_namespaced_replica_set(
                            name=resource_name,
                            namespace=namespace,
                            body=patch_data
                        )
                    elif resource_type.lower() == "daemonset":
                        await api_client.patch_namespaced_daemon_set(
                            name=resource_name,
                            namespace=namespace,
                            body=patch_data
                        )
                    elif resource_type.lower() == "statefulset":
                        await api_client.patch_namespaced_stateful_set(
                            name=resource_name,
                            namespace=namespace,
                            body=patch_data
                        )

                else:
                    return ActionResult(
                        status=ActionStatus.FAILED,
                        message=f"Unsupported resource type: {resource_type}",
                        details={"supported_types": [
                            "pod", "service", "configmap", "secret",
                            "deployment", "replicaset", "daemonset", "statefulset"
                        ]},
                        execution_time_seconds=0
                    )

                logger.info(
                    "Patched resource",
                    resource_type=resource_type,
                    resource_name=resource_name,
                    namespace=namespace,
                    tapp=context.state_change.tapp_name
                )

                return ActionResult(
                    status=ActionStatus.SUCCESS,
                    message=f"Successfully patched {resource_type} '{resource_name}'",
                    details={
                        "resource_type": resource_type,
                        "resource_name": resource_name,
                        "namespace": namespace,
                        "patch_data": patch_data
                    },
                    execution_time_seconds=0  # Will be set by registry
                )

            except client.ApiException as e:
                error_msg = f"Kubernetes API error: {e.status} - {e.reason}"
                if e.body:
                    try:
                        error_details = json.loads(e.body)
                        error_msg += f" - {error_details.get('message', '')}"
                    except json.JSONDecodeError:
                        pass

                return ActionResult(
                    status=ActionStatus.FAILED,
                    message=error_msg,
                    details={
                        "api_error": {
                            "status": e.status,
                            "reason": e.reason,
                            "body": e.body
                        }
                    },
                    execution_time_seconds=0
                )

        except Exception as e:
            logger.error(
                "Error in patch resource action",
                error=str(e),
                tapp=context.state_change.tapp_name
            )

            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Failed to patch resource: {str(e)}",
                details={"error": str(e)},
                execution_time_seconds=0
            )
