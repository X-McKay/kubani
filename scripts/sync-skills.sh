#!/bin/bash
# Sync skills from filesystem to Qdrant for semantic search.
#
# Usage:
#   ./scripts/sync-skills.sh
#
# Environment variables:
#   QDRANT_HOST - Qdrant server host (default: localhost)
#   QDRANT_PORT - Qdrant server port (default: 6333)
#   EMBEDDINGS_API_URL - Embeddings API URL (default: http://localhost:8001/v1)
#
# This reads all SKILL.md files from skills/ directory,
# generates embeddings, and indexes them in Qdrant.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🔄 Syncing skills to Qdrant..."
echo ""

cd "$PROJECT_ROOT"

# Ensure we're in the virtual environment
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Set defaults if not provided
export QDRANT_HOST="${QDRANT_HOST:-localhost}"
export QDRANT_PORT="${QDRANT_PORT:-6333}"
export EMBEDDINGS_API_URL="${EMBEDDINGS_API_URL:-http://localhost:8001/v1}"

echo "   QDRANT_HOST: $QDRANT_HOST"
echo "   QDRANT_PORT: $QDRANT_PORT"
echo "   EMBEDDINGS_API_URL: $EMBEDDINGS_API_URL"
echo ""

python -c "
import asyncio
import sys
sys.path.insert(0, 'agents/core/src')

from core_agents.skills import get_unified_skill_library

async def main():
    library = await get_unified_skill_library(skills_dir='skills')

    try:
        synced = await library.sync()
        print(f'✅ Synced {len(synced)} skills to Qdrant')
        print()
        for skill_id in synced:
            print(f'   - {skill_id}')
        return 0
    except Exception as e:
        print(f'❌ Error: {e}')
        return 1

exit_code = asyncio.run(main())
sys.exit(exit_code)
"
