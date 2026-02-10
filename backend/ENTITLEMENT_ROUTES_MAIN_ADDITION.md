# Add Entitlement Routes to main.py

In your FastAPI `main.py` (e.g. `backend/main.py` or `backend/src/main.py`), add:

```python
# Entitlement and admin override routes
from src.api.routes import entitlements as entitlement_routes
from src.api.routes import admin_overrides as admin_overrides_routes

# After creating the app (e.g. app = FastAPI()):
app.include_router(entitlement_routes.router)
app.include_router(admin_overrides_routes.router)
```

This registers:
- `GET /api/v1/entitlements` — read-only entitlements for current tenant
- `POST/PUT/DELETE/GET /api/v1/admin/entitlement-overrides` — admin override CRUD (Super Admin + Support only)
