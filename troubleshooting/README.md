# Troubleshooting Guides

This directory contains detailed troubleshooting guides for issues encountered while operating the Kubani cluster.

Each guide documents:
- Problem symptoms
- Investigation methodology
- Root cause analysis
- Solution and verification steps
- Prevention strategies

## Index

| Issue | Summary |
|-------|---------|
| [Flannel Routes Lost After Tailscale Upgrade](flannel-routes-lost-after-tailscale-upgrade.md) | Pod networking breaks after upgrading Tailscale, causing DNS failures and application crashes |

## Contributing

When adding new troubleshooting guides:

1. Use the existing guides as a template
2. Include the investigation steps you took (helps others learn the debugging process)
3. Document the root cause clearly
4. Provide both immediate fixes and prevention strategies
5. Avoid including sensitive information (IPs, tokens, passwords)
