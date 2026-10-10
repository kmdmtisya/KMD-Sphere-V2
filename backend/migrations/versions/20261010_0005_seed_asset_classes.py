"""seed the 16 initial asset classes (P05-T02)

A data migration: the rows are written out here (a fixed snapshot), not imported from application
code that may change later. tests/test_assets_api.py checks they match app/modules/assets/catalogue.py.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CLASSES = [
    {
        "code": "stock",
        "name": "Stocks",
        "valuation_mode": "market",
        "metadata_schema": {
            "fields": {
                "exchange": {"type": "string", "required": False},
                "isin": {"type": "string", "required": False},
                "sector": {"type": "string", "required": False},
            }
        },
    },
    {
        "code": "etf",
        "name": "ETFs",
        "valuation_mode": "market",
        "metadata_schema": {
            "fields": {
                "exchange": {"type": "string", "required": False},
                "isin": {"type": "string", "required": False},
                "expense_ratio": {"type": "decimal", "required": False},
            }
        },
    },
    {
        "code": "bond",
        "name": "Bonds",
        "valuation_mode": "market",
        "metadata_schema": {
            "fields": {
                "issuer": {"type": "string", "required": False},
                "isin": {"type": "string", "required": False},
                "coupon_rate": {"type": "decimal", "required": False},
                "maturity_date": {"type": "date", "required": False},
                "face_value": {"type": "decimal", "required": False},
            }
        },
    },
    {
        "code": "money_market_fund",
        "name": "Money market funds",
        "valuation_mode": "manual",
        "metadata_schema": {
            "fields": {
                "fund_manager": {"type": "string", "required": False},
                "yield_rate": {"type": "decimal", "required": False},
            }
        },
    },
    {
        "code": "fixed_deposit",
        "name": "Fixed deposits",
        "valuation_mode": "manual",
        "metadata_schema": {
            "fields": {
                "institution": {"type": "string", "required": False},
                "interest_rate": {"type": "decimal", "required": True},
                "start_date": {"type": "date", "required": False},
                "maturity_date": {"type": "date", "required": True},
            }
        },
    },
    {
        "code": "mutual_fund",
        "name": "Mutual funds",
        "valuation_mode": "market",
        "metadata_schema": {
            "fields": {
                "fund_manager": {"type": "string", "required": False},
                "isin": {"type": "string", "required": False},
                "expense_ratio": {"type": "decimal", "required": False},
            }
        },
    },
    {
        "code": "reit",
        "name": "REITs",
        "valuation_mode": "market",
        "metadata_schema": {
            "fields": {
                "exchange": {"type": "string", "required": False},
                "isin": {"type": "string", "required": False},
                "sector": {"type": "string", "required": False},
            }
        },
    },
    {
        "code": "real_estate",
        "name": "Real estate",
        "valuation_mode": "manual",
        "metadata_schema": {
            "fields": {
                "property_type": {"type": "string", "required": False},
                "location": {"type": "string", "required": False},
                "ownership_percent": {"type": "decimal", "required": False},
            }
        },
    },
    {
        "code": "cryptocurrency",
        "name": "Cryptocurrency",
        "valuation_mode": "market",
        "metadata_schema": {"fields": {"network": {"type": "string", "required": False}}},
    },
    {
        "code": "commodity",
        "name": "Commodities",
        "valuation_mode": "market",
        "metadata_schema": {"fields": {"unit": {"type": "string", "required": False}}},
    },
    {
        "code": "pension",
        "name": "Pension and retirement",
        "valuation_mode": "manual",
        "metadata_schema": {
            "fields": {
                "provider": {"type": "string", "required": False},
                "scheme_type": {"type": "string", "required": False},
            }
        },
    },
    {
        "code": "sacco",
        "name": "SACCO and co-operative holdings",
        "valuation_mode": "manual",
        "metadata_schema": {
            "fields": {
                "institution": {"type": "string", "required": False},
                "share_type": {"type": "string", "required": False},
            }
        },
    },
    {
        "code": "private_business",
        "name": "Private business",
        "valuation_mode": "manual",
        "metadata_schema": {
            "fields": {
                "ownership_percent": {"type": "decimal", "required": False},
                "registration_country": {"type": "string", "required": False},
            }
        },
    },
    {
        "code": "private_equity",
        "name": "Private equity",
        "valuation_mode": "manual",
        "metadata_schema": {
            "fields": {
                "fund_manager": {"type": "string", "required": False},
                "vintage_year": {"type": "integer", "required": False},
                "commitment": {"type": "decimal", "required": False},
            }
        },
    },
    {
        "code": "cash",
        "name": "Cash and savings",
        "valuation_mode": "manual",
        "metadata_schema": {
            "fields": {
                "institution": {"type": "string", "required": False},
                "account_type": {"type": "string", "required": False},
            }
        },
    },
    {
        "code": "custom",
        "name": "Custom assets",
        "valuation_mode": "manual",
        "metadata_schema": {"fields": {"description": {"type": "string", "required": False}}},
    },
]

_asset_classes = sa.table(
    "asset_classes",
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("valuation_mode", sa.String),
    sa.column("metadata_schema", postgresql.JSONB),
)


def upgrade() -> None:
    op.bulk_insert(_asset_classes, CLASSES)


def downgrade() -> None:
    op.execute(
        _asset_classes.delete().where(_asset_classes.c.code.in_([c["code"] for c in CLASSES]))
    )
