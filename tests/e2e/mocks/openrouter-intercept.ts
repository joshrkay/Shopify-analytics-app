/**
 * Playwright route interceptor for OpenRouter (LLM) API calls.
 *
 * OpenRouter is called server-side for AI features, but this
 * interceptor handles any frontend-side LLM requests or
 * streaming responses.
 */
import { Page, Route } from '@playwright/test';

const OPENROUTER_PATTERNS = [
  '**/openrouter.ai/**',
  '**/localhost:9003/**',
];

export async function interceptOpenRouter(page: Page): Promise<void> {
  for (const pattern of OPENROUTER_PATTERNS) {
    await page.route(pattern, async (route: Route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          choices: [
            {
              message: {
                role: 'assistant',
                content: 'This is a mock AI response for E2E testing.',
              },
            },
          ],
          model: 'mock-model',
          usage: { prompt_tokens: 10, completion_tokens: 20 },
        }),
      });
    });
  }
}
