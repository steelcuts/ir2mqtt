/**
 * Doc GIF: devices
 *
 * Shows:
 *   1. Create a device ("Living Room TV")
 *   2. Show MQTT topics for the device
 *   3. Edit the device name → "LG TV"
 *   4. Duplicate the device (hover highlights duplicate button)
 *   5. Drag-and-drop reorder the two devices
 *   6. Delete the copy
 *
 * Output: test-results/doc-gifs/devices/*.webm → docs/public/gifs/devices.gif
 */

import { test, expect } from '@playwright/test';
import type { BrowserContext, Page, WebSocketRoute } from '@playwright/test';
import { delay, scrollTo, naturalClick, setupDocGifContext } from './helpers';

/** Smooth drag from one element's center to another's center. */
async function smoothDrag(page: Page, src: import('@playwright/test').Locator, dst: import('@playwright/test').Locator) {
  const srcBox = await src.boundingBox();
  const dstBox = await dst.boundingBox();
  if (!srcBox || !dstBox) return;
  const sx = srcBox.x + srcBox.width / 2;
  const sy = srcBox.y + srcBox.height / 2;
  const dx = dstBox.x + dstBox.width / 2;
  const dy = dstBox.y + dstBox.height / 2;
  await page.mouse.move(sx, sy);
  await delay(200);
  await page.mouse.down();
  await delay(300);
  const steps = 20;
  for (let i = 1; i <= steps; i++) {
    await page.mouse.move(sx + (dx - sx) * i / steps, sy + (dy - sy) * i / steps);
    await delay(25);
  }
  await delay(200);
  await page.mouse.up();
}

test.describe.serial('doc-gif: devices', () => {
  let context: BrowserContext;
  let page: Page;
  const wsRef: { connection: WebSocketRoute | null } = { connection: null };

  test.beforeAll(async ({ browser, request }) => {
    test.setTimeout(60_000);
    await request.post('/api/reset?keep_irdb=true');
    ({ context, page } = await setupDocGifContext(browser, 'devices', wsRef));
    await page.goto('/');
    await delay(800);
  });

  test.afterAll(async () => {
    await context?.close();
  });

  // ── Step 1: Create a device ────────────────────────────────────────────────

  test('Step 1: Create a device', async () => {
    test.setTimeout(20_000);

    const addBtn = page.locator('[data-tour-id="add-device-button"]');
    await scrollTo(page, addBtn);
    await naturalClick(addBtn);
    await delay(400);

    const nameInput = page.locator('[data-tour-id="device-name-input"] input');
    await scrollTo(page, nameInput);
    await nameInput.fill('Living Room TV');
    await delay(600);

    const saveBtn = page.locator('[data-tour-id="device-save-button"]');
    await scrollTo(page, saveBtn);
    await naturalClick(saveBtn);

    await expect(page.locator('[data-tour-id="device-modal-cancel"]')).not.toBeVisible();
    await expect(page.locator('[data-tour-id="device-card"]', { hasText: 'Living Room TV' })).toBeVisible();
    await delay(800);

    // Add buttons via API so the MQTT topics panel shows real content in Step 2
    const res = await page.request.get('/api/devices');
    const devList = await res.json();
    const dev = devList.find((d: { name: string; id: string }) => d.name === 'Living Room TV');
    if (dev) {
      await page.request.post(`/api/devices/${dev.id}/buttons`, {
        data: { name: 'Power', icon: 'power', is_output: true, code: { protocol: 'nec', address: '0x0707', command: '0x02' } },
      });
      await page.request.post(`/api/devices/${dev.id}/buttons`, {
        data: { name: 'Volume Up', icon: 'volume-plus', is_output: true, code: { protocol: 'nec', address: '0x0707', command: '0x10' } },
      });
    }
  });

  // ── Step 2: Show MQTT topics ───────────────────────────────────────────────

  test('Step 2: Show MQTT topics for the device', async () => {
    test.setTimeout(15_000);

    const card = page.locator('[data-tour-id="device-card"]', { hasText: 'Living Room TV' });
    const topicsBtn = card.locator('[data-tour-id="device-show-topics"]');
    await naturalClick(topicsBtn);
    await delay(1800); // Hold so viewer can read the MQTT topics

    await topicsBtn.click();
    await delay(600);
  });

  // ── Step 3: Edit the device name ──────────────────────────────────────────

  test('Step 3: Edit the device name', async () => {
    test.setTimeout(20_000);

    const card = page.locator('[data-tour-id="device-card"]', { hasText: 'Living Room TV' });
    await card.locator('[data-tour-id="device-card-header"]').hover();
    await delay(400);
    await card.locator('[data-tour-id="device-edit-button"]').click();
    await delay(400);

    const nameInput = page.locator('[data-tour-id="device-name-input"] input');
    await scrollTo(page, nameInput);
    await nameInput.fill('LG TV');
    await delay(600);

    const saveBtn = page.locator('[data-tour-id="device-save-button"]');
    await scrollTo(page, saveBtn);
    await naturalClick(saveBtn);

    await expect(page.locator('[data-tour-id="device-modal-cancel"]')).not.toBeVisible();
    await expect(page.locator('[data-tour-id="device-card"]', { hasText: 'LG TV' })).toBeVisible();
    await delay(800);
  });

  // ── Step 4: Duplicate the device (explicit hover on button) ───────────────

  test('Step 4: Duplicate the device', async () => {
    test.setTimeout(15_000);

    const card = page.locator('[data-tour-id="device-card"]').filter({ hasText: 'LG TV' }).filter({ hasNotText: 'LG TV (Copy)' });
    await card.locator('[data-tour-id="device-card-header"]').hover();
    await delay(500);

    // Hover specifically on the duplicate button so it highlights in the recording
    const dupBtn = card.locator('[data-tour-id="device-duplicate-button"]');
    await dupBtn.hover();
    await delay(500);
    await dupBtn.click();

    await expect(page.locator('[data-tour-id="device-card"]', { hasText: 'LG TV (Copy)' })).toBeVisible();
    await delay(800);
  });

  // ── Step 5: Drag-and-drop reorder ─────────────────────────────────────────

  test('Step 5: Reorder devices with drag-and-drop', async () => {
    test.setTimeout(15_000);

    const cards = page.locator('[data-tour-id="device-card"]');
    // .last() selects the card-level drag handle (bottom-right) — cards with buttons
    // also contain per-button drag handles (top-left) that would otherwise match first.
    const firstHandle = cards.nth(0).locator('[draggable="true"]').last();
    const secondHandle = cards.nth(1).locator('[draggable="true"]').last();

    await scrollTo(page, firstHandle);
    await delay(400);

    await smoothDrag(page, secondHandle, firstHandle);
    await delay(1000);
  });

  // ── Step 6: Delete the copy ────────────────────────────────────────────────

  test('Step 6: Delete the copy', async () => {
    test.setTimeout(15_000);

    const copy = page.locator('[data-tour-id="device-card"]', { hasText: 'LG TV (Copy)' });
    await copy.locator('[data-tour-id="device-card-header"]').hover();
    await delay(400);

    const delBtn = copy.locator('[data-tour-id="device-delete-button"]');
    await delBtn.hover();
    await delay(400);
    await delBtn.click();
    await delay(500);

    await page.locator('.btn-danger', { hasText: 'Confirm' }).click();
    await delay(1000);

    await expect(copy).not.toBeVisible();
    await delay(500);
  });
});
