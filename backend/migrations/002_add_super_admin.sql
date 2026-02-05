-- =============================================================================
-- Super Admin Migration
-- =============================================================================
-- Version: 1.0.0
-- Date: 2026-02-04
-- Feature: Secure Administrative Access - DB-Backed Super Admin
--
-- This migration adds the is_super_admin field to the users table.
--
-- SECURITY CRITICAL:
-- - Super admin status is NEVER determined from JWT claims
-- - Super admin can ONLY be set via:
--   1. This migration (initial bootstrap)
--   2. SuperAdminService (requires existing super admin authorization)
-- - Super admin grants:
--   - Access to all tenants
--   - Ability to export audit logs across tenants
--   - Ability to view system-wide settings
--   - Ability to grant/revoke super admin to other users
--
-- AUDIT REQUIREMENTS:
-- - All super admin changes must be logged via audit events:
--   - identity.super_admin_granted
--   - identity.super_admin_revoked
-- =============================================================================

-- Add is_super_admin column to users table
ALTER TABLE users
ADD COLUMN IF NOT EXISTS is_super_admin BOOLEAN NOT NULL DEFAULT FALSE;

-- Create index for super admin lookups (performance for authorization checks)
CREATE INDEX IF NOT EXISTS ix_users_super_admin
ON users(is_super_admin)
WHERE is_super_admin = TRUE;

-- Comment on the column explaining the security model
COMMENT ON COLUMN users.is_super_admin IS
'Super admin status - grants access to all tenants. SECURITY: DB-only field, NEVER from JWT claims. Can only be modified via migration or SuperAdminService.';

-- =============================================================================
-- Bootstrap: Initial Super Admin (Optional)
-- =============================================================================
-- To bootstrap your first super admin, uncomment and modify the following:
-- WARNING: Only run this ONCE during initial setup
--
-- UPDATE users
-- SET is_super_admin = TRUE, updated_at = NOW()
-- WHERE clerk_user_id = 'user_XXXXXXXXXXXXXXXXX'  -- Replace with actual Clerk user ID
-- RETURNING id, clerk_user_id, email, is_super_admin;
--
-- After bootstrap, use the SuperAdminService API to manage super admins.
-- =============================================================================

-- =============================================================================
-- Migration Verification
-- =============================================================================
SELECT 'Super admin migration completed successfully' AS status;
SELECT
    column_name,
    data_type,
    column_default,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'users'
AND column_name = 'is_super_admin';
