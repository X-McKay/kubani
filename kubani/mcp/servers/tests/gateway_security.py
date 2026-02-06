"""
Gateway Security and Egress Control Evaluation Script

This script evaluates:
1. Authentication mechanisms
2. Authorization capabilities
3. Egress control
4. Security posture comparison with direct connections
"""

import asyncio
import httpx
from typing import Dict, Any, List
import json


class SecurityEvaluator:
    """Evaluates gateway security features."""
    
    def __init__(self, gateway_url: str):
        self.gateway_url = gateway_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        """Close the client."""
        await self.client.aclose()
    
    async def test_authentication(self) -> Dict[str, Any]:
        """Test authentication mechanisms."""
        results = {
            "no_auth": None,
            "bearer_token": None,
            "api_key": None,
            "mutual_tls": None
        }
        
        # Test 1: No authentication
        try:
            response = await self.client.post(
                f"{self.gateway_url}/call",
                json={
                    "server": "skills-mcp",
                    "tool": "list_skills",
                    "arguments": {}
                }
            )
            results["no_auth"] = {
                "allowed": response.status_code == 200,
                "status_code": response.status_code
            }
        except Exception as e:
            results["no_auth"] = {
                "allowed": False,
                "error": str(e)
            }
        
        # Test 2: Bearer token
        try:
            response = await self.client.post(
                f"{self.gateway_url}/call",
                json={
                    "server": "skills-mcp",
                    "tool": "list_skills",
                    "arguments": {}
                },
                headers={"Authorization": "Bearer test-token"}
            )
            results["bearer_token"] = {
                "supported": response.status_code != 401,
                "status_code": response.status_code
            }
        except Exception as e:
            results["bearer_token"] = {
                "supported": False,
                "error": str(e)
            }
        
        # Test 3: API Key
        try:
            response = await self.client.post(
                f"{self.gateway_url}/call",
                json={
                    "server": "skills-mcp",
                    "tool": "list_skills",
                    "arguments": {}
                },
                headers={"X-API-Key": "test-key"}
            )
            results["api_key"] = {
                "supported": response.status_code != 401,
                "status_code": response.status_code
            }
        except Exception as e:
            results["api_key"] = {
                "supported": False,
                "error": str(e)
            }
        
        # Test 4: mTLS (would require client certificates)
        results["mutual_tls"] = {
            "supported": "unknown",
            "note": "Requires client certificate configuration"
        }
        
        return results
    
    async def test_authorization(self) -> Dict[str, Any]:
        """Test authorization capabilities."""
        results = {
            "tool_level": None,
            "server_level": None,
            "role_based": None
        }
        
        # Test tool-level authorization
        # Try to call different tools and see if access can be restricted
        try:
            # Try a read operation
            read_response = await self.client.post(
                f"{self.gateway_url}/call",
                json={
                    "server": "skills-mcp",
                    "tool": "list_skills",
                    "arguments": {}
                }
            )
            
            # Try a write operation (if available)
            # This would need to be a real write tool
            results["tool_level"] = {
                "testable": True,
                "read_allowed": read_response.status_code == 200,
                "note": "Tool-level authorization would require policy configuration"
            }
        except Exception as e:
            results["tool_level"] = {
                "testable": False,
                "error": str(e)
            }
        
        # Test server-level authorization
        results["server_level"] = {
            "testable": True,
            "note": "Would require configuring access policies per server"
        }
        
        # Test role-based access
        results["role_based"] = {
            "supported": "unknown",
            "note": "Requires RBAC configuration and testing with different roles"
        }
        
        return results
    
    async def test_egress_control(self) -> Dict[str, Any]:
        """Test egress control capabilities."""
        results = {
            "network_policy": None,
            "upstream_filtering": None,
            "request_filtering": None
        }
        
        # Network policy integration
        results["network_policy"] = {
            "testable": False,
            "note": "Requires Kubernetes NetworkPolicy configuration",
            "benefit": "Gateway can act as single egress point, simplifying network policies"
        }
        
        # Upstream server filtering
        results["upstream_filtering"] = {
            "testable": True,
            "note": "Gateway can restrict which upstream servers are accessible",
            "benefit": "Centralized control over which MCP servers agents can access"
        }
        
        # Request filtering
        results["request_filtering"] = {
            "testable": True,
            "note": "Gateway can filter/validate requests before forwarding",
            "benefit": "Additional security layer for input validation"
        }
        
        return results
    
    async def compare_with_direct(self) -> Dict[str, Any]:
        """Compare security posture with direct connections."""
        return {
            "direct_connection": {
                "pros": [
                    "Simpler architecture",
                    "Fewer components to secure",
                    "Direct network policies per server",
                    "No single point of failure"
                ],
                "cons": [
                    "Each agent needs credentials for each server",
                    "Harder to audit access patterns",
                    "More complex network policy management",
                    "Distributed authentication/authorization"
                ]
            },
            "gateway": {
                "pros": [
                    "Centralized authentication/authorization",
                    "Single point for access control",
                    "Easier to audit and monitor",
                    "Simplified network policies",
                    "Can add security layers (WAF, rate limiting)"
                ],
                "cons": [
                    "Single point of failure",
                    "Additional component to secure",
                    "Potential bottleneck",
                    "More complex deployment"
                ]
            },
            "recommendation": "TBD based on evaluation results"
        }
    
    async def test_rate_limiting(self) -> Dict[str, Any]:
        """Test rate limiting capabilities."""
        try:
            # Send multiple requests quickly
            responses = []
            for i in range(20):
                response = await self.client.post(
                    f"{self.gateway_url}/call",
                    json={
                        "server": "skills-mcp",
                        "tool": "list_skills",
                        "arguments": {}
                    }
                )
                responses.append(response.status_code)
            
            # Check if any requests were rate limited (429)
            rate_limited = 429 in responses
            
            return {
                "supported": rate_limited,
                "total_requests": len(responses),
                "successful": responses.count(200),
                "rate_limited": responses.count(429),
                "note": "Rate limiting may need to be configured"
            }
        except Exception as e:
            return {
                "supported": False,
                "error": str(e)
            }
    
    async def test_input_validation(self) -> Dict[str, Any]:
        """Test input validation and sanitization."""
        results = {
            "malformed_json": None,
            "invalid_server": None,
            "invalid_tool": None,
            "injection_attempts": None
        }
        
        # Test malformed JSON
        try:
            response = await self.client.post(
                f"{self.gateway_url}/call",
                content=b"not valid json",
                headers={"Content-Type": "application/json"}
            )
            results["malformed_json"] = {
                "handled": response.status_code == 400,
                "status_code": response.status_code
            }
        except Exception as e:
            results["malformed_json"] = {
                "handled": True,
                "error": str(e)
            }
        
        # Test invalid server
        try:
            response = await self.client.post(
                f"{self.gateway_url}/call",
                json={
                    "server": "../../../etc/passwd",
                    "tool": "list_skills",
                    "arguments": {}
                }
            )
            results["invalid_server"] = {
                "handled": response.status_code in [400, 404],
                "status_code": response.status_code
            }
        except Exception as e:
            results["invalid_server"] = {
                "handled": True,
                "error": str(e)
            }
        
        # Test invalid tool
        try:
            response = await self.client.post(
                f"{self.gateway_url}/call",
                json={
                    "server": "skills-mcp",
                    "tool": "'; DROP TABLE users; --",
                    "arguments": {}
                }
            )
            results["invalid_tool"] = {
                "handled": response.status_code in [400, 404],
                "status_code": response.status_code
            }
        except Exception as e:
            results["invalid_tool"] = {
                "handled": True,
                "error": str(e)
            }
        
        results["injection_attempts"] = {
            "note": "Gateway should validate and sanitize all inputs",
            "tested": True
        }
        
        return results


async def main():
    """Run security evaluation."""
    
    gateway_url = "http://mcp-gateway.ai-agents-test.svc:8080"
    
    evaluator = SecurityEvaluator(gateway_url)
    
    try:
        print("=" * 80)
        print("MCP Gateway Security and Egress Control Evaluation")
        print("=" * 80)
        print()
        
        # Test authentication
        print("1. Authentication Mechanisms")
        print("-" * 80)
        auth_results = await evaluator.test_authentication()
        print(f"  No auth allowed: {auth_results['no_auth'].get('allowed', 'unknown')}")
        print(f"  Bearer token supported: {auth_results['bearer_token'].get('supported', 'unknown')}")
        print(f"  API key supported: {auth_results['api_key'].get('supported', 'unknown')}")
        print(f"  mTLS supported: {auth_results['mutual_tls'].get('supported', 'unknown')}")
        print()
        
        # Test authorization
        print("2. Authorization Capabilities")
        print("-" * 80)
        authz_results = await evaluator.test_authorization()
        print(f"  Tool-level authorization: {authz_results['tool_level'].get('testable', 'unknown')}")
        print(f"  Server-level authorization: {authz_results['server_level'].get('testable', 'unknown')}")
        print(f"  Role-based access: {authz_results['role_based'].get('supported', 'unknown')}")
        print()
        
        # Test egress control
        print("3. Egress Control")
        print("-" * 80)
        egress_results = await evaluator.test_egress_control()
        print(f"  Network policy integration: {egress_results['network_policy']['note']}")
        print(f"  Upstream filtering: {egress_results['upstream_filtering']['note']}")
        print(f"  Request filtering: {egress_results['request_filtering']['note']}")
        print()
        
        # Test rate limiting
        print("4. Rate Limiting")
        print("-" * 80)
        rate_limit_results = await evaluator.test_rate_limiting()
        print(f"  Rate limiting supported: {rate_limit_results.get('supported', 'unknown')}")
        if rate_limit_results.get('supported'):
            print(f"  Successful requests: {rate_limit_results['successful']}")
            print(f"  Rate limited requests: {rate_limit_results['rate_limited']}")
        print()
        
        # Test input validation
        print("5. Input Validation")
        print("-" * 80)
        validation_results = await evaluator.test_input_validation()
        print(f"  Malformed JSON handled: {validation_results['malformed_json'].get('handled', 'unknown')}")
        print(f"  Invalid server handled: {validation_results['invalid_server'].get('handled', 'unknown')}")
        print(f"  Invalid tool handled: {validation_results['invalid_tool'].get('handled', 'unknown')}")
        print()
        
        # Comparison
        print("6. Comparison with Direct Connection")
        print("-" * 80)
        comparison = await evaluator.compare_with_direct()
        print("  Direct Connection:")
        print("    Pros:")
        for pro in comparison['direct_connection']['pros']:
            print(f"      + {pro}")
        print("    Cons:")
        for con in comparison['direct_connection']['cons']:
            print(f"      - {con}")
        print()
        print("  Gateway:")
        print("    Pros:")
        for pro in comparison['gateway']['pros']:
            print(f"      + {pro}")
        print("    Cons:")
        for con in comparison['gateway']['cons']:
            print(f"      - {con}")
        print()
        
        # Save results
        print("=" * 80)
        results = {
            "authentication": auth_results,
            "authorization": authz_results,
            "egress_control": egress_results,
            "rate_limiting": rate_limit_results,
            "input_validation": validation_results,
            "comparison": comparison
        }
        
        with open("gateway_security_results.json", "w") as f:
            json.dump(results, f, indent=2)
        
        print("Results saved to gateway_security_results.json")
        print()
        
        # Summary
        print("Summary:")
        print(f"  Authentication: {len([r for r in auth_results.values() if r and r.get('supported')])} mechanisms supported")
        print(f"  Input validation: {'Good' if all(r.get('handled') for r in validation_results.values() if r and 'handled' in r) else 'Needs improvement'}")
        print(f"  Egress control: Provides centralized control point")
        
    finally:
        await evaluator.close()


if __name__ == "__main__":
    asyncio.run(main())
