"""Users, consents and contributions for voluntary recordings.

Revision ID: 0001
Revises: 
Create Date: 2026-09-18 05:12:29.564235
"""

from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('google_sub', sa.String(length=255), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_google_sub'), 'users', ['google_sub'], unique=True)
    op.create_table('consents',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.String(length=32), nullable=False),
    sa.Column('adult_confirmed', sa.Boolean(), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_consents_user_id'), 'consents', ['user_id'], unique=False)
    op.create_table('contributions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('consent_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('audio_key', sa.String(length=512), nullable=False),
    sa.Column('audio_bytes', sa.Integer(), nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=False),
    sa.Column('heard_text', sa.Text(), nullable=False),
    sa.Column('confirmed_text', sa.Text(), nullable=False),
    sa.Column('label_source', sa.String(length=16), nullable=False),
    sa.Column('exact', sa.Boolean(), nullable=False),
    sa.Column('stt_model', sa.String(length=64), nullable=False),
    sa.Column('interpret_model', sa.String(length=64), nullable=False),
    sa.Column('app_version', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['consent_id'], ['consents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_contributions_user_id'), 'contributions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_contributions_user_id'), table_name='contributions')
    op.drop_table('contributions')
    op.drop_index(op.f('ix_consents_user_id'), table_name='consents')
    op.drop_table('consents')
    op.drop_index(op.f('ix_users_google_sub'), table_name='users')
    op.drop_table('users')
