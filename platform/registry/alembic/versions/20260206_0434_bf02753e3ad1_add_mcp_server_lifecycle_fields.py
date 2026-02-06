"""add_mcp_server_lifecycle_fields

Revision ID: bf02753e3ad1
Revises: 20260128_0003
Create Date: 2026-02-06 04:34:21.692827+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bf02753e3ad1'
down_revision: Union[str, None] = '20260128_0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new fields to mcp_servers table
    op.add_column('mcp_servers', sa.Column('health_endpoint', sa.String(length=255), nullable=False, server_default='/health'))
    op.add_column('mcp_servers', sa.Column('metrics_endpoint', sa.String(length=255), nullable=False, server_default='/metrics'))
    op.add_column('mcp_servers', sa.Column('last_heartbeat', sa.DateTime(timezone=True), nullable=True))
    op.add_column('mcp_servers', sa.Column('backend_status', sa.dialects.postgresql.JSONB(), nullable=False, server_default='{}'))


def downgrade() -> None:
    # Remove the added fields
    op.drop_column('mcp_servers', 'backend_status')
    op.drop_column('mcp_servers', 'last_heartbeat')
    op.drop_column('mcp_servers', 'metrics_endpoint')
    op.drop_column('mcp_servers', 'health_endpoint')
