"""Small real MCP server for development evaluations; never deployed."""

import argparse

from mcp.server import MCPServer

server = MCPServer("investigator-fixture")


@server.tool()
def pods_list_in_namespace(namespace: str, labelSelector: str = "") -> str:
    return "NAME                         READY STATUS\ninvestigator-demo-broken     0/1   CreateContainerConfigError\ninvestigator-demo-healthy    1/1   Running"


@server.tool()
def pods_get(name: str, namespace: str) -> str:
    return 'metadata:\n  name: investigator-demo-broken\nstatus:\n  containerStatuses:\n  - state:\n      waiting:\n        reason: CreateContainerConfigError\n        message: configmap "investigator-demo-config" not found'


@server.tool()
def events_list(namespace: str) -> str:
    return 'Warning Failed investigator-demo-broken: configmap "investigator-demo-config" not found'


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    server.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=parser.parse_args().port,
        json_response=True,
        stateless_http=True,
    )
