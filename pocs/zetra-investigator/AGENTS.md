# Agent development

Keep agent definitions indexed in pyproject.toml. Use a standard ADK LlmAgent with ctx.model, ctx.tools, and ctx.instruction. Classify every tool effect explicitly. Keep package instructions and manifests in the wheel. Run just validate after changes. Fixture evaluation runs trusted host code and cannot qualify sandbox isolation.
