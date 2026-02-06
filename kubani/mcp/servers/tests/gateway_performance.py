"""
Gateway Performance Measurement Script

This script measures and compares:
1. Request latency (gateway vs direct)
2. Throughput (requests per second)
3. Concurrent request handling
4. Error rates
5. Resource usage
"""

import asyncio
import time
import statistics
from dataclasses import dataclass
from typing import List, Dict, Any
import httpx
import json


@dataclass
class PerformanceMetrics:
    """Performance metrics for a test run."""
    test_name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_duration_seconds: float
    min_latency_ms: float
    max_latency_ms: float
    mean_latency_ms: float
    median_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    requests_per_second: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "test_name": self.test_name,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": self.successful_requests / self.total_requests if self.total_requests > 0 else 0,
            "total_duration_seconds": self.total_duration_seconds,
            "min_latency_ms": self.min_latency_ms,
            "max_latency_ms": self.max_latency_ms,
            "mean_latency_ms": self.mean_latency_ms,
            "median_latency_ms": self.median_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "requests_per_second": self.requests_per_second,
        }


class PerformanceTester:
    """Performance testing utility."""
    
    def __init__(self, gateway_url: str, direct_urls: Dict[str, str]):
        self.gateway_url = gateway_url
        self.direct_urls = direct_urls
        self.gateway_client = httpx.AsyncClient(timeout=30.0)
        self.direct_clients = {
            name: httpx.AsyncClient(timeout=30.0)
            for name in direct_urls
        }
    
    async def close(self):
        """Close all clients."""
        await self.gateway_client.aclose()
        for client in self.direct_clients.values():
            await client.aclose()
    
    async def call_via_gateway(
        self,
        server_id: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> tuple[bool, float]:
        """Call a tool via gateway and return (success, latency_ms)."""
        start_time = time.time()
        try:
            response = await self.gateway_client.post(
                f"{self.gateway_url}/call",
                json={
                    "server": server_id,
                    "tool": tool_name,
                    "arguments": arguments
                }
            )
            response.raise_for_status()
            latency = (time.time() - start_time) * 1000
            return True, latency
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            print(f"Gateway call failed: {e}")
            return False, latency
    
    async def call_direct(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> tuple[bool, float]:
        """Call a tool directly and return (success, latency_ms)."""
        start_time = time.time()
        try:
            client = self.direct_clients[server_name]
            url = self.direct_urls[server_name]
            response = await client.post(
                f"{url}/call",
                json={
                    "tool": tool_name,
                    "arguments": arguments
                }
            )
            response.raise_for_status()
            latency = (time.time() - start_time) * 1000
            return True, latency
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            print(f"Direct call failed: {e}")
            return False, latency
    
    async def run_sequential_test(
        self,
        test_name: str,
        num_requests: int,
        call_func
    ) -> PerformanceMetrics:
        """Run sequential requests and measure performance."""
        latencies = []
        successes = 0
        failures = 0
        
        start_time = time.time()
        
        for i in range(num_requests):
            success, latency = await call_func()
            latencies.append(latency)
            if success:
                successes += 1
            else:
                failures += 1
        
        total_duration = time.time() - start_time
        
        return PerformanceMetrics(
            test_name=test_name,
            total_requests=num_requests,
            successful_requests=successes,
            failed_requests=failures,
            total_duration_seconds=total_duration,
            min_latency_ms=min(latencies),
            max_latency_ms=max(latencies),
            mean_latency_ms=statistics.mean(latencies),
            median_latency_ms=statistics.median(latencies),
            p95_latency_ms=statistics.quantiles(latencies, n=20)[18] if len(latencies) > 1 else latencies[0],
            p99_latency_ms=statistics.quantiles(latencies, n=100)[98] if len(latencies) > 1 else latencies[0],
            requests_per_second=num_requests / total_duration,
        )
    
    async def run_concurrent_test(
        self,
        test_name: str,
        num_requests: int,
        concurrency: int,
        call_func
    ) -> PerformanceMetrics:
        """Run concurrent requests and measure performance."""
        latencies = []
        successes = 0
        failures = 0
        
        start_time = time.time()
        
        # Create batches of concurrent requests
        for batch_start in range(0, num_requests, concurrency):
            batch_size = min(concurrency, num_requests - batch_start)
            tasks = [call_func() for _ in range(batch_size)]
            results = await asyncio.gather(*tasks)
            
            for success, latency in results:
                latencies.append(latency)
                if success:
                    successes += 1
                else:
                    failures += 1
        
        total_duration = time.time() - start_time
        
        return PerformanceMetrics(
            test_name=test_name,
            total_requests=num_requests,
            successful_requests=successes,
            failed_requests=failures,
            total_duration_seconds=total_duration,
            min_latency_ms=min(latencies),
            max_latency_ms=max(latencies),
            mean_latency_ms=statistics.mean(latencies),
            median_latency_ms=statistics.median(latencies),
            p95_latency_ms=statistics.quantiles(latencies, n=20)[18] if len(latencies) > 1 else latencies[0],
            p99_latency_ms=statistics.quantiles(latencies, n=100)[98] if len(latencies) > 1 else latencies[0],
            requests_per_second=num_requests / total_duration,
        )


async def main():
    """Run performance tests."""
    
    # Configuration
    gateway_url = "http://mcp-gateway.ai-agents-test.svc:8080"
    direct_urls = {
        "skills": "http://skills-mcp-server.ai-agents.svc:8080",
        "discord": "http://discord-mcp-server.ai-agents.svc:8080",
        "memory": "http://memory-mcp-server.ai-agents.svc:8080",
    }
    
    tester = PerformanceTester(gateway_url, direct_urls)
    results = []
    
    try:
        print("=" * 80)
        print("MCP Gateway Performance Evaluation")
        print("=" * 80)
        print()
        
        # Test 1: Sequential requests via gateway
        print("Test 1: Sequential requests via gateway (100 requests)")
        metrics = await tester.run_sequential_test(
            "gateway_sequential",
            100,
            lambda: tester.call_via_gateway("skills-mcp", "list_skills", {})
        )
        results.append(metrics)
        print(f"  Mean latency: {metrics.mean_latency_ms:.2f}ms")
        print(f"  P95 latency: {metrics.p95_latency_ms:.2f}ms")
        print(f"  Throughput: {metrics.requests_per_second:.2f} req/s")
        print()
        
        # Test 2: Sequential requests direct
        print("Test 2: Sequential requests direct (100 requests)")
        metrics = await tester.run_sequential_test(
            "direct_sequential",
            100,
            lambda: tester.call_direct("skills", "list_skills", {})
        )
        results.append(metrics)
        print(f"  Mean latency: {metrics.mean_latency_ms:.2f}ms")
        print(f"  P95 latency: {metrics.p95_latency_ms:.2f}ms")
        print(f"  Throughput: {metrics.requests_per_second:.2f} req/s")
        print()
        
        # Calculate overhead
        gateway_mean = results[0].mean_latency_ms
        direct_mean = results[1].mean_latency_ms
        overhead = gateway_mean - direct_mean
        overhead_percent = (overhead / direct_mean) * 100
        print(f"Gateway overhead: {overhead:.2f}ms ({overhead_percent:.1f}%)")
        print()
        
        # Test 3: Concurrent requests via gateway
        print("Test 3: Concurrent requests via gateway (100 requests, 10 concurrent)")
        metrics = await tester.run_concurrent_test(
            "gateway_concurrent",
            100,
            10,
            lambda: tester.call_via_gateway("skills-mcp", "list_skills", {})
        )
        results.append(metrics)
        print(f"  Mean latency: {metrics.mean_latency_ms:.2f}ms")
        print(f"  P95 latency: {metrics.p95_latency_ms:.2f}ms")
        print(f"  Throughput: {metrics.requests_per_second:.2f} req/s")
        print()
        
        # Test 4: Concurrent requests direct
        print("Test 4: Concurrent requests direct (100 requests, 10 concurrent)")
        metrics = await tester.run_concurrent_test(
            "direct_concurrent",
            100,
            10,
            lambda: tester.call_direct("skills", "list_skills", {})
        )
        results.append(metrics)
        print(f"  Mean latency: {metrics.mean_latency_ms:.2f}ms")
        print(f"  P95 latency: {metrics.p95_latency_ms:.2f}ms")
        print(f"  Throughput: {metrics.requests_per_second:.2f} req/s")
        print()
        
        # Test 5: High concurrency via gateway
        print("Test 5: High concurrency via gateway (200 requests, 50 concurrent)")
        metrics = await tester.run_concurrent_test(
            "gateway_high_concurrency",
            200,
            50,
            lambda: tester.call_via_gateway("skills-mcp", "list_skills", {})
        )
        results.append(metrics)
        print(f"  Mean latency: {metrics.mean_latency_ms:.2f}ms")
        print(f"  P95 latency: {metrics.p95_latency_ms:.2f}ms")
        print(f"  P99 latency: {metrics.p99_latency_ms:.2f}ms")
        print(f"  Throughput: {metrics.requests_per_second:.2f} req/s")
        print(f"  Success rate: {metrics.successful_requests / metrics.total_requests * 100:.1f}%")
        print()
        
        # Save results
        print("=" * 80)
        print("Saving results to gateway_performance_results.json")
        with open("gateway_performance_results.json", "w") as f:
            json.dump([m.to_dict() for m in results], f, indent=2)
        
        print()
        print("Summary:")
        print(f"  Gateway adds ~{overhead:.2f}ms overhead ({overhead_percent:.1f}%)")
        print(f"  Gateway handles high concurrency: {results[4].successful_requests}/{results[4].total_requests} successful")
        print(f"  Gateway throughput: {results[2].requests_per_second:.2f} req/s (concurrent)")
        
    finally:
        await tester.close()


if __name__ == "__main__":
    asyncio.run(main())
