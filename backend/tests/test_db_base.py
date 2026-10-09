import uuid
from datetime import datetime
from decimal import Decimal
from typing import cast

from sqlalchemy import ForeignKey, Index, MetaData, String, Table, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.base import (
    AMOUNT,
    NAMING_CONVENTION,
    QUANTITY,
    RATE,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class _Scratch(DeclarativeBase):
    """Isolated metadata so this test never pollutes the application's Base."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = Base.type_annotation_map


class Parent(UUIDPrimaryKeyMixin, TimestampMixin, _Scratch):
    __tablename__ = "parent"
    code: Mapped[str] = mapped_column(String(10))
    balance: Mapped[Decimal]
    __table_args__ = (UniqueConstraint("code"), Index("ix_parent_code_lookup", "code"))


class Child(UUIDPrimaryKeyMixin, TimestampMixin, _Scratch):
    __tablename__ = "child"
    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parent.id"))
    quantity: Mapped[Decimal] = mapped_column(QUANTITY)
    rate: Mapped[Decimal] = mapped_column(RATE)


def _table(model: type[DeclarativeBase]) -> Table:
    return cast(Table, model.__table__)


def _ddl(model: type[DeclarativeBase]) -> str:
    return str(CreateTable(_table(model)).compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]


def test_naming_convention_gives_deterministic_constraint_names() -> None:
    parent = _ddl(Parent)
    child = _ddl(Child)
    assert "CONSTRAINT pk_parent PRIMARY KEY (id)" in parent
    assert "CONSTRAINT uq_parent_code UNIQUE (code)" in parent
    assert "CONSTRAINT pk_child PRIMARY KEY (id)" in child
    assert (
        "CONSTRAINT fk_child_parent_id_parent FOREIGN KEY(parent_id) REFERENCES parent (id)"
        in child
    )


def test_uuid_primary_key_with_server_default() -> None:
    ddl = _ddl(Parent)
    assert "id UUID DEFAULT gen_random_uuid() NOT NULL" in ddl


def test_money_columns_are_numeric_never_float() -> None:
    ddl = _ddl(Parent) + _ddl(Child)
    assert "balance NUMERIC(28, 8) NOT NULL" in ddl
    assert "quantity NUMERIC(28, 12) NOT NULL" in ddl
    assert "rate NUMERIC(28, 12) NOT NULL" in ddl
    assert "FLOAT" not in ddl.upper()
    assert "DOUBLE" not in ddl.upper()
    assert AMOUNT.precision == 28
    assert AMOUNT.scale == 8


def test_timestamps_are_timezone_aware_with_server_defaults() -> None:
    ddl = _ddl(Parent)
    assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl
    assert "updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl
    assert isinstance(datetime.now().astimezone(), datetime)


def test_index_names_follow_convention() -> None:
    index = next(iter(_table(Parent).indexes))
    assert str(CreateIndex(index).compile(dialect=postgresql.dialect())).startswith(  # type: ignore[no-untyped-call]
        "CREATE INDEX ix_parent_code_lookup ON parent (code)"
    )
