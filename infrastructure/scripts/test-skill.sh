#!/bin/bash
# Test a single skill locally using the LocalRunner.
#
# Usage:
#   ./scripts/test-skill.sh k8s/remediation/restart-crashloop
#
# This runs the test scenarios defined in the skill's test.yaml file
# using mocked MCP tools.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SKILL_PATH="${1:-k8s/remediation/restart-crashloop}"

echo "🧪 Testing skill: $SKILL_PATH"
echo ""

cd "$PROJECT_ROOT"

# Ensure we're in the virtual environment
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

python -c "
import asyncio
import sys
sys.path.insert(0, 'agents/core/src')

from core_agents.skills import test_skill

async def main():
    result = await test_skill('$SKILL_PATH', skills_dir='skills')

    if 'error' in result and result.get('total', 0) == 0:
        print(f\"❌ Error: {result['error']}\")
        return 1

    print(f\"📊 Results: {result['passed']}/{result['total']} passed\")
    print()

    for t in result.get('results', []):
        status = '✅' if t['passed'] else '❌'
        print(f\"   {status} {t['name']}\")
        if t.get('error'):
            print(f\"      Error: {t['error']}\")

    print()
    return 0 if result['failed'] == 0 else 1

exit_code = asyncio.run(main())
sys.exit(exit_code)
"
