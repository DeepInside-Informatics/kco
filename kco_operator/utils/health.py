"""Health check utilities for the operator."""

import asyncio
import json
from typing import Any, Dict, Optional
from datetime import datetime, timezone

import aiohttp
from aiohttp import web
import structlog


logger = structlog.get_logger(__name__)


class HealthCheckServer:
    """HTTP server for health checks and operator status."""
    
    def __init__(self, port: int = 8081) -> None:
        """Initialize health check server.
        
        Args:
            port: Port to listen on
        """
        self.port = port
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self._startup_time = datetime.now(timezone.utc)
        self._monitoring_controller = None
        
        # Setup routes
        self.app.router.add_get('/healthz', self._health_handler)
        self.app.router.add_get('/readyz', self._readiness_handler)
        self.app.router.add_get('/stats', self._stats_handler)
        self.app.router.add_get('/metrics', self._metrics_handler)
        
        logger.info("Initialized HealthCheckServer", port=port)
    
    def set_monitoring_controller(self, controller) -> None:
        """Set monitoring controller for stats collection."""
        self._monitoring_controller = controller
    
    async def start(self) -> None:
        """Start the health check server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
        await self.site.start()
        
        logger.info("Health check server started", port=self.port)
    
    async def stop(self) -> None:
        """Stop the health check server."""
        if self.site:
            await self.site.stop()
            self.site = None
        
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
        
        logger.info("Health check server stopped")
    
    async def _health_handler(self, request: web.Request) -> web.Response:
        """Handle health check requests."""
        # Basic liveness check - just return OK if the server is running
        health_data = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": (datetime.now(timezone.utc) - self._startup_time).total_seconds(),
            "version": "0.1.0"
        }
        
        return web.json_response(health_data)
    
    async def _readiness_handler(self, request: web.Request) -> web.Response:
        """Handle readiness check requests."""
        # More comprehensive readiness check
        ready = True
        checks = {}
        
        # Check if monitoring controller is available
        if self._monitoring_controller is None:
            ready = False
            checks["monitoring_controller"] = "not_available"
        else:
            checks["monitoring_controller"] = "available"
        
        # Additional checks can be added here
        # - Check Kubernetes connectivity
        # - Check critical dependencies
        
        status_code = 200 if ready else 503
        response_data = {
            "status": "ready" if ready else "not_ready",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": checks
        }
        
        return web.json_response(response_data, status=status_code)
    
    async def _stats_handler(self, request: web.Request) -> web.Response:
        """Handle statistics requests."""
        stats = {
            "operator": {
                "uptime_seconds": (datetime.now(timezone.utc) - self._startup_time).total_seconds(),
                "startup_time": self._startup_time.isoformat(),
                "version": "0.1.0"
            }
        }
        
        # Add monitoring controller stats if available
        if self._monitoring_controller:
            try:
                monitoring_stats = self._monitoring_controller.get_stats()
                stats["monitoring"] = monitoring_stats
            except Exception as e:
                logger.warning("Failed to get monitoring stats", error=str(e))
                stats["monitoring"] = {"error": str(e)}
        
        return web.json_response(stats)
    
    async def _metrics_handler(self, request: web.Request) -> web.Response:
        """Handle Prometheus metrics exposition."""
        # Note: This is a simple text endpoint. In production, you'd typically
        # use the prometheus_client library's generate_latest() function
        
        try:
            from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
            
            # Generate Prometheus metrics
            metrics_data = generate_latest()
            
            return web.Response(
                body=metrics_data,
                content_type=CONTENT_TYPE_LATEST
            )
            
        except ImportError:
            # Fallback if prometheus_client is not available
            return web.json_response(
                {"error": "Prometheus client not available"},
                status=503
            )
        except Exception as e:
            logger.error("Error generating metrics", error=str(e))
            return web.json_response(
                {"error": f"Failed to generate metrics: {str(e)}"},
                status=500
            )


# Global health check server instance
_health_server: Optional[HealthCheckServer] = None


async def start_health_server(port: int = 8081, monitoring_controller=None) -> HealthCheckServer:
    """Start the global health check server.
    
    Args:
        port: Port to listen on
        monitoring_controller: Monitoring controller for stats
        
    Returns:
        HealthCheckServer instance
    """
    global _health_server
    
    if _health_server is not None:
        logger.warning("Health server already started")
        return _health_server
    
    _health_server = HealthCheckServer(port)
    
    if monitoring_controller:
        _health_server.set_monitoring_controller(monitoring_controller)
    
    await _health_server.start()
    return _health_server


async def stop_health_server() -> None:
    """Stop the global health check server."""
    global _health_server
    
    if _health_server is not None:
        await _health_server.stop()
        _health_server = None


def get_health_server() -> Optional[HealthCheckServer]:
    """Get the global health check server instance."""
    return _health_server