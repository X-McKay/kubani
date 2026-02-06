"""
Gateway Observability Evaluation Script

This script evaluates the observability features of the MCP Gateway:
1. Metrics collection and exposure
2. Request tracing
3. Logging capabilities
4. Health check aggregation
"""

import asyncio
import httpx
from typing import Dict, Any, List
import json


class ObservabilityEvaluator:
    """Evaluates gateway observability features."""
    
    def __init__(self, gateway_url: str, metrics_url: str):
        self.gateway_url = gateway_url
        self.metrics_url = metrics_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        """Close the client."""
        await self.client.aclose()
    
    async def check_metrics_endpoint(self) -> Dict[str, Any]:
        """Check if metrics endpoint is available and what metrics are exposed."""
        try:
            response = await self.client.get(self.metrics_url)
            response.raise_for_status()
            
            metrics_text = response.text
            
            # Parse Prometheus metrics
            metrics = {}
            for line in metrics_text.split('\n'):
                if line and not line.startswith('#'):
                    parts = line.split()
                    if len(parts) >= 2:
                        metric_name = parts[0].split('{')[0]
                        if metric_name not in metrics:
                            metrics[metric_name] = []
                        metrics[metric_name].append(line)
            
            return {
                "available": True,
                "metric_count": len(metrics),
                "metrics": list(metrics.keys()),
                "sample_metrics": {k: v[:3] for k, v in list(metrics.items())[:5]}
            }
        except Exception as e:
            return {
                "available": False,
                "error": str(e)
            }
    
    async def check_health_aggregation(self) -> Dict[str, Any]:
        """Check if gateway aggregates health from upstream servers."""
        try:
            response = await self.client.get(f"{self.gateway_url}/health")
            response.raise_for_status()
            health = response.json()
            
            # Check if health includes upstream server status
            has_upstream_health = "servers" in health or "backends" in health
            
            return {
                "available": True,
                "aggregates_upstream": has_upstream_health,
                "health_data": health
            }
        except Exception as e:
            return {
                "available": False,
                "error": str(e)
            }
    
    async def check_request_tracing(self) -> Dict[str, Any]:
        """Check if gateway supports request tracing."""
        try:
            # Make a request with trace headers
            headers = {
                "X-Trace-Id": "test-trace-123",
                "X-Request-Id": "test-request-456"
            }
            
            response = await self.client.post(
                f"{self.gateway_url}/call",
                json={
                    "server": "skills-mcp",
                    "tool": "list_skills",
                    "arguments": {}
                },
                headers=headers
            )
            
            # Check if trace headers are propagated
            response_headers = dict(response.headers)
            has_trace_id = "x-trace-id" in response_headers or "traceparent" in response_headers
            
            return {
                "supported": has_trace_id,
                "request_headers": headers,
                "response_headers": {
                    k: v for k, v in response_headers.items()
                    if k.lower().startswith('x-') or k.lower() == 'traceparent'
                }
            }
        except Exception as e:
            return {
                "supported": False,
                "error": str(e)
            }
    
    async def check_logging_capabilities(self) -> Dict[str, Any]:
        """Check gateway logging capabilities."""
        # This would typically involve checking logs via kubectl or log aggregation
        # For now, we'll document what to look for
        return {
            "check_manually": True,
            "what_to_check": [
                "Request/response logging",
                "Error logging with context",
                "Structured logging (JSON format)",
                "Log levels (DEBUG, INFO, WARN, ERROR)",
                "Request correlation IDs"
            ]
        }
    
    async def evaluate_routing_visibility(self) -> Dict[str, Any]:
        """Evaluate visibility into request routing."""
        try:
            # Make requests to different servers
            servers = ["skills-mcp", "discord-mcp", "memory-mcp"]
            routing_info = []
            
            for server in servers:
                try:
                    response = await self.client.post(
                        f"{self.gateway_url}/call",
                        json={
                            "server": server,
                            "tool": "list_skills" if server == "skills-mcp" else "health",
                            "arguments": {}
                        }
                    )
                    
                    routing_info.append({
                        "server": server,
                        "status": response.status_code,
                        "routed": response.status_code == 200,
                        "headers": {
                            k: v for k, v in dict(response.headers).items()
                            if k.lower().startswith('x-')
                        }
                    })
                except Exception as e:
                    routing_info.append({
                        "server": server,
                        "status": "error",
                        "error": str(e)
                    })
            
            return {
                "routing_tested": True,
                "servers_tested": len(servers),
                "routing_info": routing_info
            }
        except Exception as e:
            return {
                "routing_tested": False,
                "error": str(e)
            }


async def main():
    """Run observability evaluation."""
    
    gateway_url = "http://mcp-gateway.ai-agents-test.svc:8080"
    metrics_url = "http://mcp-gateway.ai-agents-test.svc:9090/metrics"
    
    evaluator = ObservabilityEvaluator(gateway_url, metrics_url)
    
    try:
        print("=" * 80)
        print("MCP Gateway Observability Evaluation")
        print("=" * 80)
        print()
        
        # Check metrics
        print("1. Metrics Endpoint")
        print("-" * 80)
        metrics_result = await evaluator.check_metrics_endpoint()
        if metrics_result["available"]:
            print(f"✓ Metrics endpoint available")
            print(f"  Metrics exposed: {metrics_result['metric_count']}")
            print(f"  Sample metrics: {', '.join(list(metrics_result['metrics'])[:10])}")
        else:
            print(f"✗ Metrics endpoint not available: {metrics_result.get('error')}")
        print()
        
        # Check health aggregation
        print("2. Health Check Aggregation")
        print("-" * 80)
        health_result = await evaluator.check_health_aggregation()
        if health_result["available"]:
            print(f"✓ Health endpoint available")
            print(f"  Aggregates upstream health: {health_result['aggregates_upstream']}")
            if health_result['aggregates_upstream']:
                print(f"  Health data: {json.dumps(health_result['health_data'], indent=2)}")
        else:
            print(f"✗ Health endpoint not available: {health_result.get('error')}")
        print()
        
        # Check request tracing
        print("3. Request Tracing")
        print("-" * 80)
        tracing_result = await evaluator.check_request_tracing()
        if tracing_result["supported"]:
            print(f"✓ Request tracing supported")
            print(f"  Response headers: {json.dumps(tracing_result['response_headers'], indent=2)}")
        else:
            print(f"✗ Request tracing not detected")
            if "error" in tracing_result:
                print(f"  Error: {tracing_result['error']}")
        print()
        
        # Check logging
        print("4. Logging Capabilities")
        print("-" * 80)
        logging_result = await evaluator.check_logging_capabilities()
        print("  Manual checks required:")
        for check in logging_result["what_to_check"]:
            print(f"    - {check}")
        print()
        
        # Check routing visibility
        print("5. Request Routing Visibility")
        print("-" * 80)
        routing_result = await evaluator.evaluate_routing_visibility()
        if routing_result["routing_tested"]:
            print(f"✓ Routing tested for {routing_result['servers_tested']} servers")
            for info in routing_result["routing_info"]:
                status = "✓" if info.get("routed") else "✗"
                print(f"  {status} {info['server']}: {info.get('status', 'unknown')}")
        else:
            print(f"✗ Routing test failed: {routing_result.get('error')}")
        print()
        
        # Summary
        print("=" * 80)
        print("Summary")
        print("=" * 80)
        
        results = {
            "metrics": metrics_result,
            "health": health_result,
            "tracing": tracing_result,
            "logging": logging_result,
            "routing": routing_result
        }
        
        # Save results
        with open("gateway_observability_results.json", "w") as f:
            json.dump(results, f, indent=2)
        
        print("Results saved to gateway_observability_results.json")
        print()
        
        # Scoring
        score = 0
        max_score = 5
        
        if metrics_result.get("available"):
            score += 1
        if health_result.get("available") and health_result.get("aggregates_upstream"):
            score += 1
        if tracing_result.get("supported"):
            score += 1
        if routing_result.get("routing_tested"):
            score += 1
        # Logging gets 1 point by default (needs manual verification)
        score += 0.5
        
        print(f"Observability Score: {score}/{max_score} ({score/max_score*100:.0f}%)")
        
    finally:
        await evaluator.close()


if __name__ == "__main__":
    asyncio.run(main())
