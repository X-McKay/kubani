"""Agent lifecycle and session operations for Kubani-applied agents.

Every command resolves facts from the committed GitOps tree or from read-only
live objects. Writes are limited to committed files (sync, stage, approve) and
to submitting a session through the tenant's existing Session Runner (run).
No command reads credential material, prints tokens or applies objects.
"""
