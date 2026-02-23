# Development Workflow Rule

When making code changes that will be deployed:

1. **Always test locally first** before building containers
   - Use egress config (`config/local.yaml` or `.env`) to test against cluster services
   - Run `just test-unit` and `just lint` before proceeding
   - For prompt/behavior changes: run the agent locally and verify the change works

2. **Build and test containers before pushing**
   - Run `just build <agent>` and verify it completes
   - Run a smoke test on the built image
   - Only push after confirming the container starts correctly

3. **Validate after deployment**
   - Check pod status (no CrashLoopBackOff)
   - Review logs for errors
   - Send a test interaction to verify functionality

4. **Never skip stages** to "save time" — catching issues locally is always faster than debugging in production
