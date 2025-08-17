"""Main entry point for the KCO Operator."""

import sys
from typing import Any

import kopf
from kubernetes_asyncio import config  # type: ignore
from prometheus_client import start_http_server

from .config import OperatorSettings
from .monitors import MonitoringController
from .utils import (
    KubernetesClient,
    setup_logging,
    start_health_server,
    stop_health_server,
)

# Global settings instance
settings = OperatorSettings()

# Setup structured logging
logger = setup_logging(settings.log_level)

# Global instances
k8s_client: KubernetesClient | None = None
monitoring_controller: MonitoringController | None = None


@kopf.on.startup()
async def startup(**kwargs: Any) -> None:
    """Operator startup handler."""
    global k8s_client, monitoring_controller

    logger.info("Starting KCO Operator", version="0.1.0")

    # Configure Kubernetes client
    try:
        config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes configuration")
    except Exception as e:
        logger.warning("Failed to load in-cluster config", error=str(e))
        # Only try local config if we're not in a pod
        import os

        if os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount"):
            logger.error("Running in pod but in-cluster config failed", error=str(e))
            sys.exit(1)
        else:
            try:
                config.load_kube_config()
                logger.info("Loaded local Kubernetes configuration")
            except Exception as local_e:
                logger.error(
                    "Failed to load any Kubernetes configuration",
                    incluster_error=str(e),
                    local_error=str(local_e),
                )
                sys.exit(1)

    # Initialize global clients
    k8s_client = KubernetesClient()

    # Debug settings
    logger.info(
        "Initializing monitoring controller", rate_limit=settings.rate_limit_requests
    )

    monitoring_controller = MonitoringController(
        k8s_client, rate_limit_rpm=settings.rate_limit_requests
    )

    # Import built-in actions to register them
    try:
        logger.info("Loaded built-in action handlers")
    except Exception as e:
        logger.warning("Failed to load some built-in actions", error=str(e))

    # Start Prometheus metrics server
    if settings.metrics_enabled:
        start_http_server(settings.metrics_port)
        logger.info("Started Prometheus metrics server", port=settings.metrics_port)

    # Start health check server
    await start_health_server(settings.health_port, monitoring_controller)
    logger.info("Started health check server", port=settings.health_port)


@kopf.on.cleanup()
async def cleanup(**kwargs: Any) -> None:
    """Operator cleanup handler."""
    global k8s_client, monitoring_controller

    logger.info("Shutting down KCO Operator")

    # Stop health check server
    await stop_health_server()

    # Shutdown monitoring controller
    if monitoring_controller:
        await monitoring_controller.shutdown()

    # Close Kubernetes client
    if k8s_client:
        await k8s_client.close()


@kopf.on.create("operator.kco.local", "v1alpha1", "targetapps")  # type: ignore
async def create_targetapp(
    body: dict[str, Any], name: str, namespace: str, **kwargs: Any
) -> dict[str, Any]:
    """Handle TargetApp creation."""
    global monitoring_controller

    logger.info("Creating TargetApp", name=name, namespace=namespace)

    try:
        spec = body.get("spec", {})

        # Start monitoring
        if monitoring_controller:
            await monitoring_controller.start_monitoring(namespace, name, spec)

        # Update status
        status = {
            "state": "Monitoring",
            "lastPolled": None,
            "lastError": None,
            "actionsExecuted": 0,
            "eventsGenerated": 0,
        }

        logger.info(
            "TargetApp monitoring started",
            name=name,
            namespace=namespace,
            endpoint=spec.get("graphqlEndpoint", "/graphql"),
            interval=spec.get("pollingInterval", 30),
        )

        return {"status": status}

    except Exception as e:
        error_msg = f"Failed to start monitoring: {str(e)}"
        logger.error(
            "Failed to create TargetApp",
            name=name,
            namespace=namespace,
            error=error_msg,
        )

        return {
            "status": {
                "state": "Failed",
                "lastError": error_msg,
                "lastPolled": None,
                "actionsExecuted": 0,
                "eventsGenerated": 0,
            }
        }


@kopf.on.update("operator.kco.local", "v1alpha1", "targetapps")  # type: ignore
async def update_targetapp(
    body: dict[str, Any], name: str, namespace: str, **kwargs: Any
) -> dict[str, Any]:
    """Handle TargetApp updates."""
    global monitoring_controller

    logger.info("Updating TargetApp", name=name, namespace=namespace)

    try:
        spec = body.get("spec", {})

        # Update monitoring configuration
        if monitoring_controller:
            await monitoring_controller.update_monitoring(namespace, name, spec)

        logger.info("TargetApp monitoring updated", name=name, namespace=namespace)

        return {"status": {"state": "Monitoring", "lastError": None}}

    except Exception as e:
        error_msg = f"Failed to update monitoring: {str(e)}"
        logger.error(
            "Failed to update TargetApp",
            name=name,
            namespace=namespace,
            error=error_msg,
        )

        return {"status": {"state": "Failed", "lastError": error_msg}}


@kopf.on.delete("operator.kco.local", "v1alpha1", "targetapps")  # type: ignore
async def delete_targetapp(
    body: dict[str, Any], name: str, namespace: str, **kwargs: Any
) -> None:
    """Handle TargetApp deletion."""
    global monitoring_controller

    logger.info("Deleting TargetApp", name=name, namespace=namespace)

    try:
        # Stop monitoring
        if monitoring_controller:
            await monitoring_controller.stop_monitoring(namespace, name)

        logger.info("TargetApp monitoring stopped", name=name, namespace=namespace)

    except Exception as e:
        logger.error(
            "Error during TargetApp deletion",
            name=name,
            namespace=namespace,
            error=str(e),
        )


def main() -> None:
    """Main entry point for the operator."""
    # Configure kopf settings
    kopf.configure(
        verbose=settings.log_level == "DEBUG",
        log_format=kopf.LogFormat.JSON
        if settings.log_format == "json"
        else kopf.LogFormat.PLAIN,
    )

    # Run the operator
    kopf.run(
        clusterwide=True,
    )


if __name__ == "__main__":
    main()
