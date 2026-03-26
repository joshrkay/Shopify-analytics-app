"""Regression: optional route modules must remain importable (prevents main.py merge drift)."""

from src.api.routes import admin_super_admin
from src.api.routes import audit as audit_story_87
from src.api.routes import templates as templates_legacy


def test_route_module_prefixes_stable():
    assert admin_super_admin.router.prefix == "/api/admin"
    assert audit_story_87.router.prefix == "/api/audit"
    assert templates_legacy.router.prefix == "/api/templates"
