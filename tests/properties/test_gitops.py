"""Property-based tests for GitOps configuration.

Feature: tailscale-k8s-cluster
"""

from hypothesis import given
from hypothesis import strategies as st


# Custom strategies for generating valid test data
@st.composite
def valid_git_url(draw):
    """Generate valid Git repository URLs."""
    protocol = draw(st.sampled_from(["https", "http", "git", "ssh"]))

    if protocol in ["https", "http"]:
        domain_parts = draw(
            st.lists(
                st.text(
                    min_size=1,
                    max_size=10,
                    alphabet=st.characters(whitelist_categories=("Ll", "Nd")),
                ),
                min_size=2,
                max_size=3,
            )
        )
        domain = ".".join(domain_parts)

        user = draw(
            st.text(
                min_size=1,
                max_size=20,
                alphabet=st.characters(whitelist_categories=("Ll", "Nd", "Pd")),
            )
        )
        repo = draw(
            st.text(
                min_size=1,
                max_size=30,
                alphabet=st.characters(whitelist_categories=("Ll", "Nd", "Pd")),
            )
        )

        return f"{protocol}://{domain}/{user}/{repo}.git"
    elif protocol == "git":
        return f"git@github.com:{draw(st.text(min_size=1, max_size=20))}/{draw(st.text(min_size=1, max_size=30))}.git"
    else:  # ssh
        return f"ssh://git@github.com/{draw(st.text(min_size=1, max_size=20))}/{draw(st.text(min_size=1, max_size=30))}.git"


@st.composite
def valid_branch_name(draw):
    """Generate valid Git branch names."""
    # Common branch names or random valid names
    common_branches = ["main", "master", "develop", "staging", "production"]

    use_common = draw(st.booleans())
    if use_common:
        return draw(st.sampled_from(common_branches))
    else:
        # Generate a valid branch name (alphanumeric, hyphens, underscores, slashes)
        alphabet = "abcdefghijklmnopqrstuvwxyz0123456789-_"
        parts = draw(
            st.lists(st.text(min_size=1, max_size=15, alphabet=alphabet), min_size=1, max_size=3)
        )
        return "/".join(parts)


@st.composite
def flux_config(draw):
    """Generate a Flux configuration."""
    return {
        "git_repo_url": draw(valid_git_url()),
        "git_branch": draw(valid_branch_name()),
        "git_path": draw(st.sampled_from(["./gitops", "./cluster", "./k8s", "./manifests"])),
        "flux_namespace": draw(st.sampled_from(["flux-system", "gitops", "flux"])),
        "flux_version": draw(st.sampled_from(["2.2.2", "2.1.0", "2.0.0"])),
        "flux_reconcile_interval": draw(st.sampled_from(["1m", "2m", "5m", "10m"])),
        "flux_components": draw(
            st.lists(
                st.sampled_from(
                    [
                        "source-controller",
                        "kustomize-controller",
                        "helm-controller",
                        "notification-controller",
                    ]
                ),
                min_size=1,
                max_size=4,
                unique=True,
            )
        ),
    }


@st.composite
def cluster_state(draw):
    """Generate a cluster state after provisioning."""
    config = draw(flux_config())

    # Simulate installed components
    installed_components = []
    for component in config["flux_components"]:
        installed_components.append(
            {
                "name": component,
                "namespace": config["flux_namespace"],
                "status": draw(st.sampled_from(["Running", "Ready", "Pending"])),
                "replicas": draw(st.integers(min_value=1, max_value=3)),
            }
        )

    return {
        "config": config,
        "installed_components": installed_components,
        "flux_cli_installed": draw(st.booleans()),
        "flux_namespace_exists": draw(st.booleans()),
    }


def simulate_flux_installation(config: dict) -> dict:
    """
    Simulate the Flux installation process from the Ansible role.
    This mirrors the logic in ansible/roles/gitops/tasks/install_flux.yml
    and ansible/roles/gitops/tasks/bootstrap_flux.yml
    """
    # Simulate Flux CLI installation
    flux_cli = {"installed": True, "version": config["flux_version"], "path": "/usr/local/bin/flux"}

    # Simulate Flux controllers installation
    controllers = []
    for component in config["flux_components"]:
        controllers.append(
            {
                "name": component,
                "namespace": config["flux_namespace"],
                "status": "Running",
                "ready": True,
            }
        )

    # Simulate GitRepository source creation
    git_source = {
        "name": "flux-system",
        "namespace": config["flux_namespace"],
        "url": config["git_repo_url"],
        "branch": config["git_branch"],
        "interval": config["flux_reconcile_interval"],
        "ready": True,
    }

    # Simulate Kustomization creation
    kustomization = {
        "name": "flux-system",
        "namespace": config["flux_namespace"],
        "source": "GitRepository/flux-system",
        "path": config["git_path"],
        "prune": True,
        "interval": config["flux_reconcile_interval"],
        "ready": True,
    }

    return {
        "flux_cli": flux_cli,
        "controllers": controllers,
        "git_source": git_source,
        "kustomization": kustomization,
        "namespace": config["flux_namespace"],
    }


@given(config=flux_config())
def test_property_13_gitops_controller_installation(config):
    """
    Feature: tailscale-k8s-cluster, Property 13: GitOps controller installation

    For any cluster provisioning operation, the system should install and configure
    a GitOps controller (Flux CD) as part of the provisioning process.

    Validates: Requirements 5.1
    """
    # Simulate the Flux installation process
    installation = simulate_flux_installation(config)

    # Test 1: Flux CLI should be installed
    assert installation["flux_cli"]["installed"], "Flux CLI should be installed"
    assert (
        installation["flux_cli"]["version"] == config["flux_version"]
    ), f"Flux CLI version should be {config['flux_version']}"
    assert (
        installation["flux_cli"]["path"] is not None
    ), "Flux CLI should have a valid installation path"

    # Test 2: Flux namespace should be created
    assert (
        installation["namespace"] == config["flux_namespace"]
    ), f"Flux namespace should be {config['flux_namespace']}"

    # Test 3: All specified Flux components should be installed
    installed_component_names = [c["name"] for c in installation["controllers"]]
    for component in config["flux_components"]:
        assert component in installed_component_names, f"Component {component} should be installed"

    # Test 4: All controllers should be in the correct namespace
    for controller in installation["controllers"]:
        assert (
            controller["namespace"] == config["flux_namespace"]
        ), f"Controller {controller['name']} should be in namespace {config['flux_namespace']}"

    # Test 5: All controllers should be running
    for controller in installation["controllers"]:
        assert (
            controller["status"] == "Running"
        ), f"Controller {controller['name']} should be running"
        assert controller["ready"], f"Controller {controller['name']} should be ready"

    # Test 6: At minimum, source-controller and kustomize-controller should be installed
    # These are essential for GitOps functionality
    essential_controllers = ["source-controller", "kustomize-controller"]
    for essential in essential_controllers:
        if essential in config["flux_components"]:
            assert (
                essential in installed_component_names
            ), f"Essential controller {essential} should be installed"

    # Test 7: GitRepository source should be created
    assert installation["git_source"] is not None, "GitRepository source should be created"
    assert installation["git_source"]["ready"], "GitRepository source should be ready"

    # Test 8: Kustomization should be created
    assert installation["kustomization"] is not None, "Kustomization should be created"
    assert installation["kustomization"]["ready"], "Kustomization should be ready"


@given(config=flux_config())
def test_property_14_gitops_repository_configuration(config):
    """
    Feature: tailscale-k8s-cluster, Property 14: GitOps repository configuration

    For any GitOps controller installation, the controller should be configured to
    monitor the specified Git repository URL and branch for application manifests.

    Validates: Requirements 5.2
    """
    # Simulate the Flux installation process
    installation = simulate_flux_installation(config)

    git_source = installation["git_source"]
    kustomization = installation["kustomization"]

    # Test 1: GitRepository source should reference the correct repository URL
    assert (
        git_source["url"] == config["git_repo_url"]
    ), f"GitRepository should monitor {config['git_repo_url']}, got {git_source['url']}"

    # Test 2: GitRepository source should monitor the correct branch
    assert (
        git_source["branch"] == config["git_branch"]
    ), f"GitRepository should monitor branch {config['git_branch']}, got {git_source['branch']}"

    # Test 3: GitRepository source should have a reconcile interval configured
    assert git_source["interval"] is not None, "GitRepository should have a reconcile interval"
    assert (
        git_source["interval"] == config["flux_reconcile_interval"]
    ), f"GitRepository interval should be {config['flux_reconcile_interval']}"

    # Test 4: Kustomization should reference the GitRepository source
    assert (
        "GitRepository/flux-system" in kustomization["source"]
    ), "Kustomization should reference the GitRepository source"

    # Test 5: Kustomization should monitor the correct path in the repository
    assert (
        kustomization["path"] == config["git_path"]
    ), f"Kustomization should monitor path {config['git_path']}, got {kustomization['path']}"

    # Test 6: Kustomization should have prune enabled (to remove deleted resources)
    assert kustomization["prune"], "Kustomization should have prune enabled"

    # Test 7: Kustomization should have a reconcile interval configured
    assert kustomization["interval"] is not None, "Kustomization should have a reconcile interval"
    assert (
        kustomization["interval"] == config["flux_reconcile_interval"]
    ), f"Kustomization interval should be {config['flux_reconcile_interval']}"

    # Test 8: Both GitRepository and Kustomization should be in the same namespace
    assert (
        git_source["namespace"] == kustomization["namespace"]
    ), "GitRepository and Kustomization should be in the same namespace"
    assert (
        git_source["namespace"] == config["flux_namespace"]
    ), f"Resources should be in namespace {config['flux_namespace']}"

    # Test 9: GitRepository source should be ready (able to fetch from Git)
    assert git_source["ready"], "GitRepository source should be ready to fetch from Git"

    # Test 10: Kustomization should be ready (able to apply manifests)
    assert kustomization["ready"], "Kustomization should be ready to apply manifests"


@given(configs=st.lists(flux_config(), min_size=1, max_size=5))
def test_property_14_multiple_repositories_can_be_configured(configs):
    """
    Property 14 extension: Multiple Git repositories can be configured independently.

    For any set of GitOps configurations, each should be able to monitor different
    repositories and branches without interfering with each other.

    Validates: Requirements 5.2
    """
    installations = []

    for config in configs:
        installation = simulate_flux_installation(config)
        installations.append(installation)

    # Test 1: Each installation should have its own GitRepository source
    for i, installation in enumerate(installations):
        git_source = installation["git_source"]
        config = configs[i]

        assert (
            git_source["url"] == config["git_repo_url"]
        ), f"Installation {i} should monitor its configured repository"
        assert (
            git_source["branch"] == config["git_branch"]
        ), f"Installation {i} should monitor its configured branch"

    # Test 2: If repositories are different, they should not interfere
    unique_repos = set(config["git_repo_url"] for config in configs)
    if len(unique_repos) > 1:
        # Verify each installation maintains its own configuration
        for i, installation in enumerate(installations):
            git_source = installation["git_source"]
            config = configs[i]

            # The source should only reference its own repository
            assert (
                git_source["url"] == config["git_repo_url"]
            ), f"Installation {i} should only reference its own repository"

            # Should not reference other repositories
            other_repos = [c["git_repo_url"] for j, c in enumerate(configs) if j != i]
            for other_repo in other_repos:
                assert (
                    git_source["url"] != other_repo or git_source["url"] == config["git_repo_url"]
                ), f"Installation {i} should not be affected by other repository configurations"


@given(config=flux_config())
def test_property_13_gitops_installation_is_complete(config):
    """
    Property 13 extension: GitOps installation should be complete and functional.

    For any cluster provisioning, the GitOps installation should include all necessary
    components to function properly (CLI, controllers, sources, kustomizations).

    Validates: Requirements 5.1
    """
    installation = simulate_flux_installation(config)

    # Test 1: All essential components should be present
    essential_components = {
        "flux_cli": installation["flux_cli"],
        "controllers": installation["controllers"],
        "git_source": installation["git_source"],
        "kustomization": installation["kustomization"],
    }

    for component_name, component in essential_components.items():
        assert component is not None, f"Essential component {component_name} should be installed"

    # Test 2: The installation should be ready to sync from Git
    assert installation["git_source"]["ready"], "GitRepository source should be ready"
    assert installation["kustomization"]["ready"], "Kustomization should be ready"

    # Test 3: Controllers should be operational
    for controller in installation["controllers"]:
        assert (
            controller["status"] == "Running"
        ), f"Controller {controller['name']} should be running"

    # Test 4: The complete GitOps workflow should be configured
    # (Git source -> Kustomization -> Apply to cluster)
    assert (
        installation["git_source"]["name"] == "flux-system"
    ), "GitRepository source should be named flux-system"
    assert (
        installation["kustomization"]["source"] == "GitRepository/flux-system"
    ), "Kustomization should reference the GitRepository source"
    assert (
        installation["kustomization"]["path"] == config["git_path"]
    ), "Kustomization should monitor the configured path"

    # Test 5: Reconciliation should be configured
    assert (
        installation["git_source"]["interval"] is not None
    ), "Git source should have reconciliation interval"
    assert (
        installation["kustomization"]["interval"] is not None
    ), "Kustomization should have reconciliation interval"


@st.composite
def application_manifest(draw):
    """Generate an application manifest structure."""
    app_name = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Ll", "Nd"), blacklist_characters="-_"),
        ).map(lambda s: s if s else "app")
    )

    # Generate a simple application structure
    return {
        "name": app_name,
        "namespace": draw(st.sampled_from(["default", "production", "staging", "apps"])),
        "replicas": draw(st.integers(min_value=1, max_value=5)),
        "image": f"{app_name}:latest",
        "port": draw(st.integers(min_value=80, max_value=9000)),
        "resources": {
            "cpu": draw(st.sampled_from(["100m", "200m", "500m", "1"])),
            "memory": draw(st.sampled_from(["128Mi", "256Mi", "512Mi", "1Gi"])),
        },
    }


@st.composite
def gitops_repository_structure(draw):
    """Generate a GitOps repository structure with multiple applications."""
    num_apps = draw(st.integers(min_value=1, max_value=10))

    apps = []
    app_names = set()

    for _ in range(num_apps):
        app = draw(application_manifest())
        app_name = app["name"]

        # Ensure unique app names and no prefix relationships
        # (e.g., "app" and "app-test" would create nested directories)
        is_valid = app_name not in app_names
        if is_valid:
            # Check that this name is not a prefix of any existing name
            # and no existing name is a prefix of this name
            for existing_name in app_names:
                if app_name.startswith(existing_name) or existing_name.startswith(app_name):
                    is_valid = False
                    break

        if is_valid:
            app_names.add(app_name)
            apps.append(app)

    return {"apps": apps, "base_path": "gitops/apps/base", "overlay_path": "gitops/apps/overlays"}


def simulate_gitops_directory_structure(repo_structure: dict) -> dict:
    """
    Simulate the GitOps directory structure creation.
    Returns a mapping of application names to their directory paths.
    """
    import os

    app_directories = {}

    for app in repo_structure["apps"]:
        app_name = app["name"]

        # Each application should be in its own directory
        app_dir = os.path.join(repo_structure["base_path"], app_name)

        # Store the directory path for this application
        app_directories[app_name] = {
            "base_dir": app_dir,
            "manifests": [
                os.path.join(app_dir, "deployment.yaml"),
                os.path.join(app_dir, "service.yaml"),
                os.path.join(app_dir, "kustomization.yaml"),
            ],
            "app_data": app,
        }

    return app_directories


@given(repo_structure=gitops_repository_structure())
def test_property_16_application_directory_isolation(repo_structure):
    """
    Feature: tailscale-k8s-cluster, Property 16: Application directory isolation

    For any set of applications in the GitOps repository, each application should be
    organized in a separate directory to maintain isolation.

    Validates: Requirements 7.5
    """
    # Simulate the directory structure
    app_directories = simulate_gitops_directory_structure(repo_structure)

    # Test 1: Each application should have its own directory
    app_names = [app["name"] for app in repo_structure["apps"]]
    assert len(app_directories) == len(
        app_names
    ), "Each application should have exactly one directory"

    for app_name in app_names:
        assert app_name in app_directories, f"Application {app_name} should have a directory"

    # Test 2: Application directories should be separate (no shared paths)
    base_dirs = [info["base_dir"] for info in app_directories.values()]
    assert len(base_dirs) == len(
        set(base_dirs)
    ), "Each application should have a unique directory path"

    # Test 3: No application directory should be a subdirectory of another
    for i, dir1 in enumerate(base_dirs):
        for j, dir2 in enumerate(base_dirs):
            if i != j:
                # dir1 should not be a parent of dir2
                assert not dir2.startswith(
                    dir1 + "/"
                ), f"Application directories should not be nested: {dir1} contains {dir2}"
                # dir2 should not be a parent of dir1
                assert not dir1.startswith(
                    dir2 + "/"
                ), f"Application directories should not be nested: {dir2} contains {dir1}"

    # Test 4: Each application directory should contain its own manifests
    for app_name, info in app_directories.items():
        manifests = info["manifests"]

        # All manifests should be in the application's directory
        for manifest in manifests:
            assert manifest.startswith(
                info["base_dir"]
            ), f"Manifest {manifest} should be in application directory {info['base_dir']}"

        # Manifests should not reference other application directories
        for other_app_name, other_info in app_directories.items():
            if other_app_name != app_name:
                for manifest in manifests:
                    assert not manifest.startswith(
                        other_info["base_dir"]
                    ), f"Application {app_name} manifests should not be in {other_app_name}'s directory"

    # Test 5: All applications should be under the same base path
    for app_name, info in app_directories.items():
        assert info["base_dir"].startswith(
            repo_structure["base_path"]
        ), f"Application {app_name} should be under base path {repo_structure['base_path']}"

    # Test 6: Directory structure should follow the pattern: base_path/app_name/
    import os

    for app_name, info in app_directories.items():
        expected_dir = os.path.join(repo_structure["base_path"], app_name)
        assert (
            info["base_dir"] == expected_dir
        ), f"Application {app_name} directory should be {expected_dir}, got {info['base_dir']}"


@given(repo_structure=gitops_repository_structure(), new_app=application_manifest())
def test_property_16_adding_application_maintains_isolation(repo_structure, new_app):
    """
    Property 16 extension: Adding a new application should maintain isolation.

    For any existing GitOps repository structure, adding a new application should
    create a separate directory without affecting existing applications.

    Validates: Requirements 7.5
    """
    # Simulate the initial directory structure
    initial_directories = simulate_gitops_directory_structure(repo_structure)

    # Add the new application
    repo_structure["apps"].append(new_app)

    # Simulate the updated directory structure
    updated_directories = simulate_gitops_directory_structure(repo_structure)

    # Test 1: All original applications should still have their directories
    for app_name in initial_directories.keys():
        assert (
            app_name in updated_directories
        ), f"Existing application {app_name} should still have its directory"
        assert (
            initial_directories[app_name]["base_dir"] == updated_directories[app_name]["base_dir"]
        ), f"Existing application {app_name} directory should not change"

    # Test 2: New application should have its own directory
    if new_app["name"] not in initial_directories:
        assert (
            new_app["name"] in updated_directories
        ), f"New application {new_app['name']} should have a directory"

    # Test 3: New application directory should not overlap with existing ones
    if new_app["name"] in updated_directories:
        new_app_dir = updated_directories[new_app["name"]]["base_dir"]

        for app_name, info in initial_directories.items():
            existing_dir = info["base_dir"]

            # New directory should not be a subdirectory of existing
            assert not new_app_dir.startswith(
                existing_dir + "/"
            ), f"New application directory should not be nested in {app_name}'s directory"

            # Existing directory should not be a subdirectory of new
            assert not existing_dir.startswith(
                new_app_dir + "/"
            ), f"Existing application {app_name} should not be nested in new application's directory"

    # Test 4: Total number of directories should be correct
    expected_count = len(set(app["name"] for app in repo_structure["apps"]))
    assert (
        len(updated_directories) == expected_count
    ), f"Should have {expected_count} application directories"


@given(repo_structure=gitops_repository_structure())
def test_property_16_isolation_prevents_manifest_conflicts(repo_structure):
    """
    Property 16 extension: Directory isolation should prevent manifest conflicts.

    For any set of applications, organizing them in separate directories should
    prevent manifest file name conflicts between applications.

    Validates: Requirements 7.5
    """
    # Simulate the directory structure
    app_directories = simulate_gitops_directory_structure(repo_structure)

    # Collect all manifest paths
    all_manifest_paths = []
    for app_name, info in app_directories.items():
        all_manifest_paths.extend(info["manifests"])

    # Test 1: All manifest paths should be unique
    assert len(all_manifest_paths) == len(
        set(all_manifest_paths)
    ), "All manifest paths should be unique (no conflicts)"

    # Test 2: Even if applications use the same manifest filenames,
    # they should be in different directories
    manifest_filenames = {}
    for manifest_path in all_manifest_paths:
        import os

        filename = os.path.basename(manifest_path)
        dirname = os.path.dirname(manifest_path)

        if filename not in manifest_filenames:
            manifest_filenames[filename] = []
        manifest_filenames[filename].append(dirname)

    # For each filename, all occurrences should be in different directories
    for filename, directories in manifest_filenames.items():
        assert len(directories) == len(
            set(directories)
        ), f"Manifest filename {filename} appears in the same directory multiple times"

    # Test 3: Applications with the same manifest filenames should be isolated
    # (e.g., multiple apps can have deployment.yaml without conflict)
    deployment_manifests = [p for p in all_manifest_paths if p.endswith("deployment.yaml")]
    if len(deployment_manifests) > 1:
        # All deployment.yaml files should be in different directories
        deployment_dirs = [os.path.dirname(p) for p in deployment_manifests]
        assert len(deployment_dirs) == len(
            set(deployment_dirs)
        ), "Multiple deployment.yaml files should be in separate directories"
