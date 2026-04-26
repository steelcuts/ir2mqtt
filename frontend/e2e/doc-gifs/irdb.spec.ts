/**
 * Doc GIF: irdb
 *
 * Shows:
 *   1. Import multiple buttons into a device via DeviceModal → Browse DB (multi-mode)
 *      Search "Samsung" → open a file → select all → import → device gets all buttons
 *   2. Browse standalone IRDB page → set send target (sim bridge) → send a test command
 *
 * Output: test-results/doc-gifs/irdb/*.webm → docs/public/gifs/irdb.gif
 */

import { test, expect } from '@playwright/test';
import type { BrowserContext, Page, WebSocketRoute } from '@playwright/test';
import { delay, scrollTo, naturalClick, setupDocGifContext } from './helpers';

/** Drill into IRDB folders/files until a file is open (buttons grid visible). */
async function navigateToFile(page: Page, searchTerm: string) {
  // Use search to jump straight to matching files
  const searchInput = page.locator('[data-tour-id="irdb-search-input"] input');
  if (await searchInput.isVisible({ timeout: 3000 })) {
    await searchInput.fill(searchTerm);
    await delay(800);

    // Click the first file result.
    // Search results render in a separate container (v-else-if="searchQuery"), NOT inside
    // irdb-file-list — use the file icon class to distinguish files from folder items.
    const firstFile = page.locator('.group').filter({ has: page.locator('.mdi-file-document-outline') }).first();
    if (await firstFile.isVisible({ timeout: 5000 })) {
      await firstFile.evaluate(el => el.scrollIntoView({ block: 'center', behavior: 'smooth' }));
      await delay(300);
      await firstFile.click();
      await delay(800);
      return;
    }

    // Clear search and fall back to folder drill
    await searchInput.fill('');
    await delay(400);
  }

  // Fallback: drill through folders until a file opens
  for (let i = 0; i < 6; i++) {
    const file = page.locator('.group:has(.mdi-file-document-outline)').first();
    const folder = page.locator('.group:has(.mdi-folder)').first();
    try {
      await page.waitForSelector(
        '.group:has(.mdi-file-document-outline), .group:has(.mdi-folder)',
        { state: 'visible', timeout: 6000 },
      );
    } catch { break; }

    if (await file.isVisible()) {
      await file.evaluate(el => el.scrollIntoView({ block: 'center', behavior: 'smooth' }));
      await delay(300);
      await file.click();
      await delay(800);
      break;
    } else if (await folder.isVisible()) {
      await folder.evaluate(el => el.scrollIntoView({ block: 'center', behavior: 'smooth' }));
      await delay(300);
      await folder.click();
      await delay(500);
    } else {
      break;
    }
  }
}

test.describe.serial('doc-gif: irdb', () => {
  let context: BrowserContext;
  let page: Page;
  const wsRef: { connection: WebSocketRoute | null } = { connection: null };

  test.beforeAll(async ({ browser, request }) => {
    test.setTimeout(120_000);

    await request.post('/api/reset?keep_irdb=true');

    // Ensure IR database is available — generate-doc-gifs.sh pre-syncs it, but when
    // running the spec directly we trigger the sync ourselves if needed.
    const statusRes = await request.get('/api/irdb/status');
    const { exists } = await statusRes.json();
    if (!exists) {
      console.log('Syncing IR database (this takes ~60s on first run)...');
      await request.post('/api/irdb/sync', { data: { flipper: true, probono: true } });
      await expect(async () => {
        const res = await request.get('/api/irdb/status');
        expect((await res.json()).exists).toBe(true);
      }).toPass({ timeout: 90_000 });
    }

    ({ context, page } = await setupDocGifContext(browser, 'irdb', wsRef));
    await page.goto('/');
    await delay(600);
  });

  test.afterAll(async () => {
    await context?.close();
  });

  // ── Step 1: Import multiple buttons via DeviceModal ────────────────────────

  test('Step 1: Import buttons from IR database into device', async () => {
    test.setTimeout(40_000);

    // Open the "Add Device" modal — "Browse DB" is only shown in create mode (v-if="!isEditMode")
    const addDeviceBtn = page.locator('[data-tour-id="add-device-button"]');
    await naturalClick(addDeviceBtn);
    await delay(400);

    // Fill in a device name
    const nameInput = page.locator('[data-tour-id="device-name-input"] input');
    await scrollTo(page, nameInput);
    await nameInput.fill('Samsung TV');
    await delay(500);

    // Click "Browse DB" → opens IrDbPicker in multi-select mode
    const browseDbBtn = page.locator('[data-tour-id="device-init-section"]').getByRole('button', { name: /browse db/i });
    await scrollTo(page, browseDbBtn);
    await naturalClick(browseDbBtn);
    await delay(800);

    // Navigate to a Samsung TV file using search
    await navigateToFile(page, 'Samsung_TV');
    await delay(600);

    // All buttons are pre-selected when a file opens — pause so viewer sees them, then import
    const importBtn = page.locator('button', { hasText: /^import/i }).last();
    await scrollTo(page, importBtn);
    await delay(1000);
    await naturalClick(importBtn);
    await delay(800);

    // Save the new device
    const saveBtn = page.locator('[data-tour-id="device-save-button"]');
    await scrollTo(page, saveBtn);
    await naturalClick(saveBtn);
    await expect(page.locator('[data-tour-id="device-modal-cancel"]')).not.toBeVisible({ timeout: 5000 });
    await delay(800);

    // Expand the new card to show imported buttons
    const card = page.locator('[data-tour-id="device-card"]', { hasText: 'Samsung TV' });
    await expect(card).toBeVisible();
    await card.locator('[data-tour-id="device-expand-toggle"]').click();
    await delay(800);
  });

  // ── Step 2: Browse IRDB + send a test command ──────────────────────────────

  test('Step 2: Browse IRDB standalone and send a test command', async () => {
    test.setTimeout(30_000);

    // Navigate to the standalone IR Database page
    await page.locator('[data-tour-id="nav-IR_DB"]').click();
    await delay(600);

    // Navigate to a Samsung TV file (browse mode — buttons show send icon on hover)
    await navigateToFile(page, 'Samsung_TV');
    await delay(600);

    // Open target selector and pick the sim bridge transmitter
    const targetBtn = page.locator('[data-tour-id="target-selector-btn"]');
    if (await targetBtn.isVisible({ timeout: 3000 })) {
      await naturalClick(targetBtn);
      await delay(600);

      // The dropdown panel is .absolute.z-50 (above the z-40 backdrop close-div).
      // BridgeSelector → TreeView renders checkboxes for each transmitter channel.
      const firstCheckbox = page.locator('input[type="checkbox"]').first();
      if (await firstCheckbox.isVisible({ timeout: 2000 })) {
        await firstCheckbox.check();
        await delay(400);
      }

      // Close dropdown: force-click the target button (bypasses z-40 backdrop interception)
      await targetBtn.click({ force: true });
      await delay(400);
    }

    // Hover a button to reveal the send icon, then click it
    const firstDbBtn = page.locator('[data-tour-id="irdb-first-button"]');
    await firstDbBtn.waitFor({ state: 'visible', timeout: 8000 });
    await firstDbBtn.evaluate(el => el.scrollIntoView({ block: 'center', behavior: 'smooth' }));
    await delay(400);
    await firstDbBtn.hover();
    await delay(600);

    const sendIcon = firstDbBtn.locator('button:has(.mdi-send), button:has(.mdi-loading)').first();
    if (await sendIcon.isVisible({ timeout: 1500 })) {
      await sendIcon.click({ force: true });
      await delay(1200);
    }

    await delay(600);
  });
});
