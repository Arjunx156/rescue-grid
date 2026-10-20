"""initial schema

Revision ID: 2eb172e27de0
Revises:
Create Date: 2026-10-20 01:01:25.391033

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2eb172e27de0'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for ext in ("postgis", "vector", "pgcrypto"):
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {ext}")
    op.create_table('organizations',
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('type', sa.String(length=16), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_organizations'))
    )
    op.create_table('replay_datasets',
    sa.Column('slug', sa.String(length=64), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.Column('message_count', sa.Integer(), nullable=False),
    sa.Column('file_path', sa.Text(), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_replay_datasets')),
    sa.UniqueConstraint('slug', name=op.f('uq_replay_datasets_slug'))
    )
    op.create_geospatial_table('disasters',
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('area', Geometry(geometry_type='MULTIPOLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('replay_dataset_id', sa.UUID(), nullable=True),
    sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('purged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['replay_dataset_id'], ['replay_datasets.id'], name=op.f('fk_disasters_replay_dataset_id_replay_datasets')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_disasters'))
    )
    op.create_geospatial_index('ix_disasters_area', 'disasters', ['area'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_table('users',
    sa.Column('email', sa.Text(), nullable=True),
    sa.Column('phone', sa.Text(), nullable=True),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=True),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=True),
    sa.Column('preferred_language', sa.String(length=4), server_default='en', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_users_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email')),
    sa.UniqueConstraint('phone', name=op.f('uq_users_phone'))
    )
    op.create_table('disaster_organizations',
    sa.Column('disaster_id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['disaster_id'], ['disasters.id'], name=op.f('fk_disaster_organizations_disaster_id_disasters'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_disaster_organizations_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('disaster_id', 'organization_id', name=op.f('pk_disaster_organizations'))
    )
    op.create_table('dispatch_plans',
    sa.Column('disaster_id', sa.UUID(), nullable=False),
    sa.Column('created_by', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('objective_value', sa.Float(), nullable=True),
    sa.Column('solver_ms', sa.Integer(), nullable=True),
    sa.Column('stats', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('approved_by', sa.UUID(), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['approved_by'], ['users.id'], name=op.f('fk_dispatch_plans_approved_by_users')),
    sa.ForeignKeyConstraint(['disaster_id'], ['disasters.id'], name=op.f('fk_dispatch_plans_disaster_id_disasters'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_dispatch_plans'))
    )
    op.create_index('ix_dispatch_plans_disaster', 'dispatch_plans', ['disaster_id', 'status'], unique=False)
    op.create_geospatial_table('flood_zones',
    sa.Column('disaster_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.Text(), nullable=True),
    sa.Column('geom', Geometry(geometry_type='MULTIPOLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('depth_estimate_m', sa.Numeric(precision=4, scale=2), nullable=True),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('valid_from', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['disaster_id'], ['disasters.id'], name=op.f('fk_flood_zones_disaster_id_disasters'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_flood_zones'))
    )
    op.create_index('ix_flood_zones_disaster', 'flood_zones', ['disaster_id'], unique=False)
    op.create_geospatial_index('ix_flood_zones_geom', 'flood_zones', ['geom'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_table('invites',
    sa.Column('email', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.Text(), nullable=False),
    sa.Column('invited_by', sa.UUID(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['invited_by'], ['users.id'], name=op.f('fk_invites_invited_by_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_invites_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_invites')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_invites_token_hash'))
    )
    op.create_index(op.f('ix_invites_email'), 'invites', ['email'], unique=False)
    op.create_table('push_subscriptions',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('endpoint', sa.Text(), nullable=False),
    sa.Column('p256dh', sa.Text(), nullable=False),
    sa.Column('auth', sa.Text(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_push_subscriptions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_push_subscriptions')),
    sa.UniqueConstraint('endpoint', name=op.f('uq_push_subscriptions_endpoint'))
    )
    op.create_index(op.f('ix_push_subscriptions_user_id'), 'push_subscriptions', ['user_id'], unique=False)
    op.create_geospatial_table('teams',
    sa.Column('disaster_id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=True),
    sa.Column('call_sign', sa.String(length=16), nullable=False),
    sa.Column('asset_type', sa.String(length=12), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('lead_user_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=12), server_default='off_duty', nullable=False),
    sa.Column('current_location', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('heading', sa.Float(), nullable=True),
    sa.Column('location_updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('base_location', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('base_name', sa.Text(), nullable=True),
    sa.Column('is_virtual', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['disaster_id'], ['disasters.id'], name=op.f('fk_teams_disaster_id_disasters'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lead_user_id'], ['users.id'], name=op.f('fk_teams_lead_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_teams_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_teams')),
    sa.UniqueConstraint('disaster_id', 'call_sign', name='uq_teams_disaster_call_sign')
    )
    op.create_index('ix_teams_lead', 'teams', ['lead_user_id'], unique=False)
    op.create_geospatial_index('ix_teams_location', 'teams', ['current_location'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_table('user_sessions',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('refresh_hash', sa.Text(), nullable=False),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_sessions')),
    sa.UniqueConstraint('refresh_hash', name=op.f('uq_user_sessions_refresh_hash'))
    )
    op.create_index(op.f('ix_user_sessions_user_id'), 'user_sessions', ['user_id'], unique=False)
    op.create_geospatial_table('cases',
    sa.Column('disaster_id', sa.UUID(), nullable=False),
    sa.Column('tracking_code', sa.String(length=12), nullable=False),
    sa.Column('location', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('location_confidence', sa.Float(), server_default='0', nullable=False),
    sa.Column('location_source', sa.String(length=16), server_default='unknown', nullable=False),
    sa.Column('location_candidates', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('address_text', sa.Text(), nullable=True),
    sa.Column('locality', sa.Text(), nullable=True),
    sa.Column('people_count', sa.Integer(), nullable=True),
    sa.Column('vulnerability', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('needs', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
    sa.Column('water_level', sa.String(length=16), nullable=True),
    sa.Column('water_rising', sa.Boolean(), nullable=True),
    sa.Column('in_flood_zone', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('flood_depth_m', sa.Float(), nullable=True),
    sa.Column('urgency_score', sa.Integer(), server_default='0', nullable=False),
    sa.Column('urgency_level', sa.String(length=12), server_default='low', nullable=False),
    sa.Column('score_breakdown', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='new', nullable=False),
    sa.Column('review_reasons', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
    sa.Column('merged_into_id', sa.UUID(), nullable=True),
    sa.Column('contact_phone', sa.Text(), nullable=True),
    sa.Column('contact_phone_hashes', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
    sa.Column('contact_name', sa.Text(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('language', sa.String(length=8), nullable=True),
    sa.Column('first_reported_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_reported_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('source_count', sa.Integer(), server_default='1', nullable=False),
    sa.Column('current_team_id', sa.UUID(), nullable=True),
    sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rescued_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('people_rescued', sa.Integer(), nullable=True),
    sa.Column('embedding', Vector(768), nullable=True),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['current_team_id'], ['teams.id'], name=op.f('fk_cases_current_team_id_teams')),
    sa.ForeignKeyConstraint(['disaster_id'], ['disasters.id'], name=op.f('fk_cases_disaster_id_disasters'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['merged_into_id'], ['cases.id'], name=op.f('fk_cases_merged_into_id_cases')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cases')),
    sa.UniqueConstraint('tracking_code', name=op.f('uq_cases_tracking_code'))
    )
    op.create_index('ix_cases_disaster_updated', 'cases', ['disaster_id', 'updated_at'], unique=False)
    op.create_geospatial_index('ix_cases_location', 'cases', ['location'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_index('ix_cases_queue', 'cases', ['disaster_id', 'status', sa.literal_column('urgency_score DESC')], unique=False)
    op.create_geospatial_table('team_locations',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('team_id', sa.UUID(), nullable=False),
    sa.Column('location', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('speed', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], name=op.f('fk_team_locations_team_id_teams'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_team_locations'))
    )
    op.create_geospatial_index('ix_team_locations_location', 'team_locations', ['location'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_index('ix_team_locations_team_time', 'team_locations', ['team_id', sa.literal_column('recorded_at DESC')], unique=False)
    op.create_geospatial_table('assignments',
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('team_id', sa.UUID(), nullable=False),
    sa.Column('plan_id', sa.UUID(), nullable=True),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('route', Geometry(geometry_type='LINESTRING', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('route_source', sa.String(length=12), nullable=True),
    sa.Column('distance_m', sa.Integer(), nullable=True),
    sa.Column('travel_s', sa.Integer(), nullable=True),
    sa.Column('eta', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('reasons', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('approved_by', sa.UUID(), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reached_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('outcome_people_rescued', sa.Integer(), nullable=True),
    sa.Column('outcome_note', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['approved_by'], ['users.id'], name=op.f('fk_assignments_approved_by_users')),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_assignments_case_id_cases'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['plan_id'], ['dispatch_plans.id'], name=op.f('fk_assignments_plan_id_dispatch_plans')),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], name=op.f('fk_assignments_team_id_teams'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assignments'))
    )
    op.create_index('ix_assignments_case', 'assignments', ['case_id'], unique=False)
    op.create_index('ix_assignments_plan', 'assignments', ['plan_id'], unique=False)
    op.create_index('ix_assignments_team_status', 'assignments', ['team_id', 'status'], unique=False)
    op.create_table('case_events',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('disaster_id', sa.UUID(), nullable=False),
    sa.Column('actor_type', sa.String(length=8), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=True),
    sa.Column('actor_label', sa.Text(), nullable=True),
    sa.Column('event_type', sa.String(length=32), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_case_events_case_id_cases'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['disaster_id'], ['disasters.id'], name=op.f('fk_case_events_disaster_id_disasters'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_case_events'))
    )
    op.create_index('ix_case_events_case', 'case_events', ['case_id', 'created_at'], unique=False)
    op.create_index('ix_case_events_disaster', 'case_events', ['disaster_id', 'created_at'], unique=False)
    op.create_table('outbound_messages',
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('to_phone', sa.Text(), nullable=True),
    sa.Column('to_phone_hash', sa.String(length=64), nullable=True),
    sa.Column('template', sa.String(length=32), nullable=False),
    sa.Column('language', sa.String(length=4), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=12), server_default='queued', nullable=False),
    sa.Column('provider_message_id', sa.Text(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_outbound_messages_case_id_cases'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_outbound_messages'))
    )
    op.create_index(op.f('ix_outbound_messages_case_id'), 'outbound_messages', ['case_id'], unique=False)
    op.create_table('review_pairs',
    sa.Column('disaster_id', sa.UUID(), nullable=False),
    sa.Column('case_a_id', sa.UUID(), nullable=False),
    sa.Column('case_b_id', sa.UUID(), nullable=False),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('reasons', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('status', sa.String(length=12), server_default='open', nullable=False),
    sa.Column('resolved_by', sa.UUID(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['case_a_id'], ['cases.id'], name=op.f('fk_review_pairs_case_a_id_cases'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['case_b_id'], ['cases.id'], name=op.f('fk_review_pairs_case_b_id_cases'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['disaster_id'], ['disasters.id'], name=op.f('fk_review_pairs_disaster_id_disasters'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], name=op.f('fk_review_pairs_resolved_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_review_pairs')),
    sa.UniqueConstraint('case_a_id', 'case_b_id', name='uq_review_pairs_cases')
    )
    op.create_index('ix_review_pairs_open', 'review_pairs', ['disaster_id', 'status'], unique=False)
    op.create_geospatial_table('sos_messages',
    sa.Column('disaster_id', sa.UUID(), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('external_id', sa.Text(), nullable=True),
    sa.Column('tracking_code', sa.String(length=12), nullable=False),
    sa.Column('sender_phone', sa.Text(), nullable=True),
    sa.Column('sender_phone_hash', sa.String(length=64), nullable=True),
    sa.Column('sender_name', sa.Text(), nullable=True),
    sa.Column('raw_text', sa.Text(), nullable=True),
    sa.Column('text_hash', sa.String(length=64), nullable=True),
    sa.Column('raw_location', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('processing_status', sa.String(length=16), server_default='pending', nullable=False),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('case_id', sa.UUID(), nullable=True),
    sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('purged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_sos_messages_case_id_cases'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['disaster_id'], ['disasters.id'], name=op.f('fk_sos_messages_disaster_id_disasters'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sos_messages')),
    sa.UniqueConstraint('channel', 'external_id', name='uq_sos_messages_channel_external_id'),
    sa.UniqueConstraint('tracking_code', name=op.f('uq_sos_messages_tracking_code'))
    )
    op.create_index('ix_sos_messages_case', 'sos_messages', ['case_id'], unique=False)
    op.create_index('ix_sos_messages_disaster_received', 'sos_messages', ['disaster_id', 'received_at'], unique=False)
    op.create_index('ix_sos_messages_pending', 'sos_messages', ['processing_status'], unique=False, postgresql_where=sa.text("processing_status = 'pending'"))
    op.create_index(op.f('ix_sos_messages_sender_phone_hash'), 'sos_messages', ['sender_phone_hash'], unique=False)
    op.create_index(op.f('ix_sos_messages_text_hash'), 'sos_messages', ['text_hash'], unique=False)
    op.create_table('extractions',
    sa.Column('sos_message_id', sa.UUID(), nullable=False),
    sa.Column('people_count', sa.Integer(), nullable=True),
    sa.Column('vulnerable', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('location_text', sa.Text(), nullable=True),
    sa.Column('locality', sa.Text(), nullable=True),
    sa.Column('landmarks', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('water_level', sa.String(length=16), nullable=True),
    sa.Column('water_rising', sa.Boolean(), nullable=True),
    sa.Column('needs', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
    sa.Column('language', sa.String(length=8), nullable=True),
    sa.Column('status_update', sa.String(length=16), server_default='none', nullable=False),
    sa.Column('contact_name', sa.Text(), nullable=True),
    sa.Column('contact_phone_hashes', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('model', sa.Text(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('raw_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('embedding', Vector(768), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['sos_message_id'], ['sos_messages.id'], name=op.f('fk_extractions_sos_message_id_sos_messages'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_extractions')),
    sa.UniqueConstraint('sos_message_id', name=op.f('uq_extractions_sos_message_id'))
    )


def downgrade() -> None:
    op.drop_table('extractions')
    op.drop_index(op.f('ix_sos_messages_text_hash'), table_name='sos_messages')
    op.drop_index(op.f('ix_sos_messages_sender_phone_hash'), table_name='sos_messages')
    op.drop_index('ix_sos_messages_pending', table_name='sos_messages', postgresql_where=sa.text("processing_status = 'pending'"))
    op.drop_index('ix_sos_messages_disaster_received', table_name='sos_messages')
    op.drop_index('ix_sos_messages_case', table_name='sos_messages')
    op.drop_geospatial_table('sos_messages')
    op.drop_index('ix_review_pairs_open', table_name='review_pairs')
    op.drop_table('review_pairs')
    op.drop_index(op.f('ix_outbound_messages_case_id'), table_name='outbound_messages')
    op.drop_table('outbound_messages')
    op.drop_index('ix_case_events_disaster', table_name='case_events')
    op.drop_index('ix_case_events_case', table_name='case_events')
    op.drop_table('case_events')
    op.drop_index('ix_assignments_team_status', table_name='assignments')
    op.drop_index('ix_assignments_plan', table_name='assignments')
    op.drop_index('ix_assignments_case', table_name='assignments')
    op.drop_geospatial_table('assignments')
    op.drop_index('ix_team_locations_team_time', table_name='team_locations')
    op.drop_geospatial_index('ix_team_locations_location', table_name='team_locations', postgresql_using='gist', column_name='location')
    op.drop_geospatial_table('team_locations')
    op.drop_index('ix_cases_queue', table_name='cases')
    op.drop_geospatial_index('ix_cases_location', table_name='cases', postgresql_using='gist', column_name='location')
    op.drop_index('ix_cases_disaster_updated', table_name='cases')
    op.drop_geospatial_table('cases')
    op.drop_index(op.f('ix_user_sessions_user_id'), table_name='user_sessions')
    op.drop_table('user_sessions')
    op.drop_geospatial_index('ix_teams_location', table_name='teams', postgresql_using='gist', column_name='current_location')
    op.drop_index('ix_teams_lead', table_name='teams')
    op.drop_geospatial_table('teams')
    op.drop_index(op.f('ix_push_subscriptions_user_id'), table_name='push_subscriptions')
    op.drop_table('push_subscriptions')
    op.drop_index(op.f('ix_invites_email'), table_name='invites')
    op.drop_table('invites')
    op.drop_geospatial_index('ix_flood_zones_geom', table_name='flood_zones', postgresql_using='gist', column_name='geom')
    op.drop_index('ix_flood_zones_disaster', table_name='flood_zones')
    op.drop_geospatial_table('flood_zones')
    op.drop_index('ix_dispatch_plans_disaster', table_name='dispatch_plans')
    op.drop_table('dispatch_plans')
    op.drop_table('disaster_organizations')
    op.drop_table('users')
    op.drop_geospatial_index('ix_disasters_area', table_name='disasters', postgresql_using='gist', column_name='area')
    op.drop_geospatial_table('disasters')
    op.drop_table('replay_datasets')
    op.drop_table('organizations')
