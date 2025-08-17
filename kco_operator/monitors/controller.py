"""Monitoring controller that orchestrates TApp monitoring workflow."""

import asyncio
from typing import Any

import structlog
from prometheus_client import Counter, Gauge, Histogram

from ..actions.registry import ActionContext, get_action_registry
from ..config import TAppConfig
from ..events.generator import EventGenerator
from ..utils.k8s import KubernetesClient
from ..utils.rate_limiter import RateLimiter
from .graphql import GraphQLMonitor
from .state import StateManager

logger = structlog.get_logger(__name__)

# Prometheus metrics
POLLS_TOTAL = Counter(
    "operator_kco_tapp_polls_total",
    "Total number of GraphQL polls executed",
    ["namespace", "tapp_name", "status"],
)

POLL_DURATION = Histogram(
    "operator_kco_tapp_poll_duration_seconds",
    "Time spent polling GraphQL endpoints",
    ["namespace", "tapp_name"],
)

EVENTS_GENERATED = Counter(
    "operator_kco_events_generated_total",
    "Total number of Kubernetes Events generated",
    ["namespace", "tapp_name", "event_type"],
)

ACTIONS_EXECUTED = Counter(
    "operator_kco_actions_executed_total",
    "Total number of actions executed",
    ["namespace", "tapp_name", "action", "status"],
)

ACTIVE_MONITORS = Gauge(
    "operator_kco_active_monitors", "Number of active TApp monitors"
)


class TAppMonitor:
    """Individual TApp monitor that handles a single TargetApp resource."""

    def __init__(
        self,
        namespace: str,
        name: str,
        config: TAppConfig,
        state_manager: StateManager,
        event_generator: EventGenerator,
        k8s_client: KubernetesClient,
        rate_limiter: RateLimiter,
    ) -> None:
        """Initialize TApp monitor.

        Args:
            namespace: Kubernetes namespace
            name: TargetApp name
            config: TApp configuration
            state_manager: Shared state manager
            event_generator: Event generator instance
            k8s_client: Kubernetes client
            rate_limiter: Rate limiter instance
        """
        self.namespace = namespace
        self.name = name
        self.config = config
        self.state_manager = state_manager
        self.event_generator = event_generator
        self.k8s_client = k8s_client
        self.rate_limiter = rate_limiter

        self.graphql_monitor: GraphQLMonitor | None = None
        self._monitor_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

        logger.info(
            "Initialized TApp monitor",
            namespace=namespace,
            tapp=name,
            polling_interval=config.polling_interval,
        )

    async def start(self) -> None:
        """Start monitoring this TApp."""
        if self._monitor_task is not None:
            logger.warning(
                "TApp monitor already started", namespace=self.namespace, tapp=self.name
            )
            return

        # Discover pods and create GraphQL monitor
        await self._initialize_graphql_monitor()

        if self.graphql_monitor is None:
            logger.error(
                "Failed to initialize GraphQL monitor",
                namespace=self.namespace,
                tapp=self.name,
            )
            return

        # Start monitoring loop
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Started TApp monitoring", namespace=self.namespace, tapp=self.name)

    async def stop(self) -> None:
        """Stop monitoring this TApp."""
        logger.info(
            "Stopping TApp monitoring", namespace=self.namespace, tapp=self.name
        )

        # Signal stop
        self._stop_event.set()

        # Cancel monitoring task
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        # Close GraphQL monitor
        if self.graphql_monitor:
            await self.graphql_monitor.close()
            self.graphql_monitor = None

        # Remove state
        await self.state_manager.remove_state(self.namespace, self.name)

        logger.info("Stopped TApp monitoring", namespace=self.namespace, tapp=self.name)

    async def _initialize_graphql_monitor(self) -> None:
        """Initialize GraphQL monitor by discovering pods or using direct URL."""
        try:
            # Check if graphqlEndpoint is a full URL
            if self.config.graphql_endpoint.startswith(("http://", "https://")):
                # Direct URL - use as-is (for external endpoints, port-forwarded, etc.)
                self.graphql_monitor = GraphQLMonitor(
                    base_url="",  # Empty base_url since we have the full URL
                    endpoint=self.config.graphql_endpoint,
                    timeout=self.config.timeout,
                    max_retries=self.config.max_retries,
                )

                logger.info(
                    "Initialized GraphQL monitor with direct URL",
                    namespace=self.namespace,
                    tapp=self.name,
                    url=self.config.graphql_endpoint,
                )
                return

            # Fallback to pod discovery for relative endpoints
            # Get label selector
            selector = self.config.selector.get("matchLabels", {})
            label_selector = ",".join([f"{k}={v}" for k, v in selector.items()])

            # Find pods
            pods = await self.k8s_client.get_pods_by_selector(
                namespace=self.namespace, label_selector=label_selector
            )

            if not pods:
                logger.warning(
                    "No pods found for TApp",
                    namespace=self.namespace,
                    tapp=self.name,
                    selector=label_selector,
                )
                return

            # Use first pod for GraphQL endpoint
            pod = pods[0]
            if not pod.status or not pod.status.pod_ip:
                logger.warning(
                    "Pod has no IP address",
                    namespace=self.namespace,
                    tapp=self.name,
                    pod=pod.metadata.name,
                )
                return

            # Construct GraphQL URL from pod IP
            base_url = f"http://{pod.status.pod_ip}:8080"  # Assume standard port

            self.graphql_monitor = GraphQLMonitor(
                base_url=base_url,
                endpoint=self.config.graphql_endpoint,
                timeout=self.config.timeout,
                max_retries=self.config.max_retries,
            )

            logger.info(
                "Initialized GraphQL monitor from pod discovery",
                namespace=self.namespace,
                tapp=self.name,
                pod=pod.metadata.name,
                url=f"{base_url}{self.config.graphql_endpoint}",
            )

        except Exception as e:
            logger.error(
                "Failed to initialize GraphQL monitor",
                namespace=self.namespace,
                tapp=self.name,
                error=str(e),
            )

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        logger.info(
            "Starting monitoring loop", namespace=self.namespace, tapp=self.name
        )

        while not self._stop_event.is_set():
            try:
                # Perform health check
                if not await self.graphql_monitor.health_check():
                    logger.warning(
                        "GraphQL endpoint health check failed",
                        namespace=self.namespace,
                        tapp=self.name,
                    )
                    POLLS_TOTAL.labels(
                        namespace=self.namespace,
                        tapp_name=self.name,
                        status="health_check_failed",
                    ).inc()
                else:
                    # Execute state query and process changes
                    await self._poll_and_process()

                # Wait for next poll interval
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self.config.polling_interval
                    )
                    break  # Stop event was set
                except asyncio.TimeoutError:
                    continue  # Normal timeout, continue polling

            except Exception as e:
                logger.error(
                    "Error in monitoring loop",
                    namespace=self.namespace,
                    tapp=self.name,
                    error=str(e),
                )
                POLLS_TOTAL.labels(
                    namespace=self.namespace, tapp_name=self.name, status="error"
                ).inc()

                # Wait before retrying
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=min(30, self.config.polling_interval),
                    )
                    break
                except asyncio.TimeoutError:
                    continue

        logger.info("Monitoring loop stopped", namespace=self.namespace, tapp=self.name)

    async def _poll_and_process(self) -> None:
        """Poll GraphQL endpoint and process state changes."""
        # Apply rate limiting
        if not await self.rate_limiter.acquire(
            self.namespace, self.name, timeout=self.config.polling_interval / 2
        ):
            logger.warning(
                "Rate limit exceeded, skipping poll",
                namespace=self.namespace,
                tapp=self.name,
            )
            POLLS_TOTAL.labels(
                namespace=self.namespace, tapp_name=self.name, status="rate_limited"
            ).inc()
            return

        with POLL_DURATION.labels(namespace=self.namespace, tapp_name=self.name).time():
            try:
                # Execute state query
                result = await self.graphql_monitor.query(self.config.state_query)

                POLLS_TOTAL.labels(
                    namespace=self.namespace, tapp_name=self.name, status="success"
                ).inc()

                # Update state and detect changes
                state_change = await self.state_manager.update_state(
                    self.namespace, self.name, result
                )

                # Generate events for state changes
                if state_change.has_changes or state_change.is_initial:
                    await self.event_generator.generate_state_change_event(state_change)

                    event_type = "initial" if state_change.is_initial else "change"
                    EVENTS_GENERATED.labels(
                        namespace=self.namespace,
                        tapp_name=self.name,
                        event_type=event_type,
                    ).inc()

                # Execute actions if configured
                if self.config.actions:
                    await self._process_actions(state_change)

            except Exception as e:
                logger.error(
                    "Failed to poll and process state",
                    namespace=self.namespace,
                    tapp=self.name,
                    error=str(e),
                )
                raise

    async def _process_actions(self, state_change) -> None:
        """Process configured actions for state changes."""
        action_registry = await get_action_registry()

        for action_config in self.config.actions:
            try:
                # Create action context
                context = ActionContext(
                    state_change=state_change,
                    trigger_config=action_config.trigger,
                    action_parameters=action_config.parameters,
                    tapp_config=self.config.dict(),
                )

                # Execute action
                result = await action_registry.execute_action(
                    action_config.action, context
                )

                ACTIONS_EXECUTED.labels(
                    namespace=self.namespace,
                    tapp_name=self.name,
                    action=action_config.action,
                    status=result.status.value,
                ).inc()

                logger.info(
                    "Action executed",
                    namespace=self.namespace,
                    tapp=self.name,
                    action=action_config.action,
                    status=result.status.value,
                    execution_time=result.execution_time_seconds,
                )

            except Exception as e:
                logger.error(
                    "Failed to execute action",
                    namespace=self.namespace,
                    tapp=self.name,
                    action=action_config.action,
                    error=str(e),
                )

                ACTIONS_EXECUTED.labels(
                    namespace=self.namespace,
                    tapp_name=self.name,
                    action=action_config.action,
                    status="failed",
                ).inc()


class MonitoringController:
    """Main controller that manages all TApp monitors."""

    def __init__(self, k8s_client: KubernetesClient, rate_limit_rpm: int = 100) -> None:
        """Initialize monitoring controller.

        Args:
            k8s_client: Kubernetes client instance
            rate_limit_rpm: Rate limit in requests per minute
        """
        self.k8s_client = k8s_client
        self.state_manager = StateManager()
        self.event_generator = EventGenerator(k8s_client)
        self.rate_limiter = RateLimiter(rate_limit_rpm)

        self._monitors: dict[str, TAppMonitor] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None

        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info("Initialized MonitoringController", rate_limit_rpm=rate_limit_rpm)

    def _get_monitor_key(self, namespace: str, name: str) -> str:
        """Generate unique key for monitor."""
        return f"{namespace}/{name}"

    async def start_monitoring(
        self, namespace: str, name: str, spec: dict[str, Any]
    ) -> None:
        """Start monitoring a TargetApp.

        Args:
            namespace: Kubernetes namespace
            name: TargetApp name
            spec: TargetApp spec
        """
        async with self._lock:
            monitor_key = self._get_monitor_key(namespace, name)

            if monitor_key in self._monitors:
                logger.warning(
                    "Monitor already exists for TApp", namespace=namespace, tapp=name
                )
                return

            try:
                # Convert camelCase fields to snake_case for TAppConfig
                converted_spec = {
                    "selector": spec.get("selector", {}),
                    "graphql_endpoint": spec.get("graphqlEndpoint", "/graphql"),
                    "polling_interval": spec.get("pollingInterval", 30),
                    "state_query": spec.get("stateQuery", ""),
                    "actions": spec.get("actions", []),
                    "timeout": spec.get("timeout", 10),
                    "max_retries": spec.get("maxRetries", 3),
                }

                # Parse configuration
                config = TAppConfig.model_validate(converted_spec)

                # Create and start monitor
                monitor = TAppMonitor(
                    namespace=namespace,
                    name=name,
                    config=config,
                    state_manager=self.state_manager,
                    event_generator=self.event_generator,
                    k8s_client=self.k8s_client,
                    rate_limiter=self.rate_limiter,
                )

                await monitor.start()
                self._monitors[monitor_key] = monitor

                ACTIVE_MONITORS.set(len(self._monitors))

                logger.info(
                    "Started monitoring TApp",
                    namespace=namespace,
                    tapp=name,
                    total_monitors=len(self._monitors),
                )

            except Exception as e:
                logger.error(
                    "Failed to start monitoring TApp",
                    namespace=namespace,
                    tapp=name,
                    error=str(e),
                )
                raise

    async def stop_monitoring(self, namespace: str, name: str) -> None:
        """Stop monitoring a TargetApp.

        Args:
            namespace: Kubernetes namespace
            name: TargetApp name
        """
        async with self._lock:
            monitor_key = self._get_monitor_key(namespace, name)

            monitor = self._monitors.pop(monitor_key, None)
            if monitor:
                await monitor.stop()

                ACTIVE_MONITORS.set(len(self._monitors))

                logger.info(
                    "Stopped monitoring TApp",
                    namespace=namespace,
                    tapp=name,
                    remaining_monitors=len(self._monitors),
                )
            else:
                logger.warning(
                    "No monitor found for TApp", namespace=namespace, tapp=name
                )

    async def update_monitoring(
        self, namespace: str, name: str, spec: dict[str, Any]
    ) -> None:
        """Update monitoring configuration for a TargetApp.

        Args:
            namespace: Kubernetes namespace
            name: TargetApp name
            spec: Updated TargetApp spec
        """
        # Stop existing monitoring
        await self.stop_monitoring(namespace, name)

        # Start with new configuration
        await self.start_monitoring(namespace, name, spec)

        logger.info("Updated monitoring configuration", namespace=namespace, tapp=name)

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup task for expired resources."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                await self.rate_limiter.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in cleanup loop", error=str(e))

    async def shutdown(self) -> None:
        """Shutdown all monitors and cleanup resources."""
        logger.info("Shutting down MonitoringController")

        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            # Stop all monitors
            for monitor in list(self._monitors.values()):
                await monitor.stop()

            self._monitors.clear()
            ACTIVE_MONITORS.set(0)

        logger.info("MonitoringController shutdown complete")

    def get_stats(self) -> dict[str, Any]:
        """Get monitoring statistics.

        Returns:
            Dictionary with monitoring statistics
        """
        return {
            "active_monitors": len(self._monitors),
            "monitored_tapps": list(self._monitors.keys()),
            "state_manager_stats": self.state_manager.get_stats(),
            "event_generator_stats": self.event_generator.get_stats(),
            "rate_limiter_stats": self.rate_limiter.get_stats(),
        }
