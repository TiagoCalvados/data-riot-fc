"""Keep fictional staffing separate from parent responses."""
from alembic import op
import sqlalchemy as sa

revision = 'd71e5082f906'
down_revision = 'c42d98ac7140'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('demo_assignments',
        sa.Column('shift_id', sa.Integer(), sa.ForeignKey('shifts.id'), nullable=False),
        sa.Column('person_key', sa.String(100), nullable=False),
        sa.Column('name', sa.String(160), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('shift_id', 'person_key'))


def downgrade():
    op.drop_table('demo_assignments')
