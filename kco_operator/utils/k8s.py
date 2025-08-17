"""Kubernetes API client utilities."""

from datetime import UTC

import structlog
from kubernetes_asyncio import client

logger = structlog.get_logger(__name__)


class KubernetesClient:
    """Async Kubernetes API client wrapper."""

    def __init__(self) -> None:
        """Initialize the Kubernetes client."""
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.custom_objects = client.CustomObjectsApi()

    async def get_pods_by_selector(
        self, namespace: str, label_selector: str
    ) -> list[client.V1Pod]:
        """Get pods matching the label selector."""
        try:
            response = await self.core_v1.list_namespaced_pod(
                namespace=namespace, label_selector=label_selector
            )
            return response.items
        except Exception as e:
            logger.error(
                "Failed to get pods by selector",
                namespace=namespace,
                selector=label_selector,
                error=str(e),
            )
            raise

    async def create_event(
        self,
        namespace: str,
        involved_object_name: str,
        involved_object_kind: str,
        reason: str,
        message: str,
        event_type: str = "Normal",
    ) -> None:
        """Create a Kubernetes Event."""
        from datetime import datetime

        event = client.CoreV1Event(
            metadata=client.V1ObjectMeta(
                generate_name=f"{involved_object_name}-", namespace=namespace
            ),
            involved_object=client.V1ObjectReference(
                kind=involved_object_kind,
                name=involved_object_name,
                namespace=namespace,
            ),
            reason=reason,
            message=message,
            type=event_type,
            first_timestamp=datetime.now(UTC),
            last_timestamp=datetime.now(UTC),
            count=1,
            source=client.V1EventSource(component="kco-operator"),
        )

        try:
            await self.core_v1.create_namespaced_event(namespace=namespace, body=event)
            logger.info(
                "Created Kubernetes Event",
                namespace=namespace,
                object=involved_object_name,
                reason=reason,
                type=event_type,
            )
        except Exception as e:
            logger.error(
                "Failed to create Kubernetes Event",
                namespace=namespace,
                object=involved_object_name,
                reason=reason,
                error=str(e),
            )
            raise

    async def scale_deployment(
        self, namespace: str, deployment_name: str, replicas: int
    ) -> None:
        """Scale a deployment to the specified number of replicas."""
        try:
            # Get current deployment
            deployment = await self.apps_v1.read_namespaced_deployment(
                name=deployment_name, namespace=namespace
            )

            # Update replicas
            deployment.spec.replicas = replicas

            # Apply the update
            await self.apps_v1.patch_namespaced_deployment(
                name=deployment_name, namespace=namespace, body=deployment
            )

            logger.info(
                "Scaled deployment",
                namespace=namespace,
                deployment=deployment_name,
                replicas=replicas,
            )
        except Exception as e:
            logger.error(
                "Failed to scale deployment",
                namespace=namespace,
                deployment=deployment_name,
                replicas=replicas,
                error=str(e),
            )
            raise

    async def restart_pod(
        self, namespace: str, pod_name: str, grace_period: int = 30
    ) -> None:
        """Restart a pod by deleting it (assuming it's managed by a controller)."""
        try:
            await self.core_v1.delete_namespaced_pod(
                name=pod_name, namespace=namespace, grace_period_seconds=grace_period
            )

            logger.info(
                "Deleted pod for restart",
                namespace=namespace,
                pod=pod_name,
                grace_period=grace_period,
            )
        except Exception as e:
            logger.error(
                "Failed to restart pod", namespace=namespace, pod=pod_name, error=str(e)
            )
            raise

    async def close(self) -> None:
        """Close the Kubernetes client connections."""
        await self.core_v1.api_client.close()
        await self.apps_v1.api_client.close()
        await self.custom_objects.api_client.close()
