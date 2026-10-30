"""Complete music service: metadata, private collections and CSRF sessions."""
from alembic import op
import sqlalchemy as sa

revision = "f103_service"
down_revision = "f102_auth"
branch_labels = depends_on = None


def upgrade():
    # All old sessions are revoked as they lack a CSRF secret.
    op.execute(sa.text("DELETE FROM sessions"))
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("csrf_token", sa.String(64), nullable=False))
        batch.create_index("ix_sessions_user_id", ["user_id"])
    with op.batch_alter_table("author") as batch:
        batch.alter_column("name", type_=sa.String(200), existing_type=sa.String(20), existing_nullable=False)
    with op.batch_alter_table("track") as batch:
        batch.alter_column("name", type_=sa.String(200), existing_type=sa.String(20), existing_nullable=False)
        batch.alter_column("author_id", nullable=True, existing_type=sa.Integer())
        batch.alter_column("duration", type_=sa.Float(), existing_type=sa.Integer(), existing_nullable=True)
        batch.add_column(sa.Column("artist", sa.String(200), nullable=False, server_default=""))
        batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
        batch.create_index("ix_track_owner_id", ["owner_id"])
    op.execute(sa.text("UPDATE track SET artist = COALESCE((SELECT name FROM author WHERE author.id = track.author_id), '')"))
    # Legacy files did not pass the new processing pipeline. Preserve their rows
    # and bytes, but keep them out of the public catalogue until securely imported.
    op.execute(sa.text("UPDATE track SET is_active = false"))
    with op.batch_alter_table("playlist") as batch:
        batch.alter_column("name", type_=sa.String(100), existing_type=sa.String(20), existing_nullable=False)
        batch.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_playlist_owner", "users", ["owner_id"], ["id"])
        batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
        batch.create_index("ix_playlist_owner_id", ["owner_id"])
    op.execute(sa.text("DELETE FROM playlisttrackmodel WHERE id NOT IN (SELECT MIN(id) FROM playlisttrackmodel GROUP BY playlist_id, music_id)"))
    with op.batch_alter_table("playlisttrackmodel") as batch:
        batch.create_unique_constraint("uq_playlist_track", ["playlist_id", "music_id"])
        batch.create_index("ix_playlisttrackmodel_playlist_id", ["playlist_id"])
        batch.create_index("ix_playlisttrackmodel_music_id", ["music_id"])
    op.create_table("favorites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("track_id", sa.Integer(), sa.ForeignKey("track.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("user_id", "track_id", name="uq_user_favorite"))
    op.create_index("ix_favorites_user_id", "favorites", ["user_id"])
    op.create_index("ix_favorites_track_id", "favorites", ["track_id"])
    op.create_table("file_deletions", sa.Column("path", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))


def downgrade():
    # Widened names and migrated metadata are deliberately retained on rollback.
    # Downgrade is data-destructive; require an explicit backup/restore instead.
    raise RuntimeError("Restore a database backup to roll back the full service migration")
