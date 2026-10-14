"""Every OpenAPI component has its own plain name. When two response or request models share a
class name, FastAPI renames both to module-qualified names (`app__modules__...__Name`), which
silently changes the published contract of the module that had the name first (P13-T06)."""

from app.main import create_app
from tests.conftest import make_settings


def test_no_two_models_share_a_schema_name() -> None:
    spec = create_app(make_settings(), readiness_checks={}).openapi()
    qualified = sorted(k for k in spec["components"]["schemas"] if "__" in k)
    assert qualified == [], f"rename one of the models that share a name: {qualified}"
