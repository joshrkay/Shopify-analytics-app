/**
 * Type definitions for Agency RBAC system.
 *
 * Agency users have access to multiple client stores via allowed_tenants[].
 */

/**
 * Role types for user classification.
 */
export enum UserRole {
  // Merchant roles (single tenant)
  MERCHANT_ADMIN = 'merchant_admin',
  MERCHANT_VIEWER = 'merchant_viewer',

  // Agency roles (multi-tenant)
  AGENCY_ADMIN = 'agency_admin',
  AGENCY_VIEWER = 'agency_viewer',

  // Platform roles (legacy)
  ADMIN = 'admin',
  OWNER = 'owner',
  EDITOR = 'editor',
  VIEWER = 'viewer',

  // Super admin
  SUPER_ADMIN = 'super_admin',
}

/**
 * Role category for determining tenant access scope.
 */
export enum RoleCategory {
  MERCHANT = 'merchant',
  AGENCY = 'agency',
  PLATFORM = 'platform',
}

/**
 * Billing tier levels.
 */
export enum BillingTier {
  FREE = 'free',
  GROWTH = 'growth',
  ENTERPRISE = 'enterprise',
}

/**
 * Assigned store information for agency users.
 */
export interface AssignedStore {
  tenant_id: string;
  store_name: string;
  shop_domain: string;
  status: 'active' | 'inactive' | 'suspended';
  assigned_at: string;
  permissions: string[];
}

/**
 * Current user context from JWT.
 */
export interface UserContext {
  user_id: string;
  tenant_id: string;
  org_id: string;
  roles: UserRole[];
  allowed_tenants: string[];
  billing_tier: BillingTier;
  is_agency_user: boolean;
}

/**
 * Response from assigned stores API.
 */
export interface AssignedStoresResponse {
  stores: AssignedStore[];
  total_count: number;
  active_tenant_id: string;
  max_stores_allowed: number;
}

/**
 * Request to switch active store.
 */
export interface SwitchStoreRequest {
  tenant_id: string;
}

/**
 * Response from store switch API.
 */
export interface SwitchStoreResponse {
  success: boolean;
  jwt_token: string;
  active_tenant_id: string;
  store: AssignedStore;
}

/**
 * Agency user permissions check result.
 */
export interface PermissionCheckResult {
  has_permission: boolean;
  required_role?: UserRole;
  required_tier?: BillingTier;
  reason?: string;
}

/**
 * Check if a role is an agency role.
 */
export function isAgencyRole(role: UserRole): boolean {
  return role === UserRole.AGENCY_ADMIN || role === UserRole.AGENCY_VIEWER;
}

/**
 * Check if a role is a merchant role.
 */
export function isMerchantRole(role: UserRole): boolean {
  return role === UserRole.MERCHANT_ADMIN || role === UserRole.MERCHANT_VIEWER;
}

/**
 * Check if user has multi-tenant access based on roles.
 */
export function hasMultiTenantAccess(roles: UserRole[]): boolean {
  return roles.some(
    (role) =>
      role === UserRole.AGENCY_ADMIN ||
      role === UserRole.AGENCY_VIEWER ||
      role === UserRole.SUPER_ADMIN
  );
}

/**
 * Get the role category for a given role.
 */
export function getRoleCategory(role: UserRole): RoleCategory {
  if (isAgencyRole(role)) return RoleCategory.AGENCY;
  if (isMerchantRole(role)) return RoleCategory.MERCHANT;
  return RoleCategory.PLATFORM;
}
