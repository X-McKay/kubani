# Implementation Plan

- [x] 1. Set up project structure and development environment
  - Create directory structure for ansible, CLI, TUI, and GitOps components
  - Initialize pyproject.toml with UV for Python dependencies
  - Create .mise.toml for runtime management (Python, Ansible, kubectl)
  - Set up basic project configuration files
  - _Requirements: 6.1, 6.3, 6.5_

- [x] 2. Implement data models and validation
  - Create Pydantic models for Node, NodeTaint, ClusterState, ClusterConfig
  - Implement serialization methods (to_inventory_dict, from_inventory_dict)
  - Add validation for IP addresses, hostnames, and required fields
  - _Requirements: 3.3, 6.4_

- [x] 2.1 Write property test for node model validation
  - **Property 8: Minimal node definition requirements**
  - **Validates: Requirements 3.3**

- [x] 2.2 Write property test for dependency format
  - **Property 15: Dependency format compliance**
  - **Validates: Requirements 6.4**

- [x] 3. Create Ansible inventory management module
  - Implement inventory parser using ruamel.yaml
  - Create functions to read, update, and write inventory files
  - Add validation for inventory structure and required fields
  - Implement group management (control_plane, workers)
  - _Requirements: 3.1, 3.3, 11.4_

- [x] 3.1 Write property test for inventory updates
  - **Property 20: Inventory update correctness**
  - **Validates: Requirements 11.4**

- [x] 3.2 Write property test for minimal node requirements
  - **Property 8: Minimal node definition requirements**
  - **Validates: Requirements 3.3**

- [x] 4. Implement Ansible role: prerequisites
  - Create role directory structure
  - Write tasks to verify Tailscale installation and authentication
  - Add tasks to install system dependencies (curl, apt-transport-https, etc.)
  - Configure firewall rules for Kubernetes ports
  - Add validation to check Tailscale IP reachability
  - _Requirements: 2.1, 2.4_

- [x] 4.1 Write property test for Tailscale validation
  - **Property 5: Tailscale validation on all nodes**
  - **Validates: Requirements 2.1**

- [x] 4.2 Write property test for node reachability
  - **Property 6: Node reachability validation**
  - **Validates: Requirements 2.4**

- [x] 5. Implement Ansible role: k3s_control_plane
  - Create role directory structure
  - Write tasks to download and install K3s server
  - Configure K3s to use Tailscale IP for API server
  - Generate and save kubeconfig file
  - Extract and store join token for worker nodes
  - Add handlers to restart K3s service
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.2_

- [x] 5.1 Write property test for Tailscale IP configuration
  - **Property 2: Tailscale IP configuration consistency**
  - **Validates: Requirements 1.3, 2.2**

- [x] 5.2 Write property test for credential distribution
  - **Property 3: Credential distribution completeness**
  - **Validates: Requirements 1.4**

- [x] 6. Implement Ansible role: k3s_worker
  - Create role directory structure
  - Write tasks to download and install K3s agent
  - Configure worker to join cluster using control plane Tailscale IP
  - Set up resource reservations (CPU, memory) for local workstation use
  - Apply node labels and taints from inventory
  - Add handlers to restart K3s agent
  - _Requirements: 1.1, 1.2, 3.4, 4.1, 4.2_

- [x] 6.1 Write property test for resource reservations
  - **Property 11: Resource reservation configuration**
  - **Validates: Requirements 4.1**

- [x] 6.2 Write property test for worker node protection
  - **Property 12: Worker node resource protection**
  - **Validates: Requirements 4.2**

- [x] 6.3 Write property test for configuration consistency
  - **Property 9: Configuration consistency across nodes**
  - **Validates: Requirements 3.4**

- [x] 7. Implement Ansible role: gpu_support
  - Create role directory structure with conditional execution
  - Write tasks to install NVIDIA drivers (if not present)
  - Deploy NVIDIA device plugin for Kubernetes
  - Configure GPU time-slicing for sharing
  - Add validation to verify GPU availability
  - _Requirements: 10.1_

- [x] 8. Implement Ansible role: gitops
  - Create role directory structure
  - Write tasks to install Flux CLI
  - Bootstrap Flux to cluster with Git repository configuration
  - Create GitOps directory structure in repository
  - Configure Flux to monitor specified Git repository and branch
  - _Requirements: 5.1, 5.2, 7.5_

- [x] 8.1 Write property test for GitOps installation
  - **Property 13: GitOps controller installation**
  - **Validates: Requirements 5.1**

- [x] 8.2 Write property test for GitOps configuration
  - **Property 14: GitOps repository configuration**
  - **Validates: Requirements 5.2**

- [x] 9. Create main Ansible playbooks
  - Write site.yml as main entry point
  - Create provision_cluster.yml for initial setup
  - Create add_node.yml for adding new nodes
  - Implement error handling and reporting with node and step information
  - Add pre-flight validation checks
  - _Requirements: 1.1, 1.2, 1.5, 3.1, 8.1_

- [x] 9.1 Write property test for complete installation
  - **Property 1: Complete component installation**
  - **Validates: Requirements 1.1, 1.2**

- [x] 9.2 Write property test for error reporting
  - **Property 4: Error reporting completeness**
  - **Validates: Requirements 1.5**

- [x] 9.3 Write property test for consistent provisioning
  - **Property 7: Node addition uses consistent provisioning**
  - **Validates: Requirements 3.1**

- [x] 9.4 Write property test for playbook idempotency
  - **Property 17: Playbook idempotency**
  - **Validates: Requirements 8.1, 8.4**

- [x] 10. Implement node-specific configuration logic
  - Create Ansible tasks to detect node hardware capabilities
  - Implement conditional logic for GPU nodes (device plugin installation)
  - Add storage class configuration based on node attributes
  - Apply custom labels and taints from inventory
  - Configure resource limits for resource-constrained nodes
  - _Requirements: 10.1, 10.2, 10.3, 10.5_

- [x] 10.1 Write property test for node-specific configuration
  - **Property 18: Node-specific configuration application**
  - **Validates: Requirements 10.1, 10.2, 10.3, 10.5**

- [x] 11. Implement CLI: Tailscale discovery
  - Create CLI module structure with Typer
  - Implement discover command that queries Tailscale network
  - Parse Tailscale status JSON output
  - Display discovered nodes with hostname, IP, and cluster status
  - Add filtering options for discovered nodes
  - _Requirements: 11.2, 11.3_

- [x] 11.1 Write property test for Tailscale discovery
  - **Property 19: Tailscale node discovery**
  - **Validates: Requirements 11.2, 11.3**

- [x] 12. Implement CLI: Node management commands
  - Create add_node command with validation
  - Implement remove_node command with optional drain
  - Add node information to inventory in correct format
  - Validate node configuration before writing
  - Handle duplicate nodes and conflicts
  - _Requirements: 11.4, 11.5_

- [x] 12.1 Write property test for inventory updates
  - **Property 20: Inventory update correctness**
  - **Validates: Requirements 11.4**

- [x] 12.2 Write property test for configuration validation
  - **Property 21: Configuration validation before write**
  - **Validates: Requirements 11.5**

- [x] 13. Implement CLI: Configuration management
  - Create config_set command for updating variables
  - Implement config_get command for retrieving values
  - Add scope support (all, control_plane, workers)
  - Validate configuration changes against schema
  - Support for nested configuration keys
  - _Requirements: 11.1, 11.5_

- [x] 13.1 Write property test for configuration validation
  - **Property 21: Configuration validation before write**
  - **Validates: Requirements 11.5**

- [x] 14. Implement CLI: Cluster operations
  - Create provision command that executes Ansible playbooks
  - Implement status command showing cluster health
  - Add support for Ansible tags and check mode
  - Integrate with ansible-runner for playbook execution
  - Display progress and results
  - _Requirements: 11.1_

- [x] 15. Implement TUI: Main application structure
  - Create Textual app with main layout
  - Implement header with cluster name and keyboard shortcuts
  - Create three main sections: Nodes, Services, Events
  - Set up keyboard event handlers
  - Configure auto-refresh timer
  - _Requirements: 12.1, 12.5_

- [x] 15.1 Write property test for keyboard navigation
  - **Property 25: TUI keyboard navigation**
  - **Validates: Requirements 12.5**

- [x] 16. Implement TUI: Node display widget
  - Create table widget for node information
  - Fetch node data from Kubernetes API
  - Display role, status, CPU, memory, Tailscale IP
  - Add color coding for node status (Ready=green, NotReady=red)
  - Implement detail view on selection
  - _Requirements: 12.1, 12.2_

- [x] 16.1 Write property test for node information display
  - **Property 22: TUI node information completeness**
  - **Validates: Requirements 12.1, 12.2**

- [x] 17. Implement TUI: Service display widget
  - Create table widget for service information
  - Fetch pod and service data from Kubernetes API
  - Display namespace, name, pod count, health status
  - Add color coding for health status
  - Implement detail view on selection
  - _Requirements: 12.3_

- [x] 17.1 Write property test for service information display
  - **Property 23: TUI service information completeness**
  - **Validates: Requirements 12.3**

- [x] 18. Implement TUI: Auto-refresh and state synchronization
  - Set up periodic refresh using Textual timers
  - Implement Kubernetes API watch for real-time updates
  - Update display when cluster state changes
  - Handle API connection errors gracefully
  - Show loading indicators during refresh
  - _Requirements: 12.4_

- [x] 18.1 Write property test for state synchronization
  - **Property 24: TUI state synchronization**
  - **Validates: Requirements 12.4**

- [x] 19. Create GitOps repository structure and templates
  - Create gitops/ directory with flux-system, infrastructure, apps
  - Add Kustomization templates for applications
  - Create example application manifests (Deployment, Service, Ingress)
  - Add templates for ConfigMaps and Secrets
  - Organize applications in separate directories
  - Document GitOps workflow in README
  - _Requirements: 7.1, 7.3, 7.4, 7.5_

- [x] 19.1 Write property test for application isolation
  - **Property 16: Application directory isolation**
  - **Validates: Requirements 7.5**

- [x] 20. Create comprehensive documentation
  - Write main README with setup instructions and prerequisites
  - Create example inventory files with detailed comments
  - Document all CLI commands with examples
  - Add troubleshooting guide with common issues
  - Document architecture and component interactions
  - Create quickstart guide
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 21. Implement error handling across all components
  - Add try-catch blocks with specific error messages
  - Implement validation with helpful error messages
  - Add logging throughout CLI and TUI
  - Create error recovery procedures in Ansible
  - Test error scenarios and improve messages
  - _Requirements: 1.5_

- [x] 22. Set up development tooling
  - Configure pytest for unit testing
  - Set up Hypothesis for property-based testing
  - Add pytest-cov for coverage reporting
  - Create pre-commit hooks for linting
  - Configure ruff for Python linting
  - Add ty for type checking
  - _Requirements: 6.1_

- [x] 23. Create example configurations and quickstart
  - Create example hosts.yml with multiple node types
  - Add example group_vars with common configurations
  - Create quickstart script for first-time setup
  - Add example GitOps applications
  - Document GPU node configuration
  - _Requirements: 9.2, 9.3_

- [x] 24. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise
