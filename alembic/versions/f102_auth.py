"""Users and track ownership."""
from alembic import op
import sqlalchemy as sa
revision = "f102_auth"
down_revision = "e463318ea53a"
branch_labels = depends_on = None
def upgrade():
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("username", sa.String(64), nullable=False, unique=True), sa.Column("password_hash", sa.String(256), nullable=False))
    op.create_table("sessions", sa.Column("token", sa.String(64), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("expires", sa.DateTime(timezone=True), nullable=False))
    with op.batch_alter_table("track") as batch:
        batch.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_track_owner", "users", ["owner_id"], ["id"])
def downgrade():
    with op.batch_alter_table("track") as batch:
        batch.drop_constraint("fk_track_owner", type_="foreignkey")
        batch.drop_column("owner_id")
    op.drop_table("sessions")
    op.drop_table("users")
