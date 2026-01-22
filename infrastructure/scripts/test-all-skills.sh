#!/bin/bash
# Test all skills in the skills/ directory.
#
# Usage:
#   ./scripts/test-all-skills.sh
#
# Runs test scenarios for all skills and reports summary.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🧪 Testing all skills..."
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

from core_agents.skills import test_all_skills

async def main():
    result = await test_all_skills('skills')

    print(f\"📊 Summary: {result['total_passed']} passed, {result['total_failed']} failed\")
    print(f\"   Skills tested: {result['skills_tested']}\")
    print()

    for skill_result in result['results']:
        if skill_result['failed'] > 0:
            print(f\"   ❌ {skill_result['skill']}: {skill_result['passed']}/{skill_result['total']} passed\")
        else:
            print(f\"   ✅ {skill_result['skill']}: {skill_result['passed']}/{skill_result['total']} passed\")

    print()
    return 0 if result['total_failed'] == 0 else 1

exit_code = asyncio.run(main())
sys.exit(exit_code)
"
