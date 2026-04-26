/**
 * Shared helpers for doc-gif Playwright specs.
 *
 * All specs run against a real backend + simulated bridge started by
 * generate-doc-gifs.sh — no REST or WebSocket mocks are needed.
 *
 * The only WS override is mqtt_status → connected: true so the UI reliably
 * shows the green MQTT indicator regardless of connection timing.
 */

import type { Browser, BrowserContext, Page, WebSocketRoute } from '@playwright/test';

// ── Utilities ──────────────────────────────────────────────────────────────────

export const delay = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));

/** URL of the sim-server control API (set by generate-doc-gifs.sh). */
export const SIM_URL = process.env.SIM_URL ?? 'http://127.0.0.1:8091';

/** ID of the pre-spawned virtual bridge (set by generate-doc-gifs.sh). */
export const BRIDGE_ID = process.env.BRIDGE_ID ?? 'living-room-node';

/** Scroll an element into the center of the viewport smoothly, then wait briefly. */
export async function scrollTo(page: Page, locator: import('@playwright/test').Locator) {
  await locator.evaluate(el => el.scrollIntoView({ block: 'center', behavior: 'smooth' }));
  await page.waitForTimeout(400);
}

/** Scroll into view → short pause → click. Makes interactions look intentional in the recording.
 *  Uses scrollIntoViewIfNeeded so it works on any element and never hangs. */
export async function naturalClick(locator: import('@playwright/test').Locator, pauseMs = 300) {
  await locator.scrollIntoViewIfNeeded();
  await delay(pauseMs);
  await locator.click();
}

// ── Context factory ────────────────────────────────────────────────────────────

/**
 * Create a browser context that records video into `test-results/doc-gifs/{gifName}/`.
 *
 * WebSocket events are proxied to the real backend. mqtt_status is overridden to
 * always report connected=true for a consistent UI appearance in recordings.
 *
 * @param wsRef  Populated with the WebSocketRoute once connected — lets tests
 *               inject WS events (e.g. learned_code for the quick-learn demo).
 */
export async function setupDocGifContext(
  browser: Browser,
  gifName: string,
  wsRef: { connection: WebSocketRoute | null },
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({
    recordVideo: { dir: `test-results/doc-gifs/${gifName}/` },
    viewport: { width: 1280, height: 720 },
  });

  const page = await context.newPage();

  // Proxy WS to real backend; override mqtt_status so the UI always shows green.
  await page.routeWebSocket('**/ws/events', ws => {
    wsRef.connection = ws;
    const server = ws.connectToServer();

    ws.onMessage(msg => server.send(msg));

    server.onMessage(message => {
      try {
        const data = JSON.parse(message as string);
        if (data.type === 'mqtt_status') {
          data.connected = true;
          ws.send(JSON.stringify(data));
          return;
        }
      } catch { /* ignore binary frames */ }
      ws.send(message);
    });

    ws.send(JSON.stringify({ type: 'mqtt_status', connected: true }));
  });

  return { context, page };
}
