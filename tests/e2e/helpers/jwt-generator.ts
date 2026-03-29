/**
 * JWT generator for E2E testing.
 *
 * Port of backend/src/tests/e2e/mocks/mock_clerk.py to TypeScript.
 * Generates Clerk-compatible JWTs signed with an RSA key pair.
 *
 * The backend must be started with E2E_AUTH_MODE=mock and the same
 * public key configured for verification.
 */
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';

const KEY_DIR = path.join(__dirname, '..', '.keys');
const PRIVATE_KEY_PATH = path.join(KEY_DIR, 'e2e-private.pem');
const PUBLIC_KEY_PATH = path.join(KEY_DIR, 'e2e-public.pem');

let _privateKey: string | null = null;
let _publicKey: string | null = null;

/**
 * Generate or load RSA key pair for E2E JWT signing.
 * Keys are persisted to disk so backend and tests share the same pair.
 */
export function getKeyPair(): { privateKey: string; publicKey: string } {
  if (_privateKey && _publicKey) {
    return { privateKey: _privateKey, publicKey: _publicKey };
  }

  if (fs.existsSync(PRIVATE_KEY_PATH) && fs.existsSync(PUBLIC_KEY_PATH)) {
    _privateKey = fs.readFileSync(PRIVATE_KEY_PATH, 'utf-8');
    _publicKey = fs.readFileSync(PUBLIC_KEY_PATH, 'utf-8');
    return { privateKey: _privateKey, publicKey: _publicKey };
  }

  // Generate new key pair
  const { privateKey, publicKey } = crypto.generateKeyPairSync('rsa', {
    modulusLength: 2048,
    publicKeyEncoding: { type: 'spki', format: 'pem' },
    privateKeyEncoding: { type: 'pkcs8', format: 'pem' },
  });

  fs.mkdirSync(KEY_DIR, { recursive: true });
  fs.writeFileSync(PRIVATE_KEY_PATH, privateKey, { mode: 0o600 });
  fs.writeFileSync(PUBLIC_KEY_PATH, publicKey, { mode: 0o644 });

  _privateKey = privateKey;
  _publicKey = publicKey;
  return { privateKey, publicKey };
}

export interface TokenOptions {
  tenantId: string;
  userId?: string;
  email?: string;
  roles?: string[];
  entitlements?: string[];
  allowedTenants?: string[];
  expiresInSeconds?: number;
  customClaims?: Record<string, unknown>;
}

/**
 * Create a Clerk-compatible JWT for E2E testing.
 *
 * Matches the claim structure from MockClerkServer.create_test_token()
 * in backend/src/tests/e2e/mocks/mock_clerk.py.
 */
export function createTestToken(options: TokenOptions): string {
  const { privateKey } = getKeyPair();
  const now = Math.floor(Date.now() / 1000);
  const userId = options.userId || `user_${crypto.randomUUID().replace(/-/g, '').slice(0, 24)}`;
  const email = options.email || `test-${crypto.randomUUID().slice(0, 8)}@example.com`;
  const roles = options.roles || ['user'];
  const entitlements = options.entitlements || [];
  const allowedTenants = options.allowedTenants || [options.tenantId];
  const expiresIn = options.expiresInSeconds || 3600;

  const payload = {
    sub: userId,
    email,
    org_id: options.tenantId,
    org_role: roles[0] ? `org:${roles[0]}` : 'org:member',
    org_permissions: roles,
    // Clerk v2 nested org claims
    o: {
      id: options.tenantId,
      rol: roles[0] || 'member',
      per: roles,
    },
    metadata: {
      roles,
      entitlements,
      allowed_tenants: allowedTenants,
    },
    iat: now,
    exp: now + expiresIn,
    iss: 'https://clerk.example.com',
    azp: 'test-clerk-publishable-key',
    sid: `sess_${crypto.randomUUID().replace(/-/g, '').slice(0, 24)}`,
    ...(options.customClaims || {}),
  };

  return signJwt(payload, privateKey);
}

/** Create a free-tier token (no AI entitlements). */
export function createFreeTierToken(tenantId: string, userId?: string): string {
  return createTestToken({ tenantId, userId, roles: ['user'], entitlements: [] });
}

/** Create a Growth-tier token. */
export function createGrowthTierToken(tenantId: string, userId?: string): string {
  return createTestToken({
    tenantId,
    userId,
    roles: ['user'],
    entitlements: ['CUSTOM_REPORTS'],
  });
}

/** Create a Pro-tier token with AI features. */
export function createProTierToken(tenantId: string, userId?: string): string {
  return createTestToken({
    tenantId,
    userId,
    roles: ['user'],
    entitlements: ['AI_INSIGHTS', 'AI_RECOMMENDATIONS', 'AI_ACTIONS', 'CUSTOM_REPORTS', 'COHORT_ANALYSIS'],
  });
}

/** Create an Enterprise-tier token with all features. */
export function createEnterpriseTierToken(tenantId: string, userId?: string): string {
  return createTestToken({
    tenantId,
    userId,
    roles: ['admin', 'user'],
    entitlements: [
      'AI_INSIGHTS', 'AI_RECOMMENDATIONS', 'AI_ACTIONS',
      'CUSTOM_REPORTS', 'COHORT_ANALYSIS',
      'BUDGET_PACING', 'ALERTS', 'ADVANCED_ANALYTICS',
    ],
  });
}

/** Create an admin token. */
export function createAdminToken(tenantId: string, userId?: string): string {
  return createTestToken({
    tenantId,
    userId,
    roles: ['admin', 'user'],
    entitlements: ['AI_INSIGHTS', 'AI_RECOMMENDATIONS', 'AI_ACTIONS', 'ADVANCED_ANALYTICS'],
  });
}

/** Create an agency user token with multi-tenant access. */
export function createAgencyToken(
  primaryTenantId: string,
  allowedTenants: string[],
  userId?: string,
): string {
  return createTestToken({
    tenantId: primaryTenantId,
    userId,
    roles: ['agency_user', 'user'],
    allowedTenants,
    entitlements: ['AI_INSIGHTS', 'AI_RECOMMENDATIONS'],
  });
}

/** Create an expired token (for auth failure testing). */
export function createExpiredToken(tenantId: string): string {
  return createTestToken({
    tenantId,
    expiresInSeconds: -3600, // 1 hour ago
  });
}

/**
 * Sign a JWT payload with RS256.
 * Uses Node.js crypto directly to avoid external dependencies.
 */
function signJwt(payload: Record<string, unknown>, privateKeyPem: string): string {
  const header = { alg: 'RS256', typ: 'JWT', kid: 'e2e-test-key-1' };

  const encode = (obj: Record<string, unknown> | string): string => {
    const json = typeof obj === 'string' ? obj : JSON.stringify(obj);
    return Buffer.from(json).toString('base64url');
  };

  const headerB64 = encode(header);
  const payloadB64 = encode(payload);
  const signingInput = `${headerB64}.${payloadB64}`;

  const sign = crypto.createSign('RSA-SHA256');
  sign.update(signingInput);
  const signature = sign.sign(privateKeyPem, 'base64url');

  return `${signingInput}.${signature}`;
}

/**
 * Get the JWKS (JSON Web Key Set) for the test key pair.
 * The backend mock auth mode uses this to verify tokens.
 */
export function getJwks(): { keys: Array<Record<string, string>> } {
  const { publicKey } = getKeyPair();
  const keyObj = crypto.createPublicKey(publicKey);
  const jwk = keyObj.export({ format: 'jwk' });

  return {
    keys: [
      {
        ...jwk,
        kid: 'e2e-test-key-1',
        use: 'sig',
        alg: 'RS256',
      } as Record<string, string>,
    ],
  };
}
