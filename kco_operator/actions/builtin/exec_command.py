"""Built-in action for executing commands in pods."""

import asyncio
from typing import Any

import structlog
from kubernetes_asyncio import client
from kubernetes_asyncio.stream import WsApiClient

from ...utils.k8s import KubernetesClient
from ..base import ActionContext, ActionHandler, ActionResult, ActionStatus
from ..registry import register_action

logger = structlog.get_logger(__name__)


@register_action("exec_command", "Execute commands in target application pods")
class ExecCommandAction(ActionHandler):
    """Action handler for executing commands in pods."""

    def __init__(self, name: str, description: str) -> None:
        """Initialize the exec command action."""
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
        """Execute command action."""
        try:
            # Get parameters
            command = context.action_parameters.get("command")
            container = context.action_parameters.get("container")
            pod_selector = context.action_parameters.get("podSelector", {})
            timeout = context.action_parameters.get("timeout", 60)
            working_dir = context.action_parameters.get("workingDir")

            if not command:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message="Missing required parameter: command",
                    details={},
                    execution_time_seconds=0
                )

            # Parse command (support both string and array formats)
            if isinstance(command, str):
                cmd_args = ["/bin/sh", "-c", command]
            elif isinstance(command, list):
                cmd_args = command
            else:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    message="Command must be string or array",
                    details={"provided_command": str(command)},
                    execution_time_seconds=0
                )

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

            # Find pods to execute command in
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

            # Execute command in each pod
            results = []
            for pod in pods:
                try:
                    result = await self._exec_in_pod(
                        pod=pod,
                        command=cmd_args,
                        container=container,
                        timeout=timeout,
                        working_dir=working_dir
                    )
                    results.append(result)

                except Exception as e:
                    logger.error(
                        "Failed to execute command in pod",
                        pod=pod.metadata.name,
                        namespace=pod.metadata.namespace,
                        command=cmd_args,
                        error=str(e)
                    )
                    results.append({
                        "pod": pod.metadata.name,
                        "success": False,
                        "error": str(e),
                        "stdout": "",
                        "stderr": "",
                        "exit_code": -1
                    })

            # Determine overall success
            successful_executions = [r for r in results if r["success"]]

            if successful_executions:
                status = ActionStatus.SUCCESS
                message = f"Command executed successfully in {len(successful_executions)}/{len(results)} pods"
            else:
                status = ActionStatus.FAILED
                message = "Command failed in all pods"

            return ActionResult(
                status=status,
                message=message,
                details={
                    "command": cmd_args,
                    "selector": label_selector,
                    "results": results,
                    "successful_pods": len(successful_executions),
                    "total_pods": len(results)
                },
                execution_time_seconds=0  # Will be set by registry
            )

        except Exception as e:
            logger.error(
                "Error in exec command action",
                error=str(e),
                tapp=context.state_change.tapp_name
            )

            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Failed to execute command: {str(e)}",
                details={"error": str(e)},
                execution_time_seconds=0
            )

    async def _exec_in_pod(
        self,
        pod: client.V1Pod,
        command: list[str],
        container: str | None = None,
        timeout: int = 60,
        working_dir: str | None = None
    ) -> dict[str, Any]:
        """Execute command in a specific pod."""
        pod_name = pod.metadata.name
        namespace = pod.metadata.namespace

        # Determine container to use
        if container:
            # Use specified container
            target_container = container
        elif pod.spec.containers and len(pod.spec.containers) == 1:
            # Use the only container
            target_container = pod.spec.containers[0].name
        elif pod.spec.containers:
            # Use first container if multiple exist
            target_container = pod.spec.containers[0].name
            logger.warning(
                "Multiple containers found, using first one",
                pod=pod_name,
                container=target_container,
                available_containers=[c.name for c in pod.spec.containers]
            )
        else:
            raise ValueError(f"No containers found in pod {pod_name}")

        logger.info(
            "Executing command in pod",
            pod=pod_name,
            namespace=namespace,
            container=target_container,
            command=command
        )

        try:
            # Create websocket client for exec
            ws_client = WsApiClient()
            core_v1 = client.CoreV1Api(api_client=ws_client)

            # Build exec parameters
            exec_params = {
                "name": pod_name,
                "namespace": namespace,
                "command": command,
                "container": target_container,
                "stderr": True,
                "stdin": False,
                "stdout": True,
                "tty": False
            }

            # Add working directory if specified
            if working_dir:
                # Note: Kubernetes doesn't directly support changing working directory
                # We need to wrap the command to change directory first
                if isinstance(command, list) and len(command) >= 3 and command[0:2] == ["/bin/sh", "-c"]:
                    # Modify the shell command to include cd
                    original_cmd = command[2]
                    command[2] = f"cd {working_dir} && {original_cmd}"
                else:
                    # Wrap command in shell with cd
                    cmd_str = " ".join(command)
                    command = ["/bin/sh", "-c", f"cd {working_dir} && {cmd_str}"]

                exec_params["command"] = command

            # Execute with timeout
            resp = await asyncio.wait_for(
                core_v1.connect_get_namespaced_pod_exec(**exec_params),
                timeout=timeout
            )

            # Parse response
            stdout = ""
            stderr = ""
            exit_code = 0

            if resp:
                lines = resp.split('\n')
                for line in lines:
                    if line.startswith('1'):  # stdout channel
                        stdout += line[1:] + '\n'
                    elif line.startswith('2'):  # stderr channel
                        stderr += line[1:] + '\n'
                    elif line.startswith('3'):  # error channel
                        # Extract exit code if possible
                        try:
                            import json
                            error_data = json.loads(line[1:])
                            if 'status' in error_data:
                                if error_data['status'] == 'Success':
                                    exit_code = 0
                                else:
                                    exit_code = 1
                        except Exception:
                            exit_code = 1

            success = exit_code == 0

            logger.info(
                "Command execution completed",
                pod=pod_name,
                container=target_container,
                success=success,
                exit_code=exit_code
            )

            return {
                "pod": pod_name,
                "container": target_container,
                "success": success,
                "exit_code": exit_code,
                "stdout": stdout.strip(),
                "stderr": stderr.strip(),
                "command": command
            }

        except asyncio.TimeoutError:
            logger.warning(
                "Command execution timed out",
                pod=pod_name,
                container=target_container,
                timeout=timeout
            )

            return {
                "pod": pod_name,
                "container": target_container,
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
                "error": "timeout"
            }

        except Exception as e:
            logger.error(
                "Error executing command in pod",
                pod=pod_name,
                container=target_container,
                error=str(e)
            )

            return {
                "pod": pod_name,
                "container": target_container,
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "error": str(e)
            }

        finally:
            if 'ws_client' in locals():
                await ws_client.close()
