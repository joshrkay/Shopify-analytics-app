/**
 * Navigation Route Coverage Contract Test
 *
 * Catches dead navigate() calls — hardcoded paths passed to navigate()
 * that have no matching <Route> in App.tsx.
 *
 * This test caught the /dashboards/templates dead route in DashboardList.tsx
 * (removed in commit 5f872b4) and prevents the same class of bug recurring.
 *
 * Pattern: static file analysis, no rendering required.
 */

import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const srcRoot = path.resolve(__dirname, '..');

function readSrc(relativePath: string): string {
  return fs.readFileSync(path.join(srcRoot, relativePath), 'utf8');
}

/** Extract all <Route path="..."> values defined in App.tsx */
function extractDefinedRoutes(appContent: string): string[] {
  const matches = [...appContent.matchAll(/path="([^"*][^"]*)"/g)];
  return matches.map((m) => m[1]);
}

/**
 * Extract hardcoded navigate('/...') calls from a file.
 * Captures the path portion up to query strings, hash, or closing quote.
 */
function extractNavigateCalls(content: string): string[] {
  const matches = [...content.matchAll(/\bnavigate\s*\(\s*['"`](\/[^'"`?#)]+)/g)];
  return matches.map((m) => m[1]);
}

/**
 * Convert a Route path pattern to a regex that matches concrete paths.
 * e.g. /dashboards/:dashboardId/edit → /dashboards/[^/]+/edit
 */
function routePatternToRegex(routePath: string): RegExp {
  const escaped = routePath.replace(/:[^/]+/g, '[^/]+');
  return new RegExp(`^${escaped}$`);
}

describe('navigation route coverage', () => {
  it('every hardcoded navigate() path targets a route defined in App.tsx', () => {
    const appContent = readSrc('App.tsx');
    const definedRoutes = extractDefinedRoutes(appContent);

    // Collect all .tsx files under pages/ (including subdirectories)
    function collectTsx(dir: string): string[] {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      const files: string[] = [];
      for (const entry of entries) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) files.push(...collectTsx(full));
        else if (entry.name.endsWith('.tsx')) files.push(full);
      }
      return files;
    }

    const pageFiles = collectTsx(path.join(srcRoot, 'pages'));

    const deadRoutes: string[] = [];

    for (const filePath of pageFiles) {
      const content = fs.readFileSync(filePath, 'utf8');
      const relativeName = path.relative(srcRoot, filePath);
      const calls = extractNavigateCalls(content);

      for (const target of calls) {
        const matched = definedRoutes.some((route) =>
          routePatternToRegex(route).test(target) || route === target
        );
        if (!matched) {
          deadRoutes.push(`  ${relativeName}: navigate('${target}')`);
        }
      }
    }

    expect(
      deadRoutes,
      `Dead navigate() calls found (no matching <Route> in App.tsx):\n${deadRoutes.join('\n')}`
    ).toHaveLength(0);
  });

  it('App.tsx defines the routes required by inter-page links', () => {
    const appContent = readSrc('App.tsx');
    const required = [
      '/home',
      '/insights',
      '/orders',
      '/attribution',
      '/alerts',
      '/budget-pacing',
      '/cohort-analysis',
      '/settings',
      '/data-sources',
      '/dashboards',
      '/billing/checkout',
      '/whats-new',
      '/ai-consultant',
      '/sync',
    ];

    for (const route of required) {
      expect(appContent, `App.tsx is missing required route: ${route}`).toContain(
        `path="${route}"`
      );
    }
  });
});
