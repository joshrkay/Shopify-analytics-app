"""
Billing Plans Seed Script (GL-3)

Seeds the 4 canonical plans (Free, Growth, Pro, Enterprise) with all 17
BillingFeature keys.  Feature enabled/disabled state and limits are derived
from BILLING_TIER_FEATURES so the seed script can never drift from the
authoritative static dict.

Usage:
    python -m scripts.seed_billing_plans
    python -m scripts.seed_billing_plans --dry-run
    python -m scripts.seed_billing_plans --delete

Environment variables:
    DATABASE_URL: PostgreSQL connection string (required)
"""

import os
import sys
import logging
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from src.models.plan import Plan, PlanFeature
from src.db_base import Base
from src.services.billing_entitlements import BillingFeature, BILLING_TIER_FEATURES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical plan definitions — pricing lives here, features come from
# BILLING_TIER_FEATURES so there is a single source of truth.
# ---------------------------------------------------------------------------

PLAN_METADATA = {
    "free": {
        "id": "plan_free",
        "display_name": "Free",
        "description": "Basic analytics for small stores",
        "price_monthly_cents": 0,
        "price_yearly_cents": 0,
    },
    "growth": {
        "id": "plan_growth",
        "display_name": "Growth",
        "description": "For growing businesses with advanced analytics",
        "price_monthly_cents": 2900,
        "price_yearly_cents": 29000,
    },
    "pro": {
        "id": "plan_pro",
        "display_name": "Pro",
        "description": "Professional tier with all features",
        "price_monthly_cents": 7900,
        "price_yearly_cents": 79000,
    },
    "enterprise": {
        "id": "plan_enterprise",
        "display_name": "Enterprise",
        "description": "Custom solutions with dedicated support",
        "price_monthly_cents": None,
        "price_yearly_cents": None,
    },
}

# All BillingFeature string keys (the 17 canonical feature keys)
ALL_FEATURE_KEYS = sorted(
    v for k, v in BillingFeature.__dict__.items()
    if not k.startswith("_") and isinstance(v, str)
)

# Tier-specific limits stored in the JSONB `limits` column.
# Only include limits that are meaningful for the feature+tier combination.
TIER_LIMITS = {
    "free": {
        "ai_insights": {"max_dashboard_access": 3, "max_users": 2, "max_alert_rules": 3},
        "ai_recommendations": {"max_dashboard_access": 3, "max_users": 2, "max_alert_rules": 3},
    },
    "growth": {
        "agency_access": {"max_agency_stores": 5},
        "multi_tenant": {"max_stores": 5},
        "advanced_dashboards": {"max_dashboard_access": 10, "max_dashboard_shares": 5},
        "data_export": {"format": "csv"},
        "ai_insights": {"max_dashboard_access": 10, "max_users": 10, "max_alert_rules": 10},
        "ai_actions": {"limited": True},
        "alerts": {"max_alert_rules": 10},
        "sheets_export": {"limited": True},
    },
    "pro": {
        "agency_access": {"max_agency_stores": 10},
        "multi_tenant": {"max_stores": 10},
        "advanced_dashboards": {"max_dashboard_access": 50, "max_dashboard_shares": 20},
        "ai_insights": {"max_dashboard_access": 50, "max_users": 20, "max_alert_rules": 50},
        "alerts": {"max_alert_rules": 50},
        "warehouse_export": {"max_warehouse_destinations": 1},
    },
    "enterprise": {
        "agency_access": {"max_agency_stores": 999},
        "multi_tenant": {"max_stores": 999},
        "advanced_dashboards": {"max_dashboard_access": 999, "max_dashboard_shares": 999},
        "ai_insights": {"max_dashboard_access": 999, "max_users": 999, "max_alert_rules": -1},
        "alerts": {"max_alert_rules": -1},
    },
}

# limit_value integers for features that have a single numeric cap
TIER_LIMIT_VALUES = {
    "growth": {"multi_tenant": 5},
    "pro": {"multi_tenant": 10, "warehouse_export": 1},
}


def _build_billing_plans():
    """Build the BILLING_PLANS list from PLAN_METADATA + BILLING_TIER_FEATURES."""
    plans = []
    for tier_name, meta in PLAN_METADATA.items():
        tier_features = BILLING_TIER_FEATURES[tier_name]
        features = []
        for fkey in ALL_FEATURE_KEYS:
            is_enabled = bool(tier_features.get(fkey, False))
            limits = TIER_LIMITS.get(tier_name, {}).get(fkey)
            limit_value = TIER_LIMIT_VALUES.get(tier_name, {}).get(fkey)
            features.append({
                "feature_key": fkey,
                "is_enabled": is_enabled,
                "limit_value": limit_value,
                "limits": limits,
            })
        plans.append({
            "id": meta["id"],
            "name": tier_name,
            "display_name": meta["display_name"],
            "description": meta["description"],
            "price_monthly_cents": meta["price_monthly_cents"],
            "price_yearly_cents": meta["price_yearly_cents"],
            "is_active": True,
            "features": features,
        })
    return plans


BILLING_PLANS = _build_billing_plans()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_database_url() -> str:
    """Get database URL from environment."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError(
            "DATABASE_URL environment variable is required. "
            "Example: postgresql://user:password@localhost:5432/dbname"
        )
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    return database_url


def format_price(cents: int | None) -> str:
    """Format price in cents to display string."""
    if cents is None:
        return "N/A"
    if cents == 0:
        return "FREE"
    return f"${cents / 100:.2f}"


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def seed_billing_plans(database_url: str, dry_run: bool = False) -> None:
    """Seed billing plans into the database."""
    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        logger.info("=" * 60)
        logger.info("BILLING PLANS SEED SCRIPT")
        logger.info("=" * 60)
        logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTION'}")
        logger.info(f"Total plans: {len(BILLING_PLANS)}")
        logger.info(f"Feature keys per plan: {len(ALL_FEATURE_KEYS)}")
        logger.info("")

        existing_plans = session.query(Plan).all()
        existing_by_name = {p.name: p for p in existing_plans}

        for plan_data in BILLING_PLANS:
            name = plan_data["name"]
            existing = existing_by_name.get(name)
            action = "UPDATE" if existing else "CREATE"

            if plan_data["price_monthly_cents"]:
                price_str = f"${plan_data['price_monthly_cents'] / 100:.2f}/month"
            elif plan_data["price_yearly_cents"]:
                price_str = f"${plan_data['price_yearly_cents'] / 100:.2f}/year"
            else:
                price_str = "FREE" if plan_data["price_monthly_cents"] == 0 else "Custom"

            enabled_count = sum(1 for f in plan_data["features"] if f["is_enabled"])
            logger.info(
                f"  [{action}] {plan_data['display_name']}: {price_str} "
                f"({enabled_count}/{len(plan_data['features'])} features enabled)"
            )

        logger.info("")

        if dry_run:
            logger.info("DRY RUN — No changes will be made")
            logger.info("")
            for plan_data in BILLING_PLANS:
                logger.info(f"Plan: {plan_data['display_name']} ({plan_data['id']})")
                logger.info(f"  Price: {format_price(plan_data['price_monthly_cents'])}/mo")
                logger.info("  Features:")
                for f in plan_data["features"]:
                    status = "ENABLED" if f["is_enabled"] else "disabled"
                    extra = ""
                    if f["limit_value"] is not None:
                        extra += f" limit_value={f['limit_value']}"
                    if f["limits"]:
                        extra += f" limits={f['limits']}"
                    logger.info(f"    {f['feature_key']}: {status}{extra}")
                logger.info("")
            return

        # Upsert plans and features
        created = 0
        updated = 0
        for plan_data in BILLING_PLANS:
            try:
                existing = existing_by_name.get(plan_data["name"])
                if existing:
                    existing.display_name = plan_data["display_name"]
                    existing.description = plan_data["description"]
                    existing.price_monthly_cents = plan_data["price_monthly_cents"]
                    existing.price_yearly_cents = plan_data["price_yearly_cents"]
                    existing.is_active = plan_data["is_active"]
                    plan_id = existing.id
                    updated += 1
                else:
                    plan = Plan(
                        id=plan_data["id"],
                        name=plan_data["name"],
                        display_name=plan_data["display_name"],
                        description=plan_data["description"],
                        price_monthly_cents=plan_data["price_monthly_cents"],
                        price_yearly_cents=plan_data["price_yearly_cents"],
                        is_active=plan_data["is_active"],
                    )
                    session.add(plan)
                    session.flush()
                    plan_id = plan.id
                    created += 1

                # Upsert features
                existing_features = {
                    pf.feature_key: pf
                    for pf in session.query(PlanFeature).filter_by(plan_id=plan_id).all()
                }
                for feat in plan_data["features"]:
                    pf = existing_features.get(feat["feature_key"])
                    if pf:
                        pf.is_enabled = feat["is_enabled"]
                        pf.limit_value = feat["limit_value"]
                        pf.limits = feat["limits"]
                    else:
                        session.add(PlanFeature(
                            id=f"feat_{os.urandom(6).hex()}",
                            plan_id=plan_id,
                            feature_key=feat["feature_key"],
                            is_enabled=feat["is_enabled"],
                            limit_value=feat["limit_value"],
                            limits=feat["limits"],
                        ))

                # Remove stale features not in ALL_FEATURE_KEYS
                for fkey, pf in existing_features.items():
                    if fkey not in ALL_FEATURE_KEYS:
                        session.delete(pf)

                session.commit()
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Failed to upsert {plan_data['name']}: {e}")

        logger.info("=" * 60)
        logger.info("SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Plans created: {created}")
        logger.info(f"Plans updated: {updated}")

    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def delete_billing_plans(database_url: str, dry_run: bool = False) -> None:
    """Delete all canonical billing plans."""
    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    plan_names = [p["name"] for p in BILLING_PLANS]

    try:
        logger.info("=" * 60)
        logger.info("DELETE BILLING PLANS")
        logger.info("=" * 60)
        logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTION'}")
        logger.info("")

        plans_to_delete = session.query(Plan).filter(Plan.name.in_(plan_names)).all()

        if not plans_to_delete:
            logger.info("No plans to delete.")
            return

        logger.info(f"Plans to delete ({len(plans_to_delete)}):")
        for plan in plans_to_delete:
            logger.info(f"   - {plan.display_name} (ID: {plan.id})")

        if dry_run:
            logger.info("")
            logger.info("DRY RUN — No changes will be made")
            return

        for plan in plans_to_delete:
            session.delete(plan)

        session.commit()
        logger.info(f"Deleted {len(plans_to_delete)} plans and their features.")

    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed billing plans into the database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.seed_billing_plans              # Create/update plans
  python -m scripts.seed_billing_plans --dry-run    # Preview without saving
  python -m scripts.seed_billing_plans --delete     # Delete seeded plans
        """
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--delete", action="store_true", help="Delete all seeded plans")
    parser.add_argument("--database-url", type=str, help="Database URL (overrides env var)")

    args = parser.parse_args()

    try:
        database_url = args.database_url or get_database_url()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    try:
        if args.delete:
            delete_billing_plans(database_url, args.dry_run)
        else:
            seed_billing_plans(database_url, args.dry_run)
    except Exception as e:
        logger.error(f"Script failed: {e}")
        sys.exit(1)

    logger.info("Done!")


if __name__ == "__main__":
    main()
