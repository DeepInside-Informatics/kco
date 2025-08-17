"""GraphQL client for monitoring Target Applications."""

import asyncio
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import aiohttp
import structlog
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.exceptions import TransportQueryError, TransportServerError


logger = structlog.get_logger(__name__)


class GraphQLMonitor:
    """Async GraphQL client for monitoring TApp endpoints."""
    
    def __init__(
        self,
        base_url: str,
        endpoint: str = "/graphql",
        timeout: int = 10,
        max_retries: int = 3,
    ) -> None:
        """Initialize GraphQL monitor.
        
        Args:
            base_url: Base URL of the target application
            endpoint: GraphQL endpoint path
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Handle direct URLs (when endpoint is a full URL)
        if endpoint.startswith(('http://', 'https://')):
            self.url = endpoint
        else:
            self.url = urljoin(f"{self.base_url}/", endpoint.lstrip("/"))
        
        # Initialize transport and client
        self.transport: Optional[AIOHTTPTransport] = None
        self.client: Optional[Client] = None
        self._session: Optional[aiohttp.ClientSession] = None
        
        logger.info(
            "Initialized GraphQL monitor",
            url=self.url,
            timeout=timeout,
            max_retries=max_retries
        )
    
    async def _ensure_client(self) -> Client:
        """Ensure GraphQL client is initialized."""
        if self.client is None:
            # Initialize transport and client with basic configuration
            # Avoiding complex session management that causes "Session is closed" errors
            self.transport = AIOHTTPTransport(
                url=self.url,
                timeout=self.timeout
            )
            self.client = Client(
                transport=self.transport,
                fetch_schema_from_transport=False  # Skip schema fetching for performance
            )
        
        return self.client
    
    async def query(self, query_string: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a GraphQL query with retry logic.
        
        Args:
            query_string: GraphQL query string
            variables: Query variables
            
        Returns:
            Query result data
            
        Raises:
            Exception: If query fails after all retries
        """
        client = await self._ensure_client()
        query_obj = gql(query_string)
        
        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(
                    "Executing GraphQL query",
                    url=self.url,
                    attempt=attempt + 1,
                    query=query_string[:100] + "..." if len(query_string) > 100 else query_string
                )
                
                result = await client.execute_async(query_obj, variable_values=variables)
                
                logger.debug(
                    "GraphQL query successful",
                    url=self.url,
                    attempt=attempt + 1
                )
                
                return result
                
            except (TransportQueryError, TransportServerError) as e:
                logger.warning(
                    "GraphQL query failed",
                    url=self.url,
                    attempt=attempt + 1,
                    error=str(e),
                    will_retry=attempt < self.max_retries
                )
                
                if attempt == self.max_retries:
                    logger.error(
                        "GraphQL query failed after all retries",
                        url=self.url,
                        max_retries=self.max_retries,
                        error=str(e)
                    )
                    raise
                
                # Exponential backoff
                await asyncio.sleep(2 ** attempt)
                
            except Exception as e:
                logger.error(
                    "Unexpected error during GraphQL query",
                    url=self.url,
                    attempt=attempt + 1,
                    error=str(e)
                )
                
                if attempt == self.max_retries:
                    raise
                
                await asyncio.sleep(2 ** attempt)
        
        # This should never be reached
        raise RuntimeError("Query failed after all retries")
    
    async def health_check(self) -> bool:
        """Check if the GraphQL endpoint is healthy.
        
        Returns:
            True if endpoint is accessible, False otherwise
        """
        try:
            # Simple introspection query to check endpoint health
            health_query = """
            query HealthCheck {
                __schema {
                    queryType {
                        name
                    }
                }
            }
            """
            
            await self.query(health_query)
            logger.debug("GraphQL endpoint health check passed", url=self.url)
            return True
            
        except Exception as e:
            logger.warning(
                "GraphQL endpoint health check failed",
                url=self.url,
                error=str(e)
            )
            return False
    
    async def close(self) -> None:
        """Close the GraphQL client and cleanup resources."""
        if self.transport:
            await self.transport.close()
            self.transport = None
        
        self.client = None
        
        logger.debug("Closed GraphQL monitor", url=self.url)