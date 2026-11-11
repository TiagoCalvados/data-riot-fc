"""Limited first-party visitor statistics and labelled sharing links."""
from alembic import op
import sqlalchemy as sa

revision = 'c42d98ac7140'
down_revision = 'b593a23d4012'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('share_links',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('code',sa.String(32),nullable=False,unique=True),
        sa.Column('label',sa.String(120),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.execute("INSERT INTO share_links (id,code,label,created_at) VALUES (0,'direct','Direct / overige links',CURRENT_TIMESTAMP)")
    op.create_table('visitor_days',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('day',sa.Date(),nullable=False),
        sa.Column('visitor_hash',sa.String(64),nullable=False),
        sa.Column('share_link_id',sa.Integer(),sa.ForeignKey('share_links.id'),nullable=False),
        sa.Column('mobile',sa.Boolean(),nullable=False),
        sa.Column('views',sa.Integer(),nullable=False),
        sa.Column('first_seen',sa.DateTime(timezone=True),nullable=False),
        sa.Column('last_seen',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('day','visitor_hash','share_link_id',name='visitor_day_link'))
    op.create_index('ix_visitor_days_day','visitor_days',['day'])
    op.create_index('ix_visitor_days_share_link_id','visitor_days',['share_link_id'])


def downgrade():
    op.drop_table('visitor_days')
    op.drop_table('share_links')
