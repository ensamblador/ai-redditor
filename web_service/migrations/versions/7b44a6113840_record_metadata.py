"""Record metadata

Revision ID: 7b44a6113840
Revises: 45b8251ff686
Create Date: 2020-07-20 14:12:52.413717

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7b44a6113840'
down_revision = '45b8251ff686'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('phc_record', schema=None) as batch_op:
        batch_op.add_column(sa.Column('creation_date', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('is_likes_prompted', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('prompted_author_username_end', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('prompted_comment_end', sa.Integer(), nullable=True))

    with op.batch_alter_table('tifu_record', schema=None) as batch_op:
        batch_op.add_column(sa.Column('creation_date', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('post_body_prompt_end', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('post_title_prompt_end', sa.Integer(), nullable=True))

    with op.batch_alter_table('wp_record', schema=None) as batch_op:
        batch_op.add_column(sa.Column('creation_date', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('prompted_prompt_end', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('prompted_response_end', sa.Integer(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('wp_record', schema=None) as batch_op:
        batch_op.drop_column('prompted_response_end')
        batch_op.drop_column('prompted_prompt_end')
        batch_op.drop_column('creation_date')

    with op.batch_alter_table('tifu_record', schema=None) as batch_op:
        batch_op.drop_column('post_title_prompt_end')
        batch_op.drop_column('post_body_prompt_end')
        batch_op.drop_column('creation_date')

    with op.batch_alter_table('phc_record', schema=None) as batch_op:
        batch_op.drop_column('prompted_comment_end')
        batch_op.drop_column('prompted_author_username_end')
        batch_op.drop_column('is_likes_prompted')
        batch_op.drop_column('creation_date')

    # ### end Alembic commands ###