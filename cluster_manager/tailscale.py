"""Tailscale network discovery and management."""

import json
import subprocess

from pydantic import BaseModel, IPvAnyAddress

from cluster_manager.exceptions import TailscaleError
from cluster_manager.logging_config import get_logger

logger = get_logger(__name__)


class TailscaleNode(BaseModel):
    """Represents a node discovered on the Tailscale network."""

    hostname: str
    tailscale_ip: IPvAnyAddress
    online: bool
    os: str | None = None

    def __str__(self) -> str:
        """String representation of the node."""
        status = "online" if self.online else "offline"
        return f"{self.hostname} ({self.tailscale_ip}) - {status}"


class TailscaleDiscovery:
    """Handles discovery of nodes on the Tailscale network."""

    @staticmethod
    def discover_nodes() -> list[TailscaleNode]:
        """
        Query the Tailscale network for available nodes.

        Returns:
            List of TailscaleNode objects representing discovered nodes.

        Raises:
            TailscaleError: If Tailscale is not running or command fails.
        """
        logger.debug("Starting Tailscale node discovery")

        try:
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )

            logger.debug(f"Tailscale status command completed with return code {result.returncode}")

            try:
                status_data = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Tailscale JSON output: {e}")
                raise TailscaleError(
                    "Failed to parse Tailscale status output",
                    "The Tailscale command returned invalid JSON. This may indicate a version mismatch or corrupted output.",
                )

            nodes = []

            # Parse the peer information from Tailscale status
            if "Peer" in status_data:
                logger.debug(f"Found {len(status_data['Peer'])} peers in Tailscale network")

                for peer_id, peer_info in status_data["Peer"].items():
                    try:
                        # Extract hostname (DNSName without the domain suffix)
                        dns_name = peer_info.get("DNSName", "")
                        hostname = (
                            dns_name.split(".")[0]
                            if dns_name
                            else peer_info.get("HostName", "unknown")
                        )

                        # Get the Tailscale IP (first IP in TailscaleIPs list)
                        tailscale_ips = peer_info.get("TailscaleIPs", [])
                        if not tailscale_ips:
                            logger.warning(f"Peer {peer_id} has no Tailscale IPs, skipping")
                            continue

                        tailscale_ip = tailscale_ips[0]

                        # Check if node is online
                        online = peer_info.get("Online", False)

                        # Get OS information
                        os_info = peer_info.get("OS", None)

                        node = TailscaleNode(
                            hostname=hostname, tailscale_ip=tailscale_ip, online=online, os=os_info
                        )
                        nodes.append(node)
                        logger.debug(
                            f"Discovered node: {hostname} ({tailscale_ip}) - {'online' if online else 'offline'}"
                        )

                    except Exception as e:
                        logger.warning(f"Failed to parse peer {peer_id}: {e}")
                        continue

            # Also include self (the current machine)
            if "Self" in status_data:
                try:
                    self_info = status_data["Self"]
                    dns_name = self_info.get("DNSName", "")
                    hostname = (
                        dns_name.split(".")[0]
                        if dns_name
                        else self_info.get("HostName", "localhost")
                    )

                    tailscale_ips = self_info.get("TailscaleIPs", [])
                    if tailscale_ips:
                        node = TailscaleNode(
                            hostname=hostname,
                            tailscale_ip=tailscale_ips[0],
                            online=True,
                            os=self_info.get("OS", None),
                        )
                        nodes.append(node)
                        logger.debug(f"Added self node: {hostname} ({tailscale_ips[0]})")
                except Exception as e:
                    logger.warning(f"Failed to parse self node: {e}")

            logger.info(f"Successfully discovered {len(nodes)} Tailscale nodes")
            return nodes

        except subprocess.TimeoutExpired:
            logger.error("Tailscale command timed out after 10 seconds")
            raise TailscaleError(
                "Tailscale command timed out",
                "The 'tailscale status' command did not respond within 10 seconds. "
                "Check if Tailscale is running: sudo systemctl status tailscaled",
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Tailscale command failed with return code {e.returncode}: {e.stderr}")
            raise TailscaleError(
                "Tailscale command failed",
                f"Command output: {e.stderr}\n\n"
                "Possible causes:\n"
                "1. Tailscale is not authenticated (run: tailscale up)\n"
                "2. Tailscale daemon is not running (run: sudo systemctl start tailscaled)\n"
                "3. Insufficient permissions (try with sudo)",
            )
        except FileNotFoundError:
            logger.error("Tailscale binary not found in PATH")
            raise TailscaleError(
                "Tailscale is not installed or not in PATH",
                "Install Tailscale from https://tailscale.com/download\n"
                "Or ensure the 'tailscale' command is in your PATH",
            )
        except Exception as e:
            logger.error(f"Unexpected error during Tailscale discovery: {e}", exc_info=True)
            raise TailscaleError(
                f"Unexpected error during Tailscale discovery: {e}",
                "Check the logs for more details",
            )

    @staticmethod
    def filter_nodes(
        nodes: list[TailscaleNode], online_only: bool = False, hostname_pattern: str | None = None
    ) -> list[TailscaleNode]:
        """
        Filter discovered nodes based on criteria.

        Args:
            nodes: List of nodes to filter
            online_only: If True, only return online nodes
            hostname_pattern: If provided, only return nodes matching this pattern

        Returns:
            Filtered list of nodes
        """
        filtered = nodes

        if online_only:
            filtered = [n for n in filtered if n.online]

        if hostname_pattern:
            pattern_lower = hostname_pattern.lower()
            filtered = [n for n in filtered if pattern_lower in n.hostname.lower()]

        return filtered
