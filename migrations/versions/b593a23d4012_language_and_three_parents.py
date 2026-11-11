"""Parent language preference and three-person staffing."""
from alembic import op
import sqlalchemy as sa

revision = 'b593a23d4012'
down_revision = 'a43119abe82d'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('language', sa.String(2), nullable=False, server_default='nl'))
    op.execute('UPDATE planning_policies SET volunteers_per_shift = 3')
    op.execute("UPDATE shifts SET capacity = 3 WHERE state = 'open' AND ends_at > CURRENT_TIMESTAMP")


def downgrade():
    op.drop_column('users', 'language')
