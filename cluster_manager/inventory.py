"""Ansible inventory management module.

This module provides functions to read, update, and write Ansible inventory files
using ruamel.yaml for preserving comments and formatting.
"""

from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from cluster_manager.exceptions import ClusterManagerError
from cluster_manager.logging_config import get_logger
from cluster_manager.models.node import Node

logger = get_logger(__name__)


class InventoryError(ClusterManagerError):
    """Base exception for inventory operations."""

    pass


class InventoryValidationError(InventoryError):
    """Exception raised when inventory validation fails."""

    pass


class InventoryManager:
    """Manager for Ansible inventory operations."""

    def __init__(self, inventory_path: str | Path):
        """Initialize inventory manager.

        Args:
            inventory_path: Path to the Ansible inventory file
        """
        self.inventory_path = Path(inventory_path)
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.default_flow_style = False
        self.yaml.indent(mapping=2, sequence=2, offset=0)

    def read(self) -> dict:
        """Read inventory file and return parsed data.

        Returns:
            Dictionary containing inventory data

        Raises:
            InventoryError: If file cannot be read or parsed
        """
        logger.debug(f"Reading inventory file: {self.inventory_path}")

        if not self.inventory_path.exists():
            logger.error(f"Inventory file not found: {self.inventory_path}")
            raise InventoryError(
                f"Inventory file not found: {self.inventory_path}\n\n"
                f"Expected location: {self.inventory_path.absolute()}\n"
                f"Create the file or specify a different path with --inventory"
            )

        try:
            with open(self.inventory_path) as f:
                data = self.yaml.load(f)

            if data is None:
                logger.error("Inventory file is empty")
                raise InventoryError(
                    "Inventory file is empty\n\n"
                    "The inventory file exists but contains no data. "
                    "See ansible/inventory/hosts.yml.example for a template."
                )

            logger.debug(f"Successfully read inventory with {len(data)} top-level keys")
            return data

        except InventoryError:
            raise
        except Exception as e:
            logger.error(f"Failed to read inventory file: {e}", exc_info=True)
            raise InventoryError(
                f"Failed to read inventory file: {e}\n\n"
                f"The file may be corrupted or have invalid YAML syntax. "
                f"Check the file at: {self.inventory_path.absolute()}"
            )

    def write(self, data: dict) -> None:
        """Write inventory data to file.

        Args:
            data: Dictionary containing inventory data

        Raises:
            InventoryError: If file cannot be written
        """
        logger.debug(f"Writing inventory file: {self.inventory_path}")

        try:
            # Ensure parent directory exists
            self.inventory_path.parent.mkdir(parents=True, exist_ok=True)

            # Create backup of existing file
            if self.inventory_path.exists():
                backup_path = self.inventory_path.with_suffix(".yml.backup")
                logger.debug(f"Creating backup at: {backup_path}")
                import shutil

                shutil.copy2(self.inventory_path, backup_path)

            with open(self.inventory_path, "w") as f:
                self.yaml.dump(data, f)

            logger.info(f"Successfully wrote inventory file: {self.inventory_path}")

        except PermissionError as e:
            logger.error(f"Permission denied writing inventory file: {e}")
            raise InventoryError(
                f"Permission denied writing inventory file: {self.inventory_path}\n\n"
                f"Check file permissions or try running with appropriate privileges"
            )
        except OSError as e:
            logger.error(f"OS error writing inventory file: {e}")
            raise InventoryError(
                f"Failed to write inventory file: {e}\n\n"
                f"Check disk space and file system permissions"
            )
        except Exception as e:
            logger.error(f"Unexpected error writing inventory file: {e}", exc_info=True)
            raise InventoryError(
                f"Failed to write inventory file: {e}\n\n"
                f"An unexpected error occurred. Check the logs for details."
            )

    def validate(self, data: dict) -> None:
        """Validate inventory structure and required fields.

        Args:
            data: Dictionary containing inventory data

        Raises:
            InventoryValidationError: If validation fails
        """
        # Check top-level structure
        if not isinstance(data, dict):
            raise InventoryValidationError("Inventory must be a dictionary")

        if "all" not in data:
            raise InventoryValidationError("Inventory must have 'all' group")

        all_group = data["all"]
        if not isinstance(all_group, dict):
            raise InventoryValidationError("'all' group must be a dictionary")

        # Check for children groups
        if "children" not in all_group:
            raise InventoryValidationError("'all' group must have 'children'")

        children = all_group["children"]
        if not isinstance(children, dict):
            raise InventoryValidationError("'children' must be a dictionary")

        # Validate control_plane and workers groups exist
        required_groups = ["control_plane", "workers"]
        for group in required_groups:
            if group not in children:
                raise InventoryValidationError(f"Missing required group: {group}")

            group_data = children[group]
            if not isinstance(group_data, dict):
                raise InventoryValidationError(f"Group '{group}' must be a dictionary")

            # Check hosts structure
            if "hosts" in group_data:
                hosts = group_data["hosts"]
                if not isinstance(hosts, dict):
                    raise InventoryValidationError(
                        f"'hosts' in group '{group}' must be a dictionary"
                    )

                # Validate each host
                for hostname, host_data in hosts.items():
                    self._validate_host(hostname, host_data, group)

    def _validate_host(self, hostname: str, host_data: dict, group: str) -> None:
        """Validate a single host entry.

        Args:
            hostname: The hostname
            host_data: Host configuration data
            group: The group name (for error messages)

        Raises:
            InventoryValidationError: If host validation fails
        """
        if not isinstance(host_data, dict):
            raise InventoryValidationError(
                f"Host '{hostname}' in group '{group}' must be a dictionary"
            )

        # Check required fields
        required_fields = ["ansible_host", "tailscale_ip"]
        for field in required_fields:
            if field not in host_data:
                raise InventoryValidationError(
                    f"Host '{hostname}' in group '{group}' missing required field: {field}"
                )

        # Validate using Node model
        try:
            role = "control-plane" if group == "control_plane" else "worker"
            Node.from_inventory_dict(hostname, {**host_data, "role": role})
        except Exception as e:
            raise InventoryValidationError(
                f"Host '{hostname}' in group '{group}' validation failed: {e}"
            )

    def get_nodes(self, group: str | None = None) -> list[Node]:
        """Get all nodes from inventory, optionally filtered by group.

        Args:
            group: Optional group name ('control_plane' or 'workers')

        Returns:
            List of Node objects

        Raises:
            InventoryError: If inventory cannot be read or parsed
        """
        data = self.read()
        self.validate(data)

        nodes = []
        children = data["all"]["children"]

        groups_to_process = [group] if group else ["control_plane", "workers"]

        for group_name in groups_to_process:
            if group_name not in children:
                continue

            group_data = children[group_name]
            if "hosts" not in group_data:
                continue

            role = "control-plane" if group_name == "control_plane" else "worker"

            for hostname, host_data in group_data["hosts"].items():
                node = Node.from_inventory_dict(hostname, {**host_data, "role": role})
                nodes.append(node)

        return nodes

    def add_node(self, node: Node) -> None:
        """Add a node to the inventory.

        Args:
            node: Node object to add

        Raises:
            InventoryError: If node already exists or operation fails
        """
        logger.info(f"Adding node '{node.hostname}' to inventory")

        data = self.read()
        self.validate(data)

        # Determine target group
        group = "control_plane" if node.role == "control-plane" else "workers"
        logger.debug(f"Node will be added to group: {group}")

        # Check if node already exists
        existing_nodes = self.get_nodes()
        if any(n.hostname == node.hostname for n in existing_nodes):
            logger.error(f"Node '{node.hostname}' already exists in inventory")
            raise InventoryError(
                f"Node '{node.hostname}' already exists in inventory\n\n"
                f"Use 'cluster-mgr remove-node {node.hostname}' to remove it first, "
                f"or use a different hostname"
            )

        # Check for IP conflicts
        if any(n.tailscale_ip == node.tailscale_ip for n in existing_nodes):
            logger.error(f"Tailscale IP '{node.tailscale_ip}' already in use")
            raise InventoryError(
                f"Tailscale IP '{node.tailscale_ip}' is already in use by another node\n\n"
                f"Each node must have a unique Tailscale IP address"
            )

        # Ensure group structure exists
        children = data["all"]["children"]
        if group not in children:
            logger.debug(f"Creating new group: {group}")
            children[group] = CommentedMap()

        if "hosts" not in children[group]:
            logger.debug(f"Creating hosts section in group: {group}")
            children[group]["hosts"] = CommentedMap()

        # Add node
        children[group]["hosts"][node.hostname] = node.to_inventory_dict()
        logger.debug(f"Node '{node.hostname}' added to inventory data structure")

        # Write updated inventory
        self.write(data)
        logger.info(f"Successfully added node '{node.hostname}' to inventory")

    def remove_node(self, hostname: str) -> None:
        """Remove a node from the inventory.

        Args:
            hostname: Hostname of the node to remove

        Raises:
            InventoryError: If node not found or operation fails
        """
        data = self.read()
        self.validate(data)

        children = data["all"]["children"]
        found = False

        # Search in both groups
        for group in ["control_plane", "workers"]:
            if group in children and "hosts" in children[group]:
                if hostname in children[group]["hosts"]:
                    del children[group]["hosts"][hostname]
                    found = True
                    break

        if not found:
            raise InventoryError(f"Node '{hostname}' not found in inventory")

        # Write updated inventory
        self.write(data)

    def update_node(self, node: Node) -> None:
        """Update an existing node in the inventory.

        Args:
            node: Node object with updated data

        Raises:
            InventoryError: If node not found or operation fails
        """
        data = self.read()
        self.validate(data)

        children = data["all"]["children"]
        found = False

        # Search in both groups
        for group in ["control_plane", "workers"]:
            if group in children and "hosts" in children[group]:
                if node.hostname in children[group]["hosts"]:
                    # Check if role changed (requires moving to different group)
                    current_role = "control-plane" if group == "control_plane" else "worker"
                    if current_role != node.role:
                        # Remove from current group
                        del children[group]["hosts"][node.hostname]
                        # Add to new group
                        new_group = "control_plane" if node.role == "control-plane" else "workers"
                        if new_group not in children:
                            children[new_group] = CommentedMap()
                        if "hosts" not in children[new_group]:
                            children[new_group]["hosts"] = CommentedMap()
                        children[new_group]["hosts"][node.hostname] = node.to_inventory_dict()
                    else:
                        # Update in place
                        children[group]["hosts"][node.hostname] = node.to_inventory_dict()
                    found = True
                    break

        if not found:
            raise InventoryError(f"Node '{node.hostname}' not found in inventory")

        # Write updated inventory
        self.write(data)

    def get_vars(self, scope: str = "all") -> dict:
        """Get variables for a specific scope.

        Args:
            scope: Variable scope ('all', 'control_plane', or 'workers')

        Returns:
            Dictionary of variables

        Raises:
            InventoryError: If scope not found
        """
        data = self.read()

        if scope == "all":
            return data.get("all", {}).get("vars", {})
        else:
            children = data.get("all", {}).get("children", {})
            if scope not in children:
                raise InventoryError(f"Scope '{scope}' not found in inventory")
            return children[scope].get("vars", {})

    def set_var(self, key: str, value: any, scope: str = "all") -> None:
        """Set a variable in the inventory.

        Args:
            key: Variable name
            value: Variable value
            scope: Variable scope ('all', 'control_plane', or 'workers')

        Raises:
            InventoryError: If operation fails
        """
        data = self.read()

        if scope == "all":
            if "vars" not in data["all"]:
                data["all"]["vars"] = CommentedMap()
            data["all"]["vars"][key] = value
        else:
            children = data["all"]["children"]
            if scope not in children:
                raise InventoryError(f"Scope '{scope}' not found in inventory")
            if "vars" not in children[scope]:
                children[scope]["vars"] = CommentedMap()
            children[scope]["vars"][key] = value

        self.write(data)
