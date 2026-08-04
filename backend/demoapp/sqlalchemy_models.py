from pathlib import Path

from django.conf import settings
from sqlalchemy import Boolean, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class SqlAlchemyBase(DeclarativeBase):
    pass


class AuditRecord(SqlAlchemyBase):
    __tablename__ = 'sa_audit_record'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        database_path = Path(settings.BASE_DIR) / 'sqlalchemy_demo.sqlite3'
        _engine = create_engine(f'sqlite:///{database_path}', future=True)
    return _engine


def ensure_sqlalchemy_demo_data():
    engine = get_engine()
    SqlAlchemyBase.metadata.create_all(engine)
    with Session(engine) as session:
        if session.scalar(select(AuditRecord.id).limit(1)) is None:
            session.add_all(
                [
                    AuditRecord(name='Alpha SQL Audit', category='security', active=True),
                    AuditRecord(name='Beta Session Event', category='auth', active=True),
                    AuditRecord(name='Gamma Validation Event', category='contract', active=False),
                ]
            )
            session.commit()


def search_audit_records(term):
    ensure_sqlalchemy_demo_data()
    engine = get_engine()
    statement = (
        select(AuditRecord)
        .where(AuditRecord.name.ilike(f'%{term}%'))
        .order_by(AuditRecord.id)
    )
    compiled = statement.compile(engine)
    with Session(engine) as session:
        records = session.scalars(statement).all()
    return {
        'model': 'AuditRecord(SqlAlchemyBase)',
        'database': 'sqlalchemy_demo.sqlite3',
        'sql_template': str(compiled),
        'bound_params': compiled.params,
        'items': [
            {
                'id': record.id,
                'name': record.name,
                'category': record.category,
                'active': record.active,
            }
            for record in records
        ],
    }
