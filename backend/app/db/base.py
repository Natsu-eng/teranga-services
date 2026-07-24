from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Convention de nommage des contraintes : sans elle, Postgres/Alembic génère
# des noms anonymes (ex. "user_phone_key") impossibles à cibler explicitement
# dans une migration de downgrade, ce qui rend les downgrades fragiles.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base déclarative commune à tous les modèles ORM."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
