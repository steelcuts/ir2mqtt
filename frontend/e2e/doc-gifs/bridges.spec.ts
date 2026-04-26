/**
 * Doc GIF: bridges
 *
 * Shows:
 *   1. Bridge card — online status, IP, TX/RX channels, protocol summary
 *   2. Protocols panel — open → view enabled protocols
 *   3. Echo Suppression settings — open → enable → sub-options animate in → cancel
 *   4. Signal History panel — open → show received & sent code list
 *   5. Add Serial Bridge modal — open → show port/baudrate UI → close
 *
 * The virtual bridge is pre-spawned by generate-doc-gifs.sh (sim-server).
 * IR signals are also pre-injected so the history panel shows real data.
 *
 * Output: test-results/doc-gifs/bridges/*.webm → docs/public/gifs/bridges.gif
 */

import { test, expect } from '@playwright/test';
import type { BrowserContext, Page, WebSocketRoute } from '@playwright/test';
import { delay, scrollTo, naturalClick, setupDocGifContext } from './helpers';

test.describe.serial('doc-gif: bridges', () => {
  let context: BrowserContext;
  let page: Page;
  const wsRef: { connection: WebSocketRoute | null } = { connection: null };
  let bridgeName = '';

  test.beforeAll(async ({ browser, request }) => {
    test.setTimeout(60_000);
    await request.post('/api/reset?keep_irdb=true');

    // Bridge is already online — just read its name for locators
    const res = await request.get('/api/bridges');
    const bridges = await res.json();
    bridgeName = bridges[0]?.name ?? 'Living Room';

    ({ context, page } = await setupDocGifContext(browser, 'bridges', wsRef));
    await page.goto('/');
    await delay(600);

    await page.locator('[data-tour-id="nav-Bridges"]').click();
    await expect(page.locator('[data-tour-id="bridges-table"]')).toBeVisible();
    await delay(800);
  });

  test.afterAll(async () => {
    await context?.close();
  });

  // ── Step 1: View bridge card ───────────────────────────────────────────────

  test('Step 1: View online bridge card', async () => {
    test.setTimeout(10_000);
    await delay(2000);
  });

  // ── Step 2: Protocols panel — view only ───────────────────────────────────

  test('Step 2: Open protocols panel', async () => {
    test.setTimeout(10_000);

    const protocolsBtn = page.locator('[data-tour-id="bridge-protocols"]');
    await naturalClick(protocolsBtn);
    await delay(2000);

    await protocolsBtn.click();
    await delay(600);
  });

  // ── Step 3: Echo Suppression settings ─────────────────────────────────────

  test('Step 3: Open settings panel and configure echo suppression', async () => {
    test.setTimeout(25_000);

    const settingsBtn = page.locator('[data-tour-id="bridge-edit-btn"]');
    await naturalClick(settingsBtn);

    const settingsPanel = page.locator('[data-tour-id="bridge-settings-panel"]');
    await expect(settingsPanel).toBeVisible();
    await delay(800);

    const echoLabel = settingsPanel.locator('label').first();
    await scrollTo(page, echoLabel);
    await echoLabel.click();
    await delay(800);

    await delay(600);

    const smartModeLabel = settingsPanel.locator('label', { hasText: /smart/i });
    await smartModeLabel.click();
    await delay(600);

    const ignoreOthersLabel = settingsPanel.locator('label', { hasText: /others/i });
    if (await ignoreOthersLabel.isVisible({ timeout: 1000 })) {
      await ignoreOthersLabel.click();
      await delay(600);
    }

    const cancelBtn = settingsPanel.locator('button', { hasText: /cancel/i });
    await naturalClick(cancelBtn);
    await delay(600);
  });

  // ── Step 4: Signal History panel ──────────────────────────────────────────

  test('Step 4: Open signal history', async () => {
    test.setTimeout(15_000);

    const historyBtn = page.locator('[data-tour-id="bridge-history-btn"]');
    await naturalClick(historyBtn);
    await delay(800);

    const historyPanel = page.locator('.card', { hasText: bridgeName })
      .locator('.grid-cols-1.md\\:grid-cols-2').first();
    if (await historyPanel.isVisible({ timeout: 2000 })) {
      await scrollTo(page, historyPanel);
    }

    await delay(2500);

    await historyBtn.click();
    await delay(600);
  });

  // ── Step 5: Add Serial Bridge modal ───────────────────────────────────────

  test('Step 5: Show Add Serial Bridge modal', async () => {
    test.setTimeout(15_000);

    const addSerialBtn = page.locator('[data-tour-id="add-serial-bridge-btn"]');
    await naturalClick(addSerialBtn);
    await delay(500);

    const modal = page.locator('[data-tour-id="add-serial-bridge-modal"]');
    await expect(modal).toBeVisible();
    await delay(800);

    // Scroll through modal content so viewer sees port + baudrate + test button
    const baudrateSelect = modal.locator('select').last();
    await scrollTo(page, baudrateSelect);
    await delay(1200);

    // Close the modal
    await modal.locator('button:has(.mdi-close)').click();
    await delay(600);
  });
});
