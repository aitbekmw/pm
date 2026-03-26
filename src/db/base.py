from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


metadata = Base.metadata


def import_all_models() -> None:
    # Import all model modules so Alembic sees the tables
    from src.users import models as _users_models  # noqa: F401
    from src.projects import models as _projects_models  # noqa: F401
    from src.meetings import models as _meetings_models  # noqa: F401
    from src.companies import models as _companies_models  # noqa: F401
    from src.faq import models as _faq_models  # noqa: F401


