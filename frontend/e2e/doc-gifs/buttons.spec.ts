/**
 * Doc GIF: buttons
 *
 * Shows:
 *   1. Add a Power button with a NEC code (manual entry)
 *   2. Add a Mute button → quick-learn its code from a remote
 *   3. Drag-and-drop reorder the two buttons
 *   4. Edit Power button capabilities (enable Input / binary_sensor)
 *   5. Send the Power button
 *
 * A device is pre-created via API so the GIF stays focused on buttons.
 * Output: test-results/doc-gifs/buttons/*.webm → docs/public/gifs/buttons.gif
 */

import { test, expect } from '@playwright/test';
import type { BrowserContext, Page, WebSocketRoute } from '@playwright/test';
import { delay, scrollTo, naturalClick, setupDocGifContext, BRIDGE_ID } from './helpers';

test.describe.serial('doc-gif: buttons', () => {
  let context: BrowserContext;
  let page: Page;
  const wsRef: { connection: WebSocketRoute | null } = { connection: null };

  test.beforeAll(async ({ browser, request }) => {
    test.setTimeout(60_000);
    await request.post('/api/reset?keep_irdb=true');

    // Pre-create a device so we can focus the GIF on button interactions.
    await request.post('/api/devices', {
      data: { name: 'Samsung TV', icon: 'television', buttons: [], target_bridges: [] },
    });

    ({ context, page } = await setupDocGifContext(browser, 'buttons', wsRef));
    await page.goto('/');
    await delay(600);
  });

  test.afterAll(async () => {
    await context?.close();
  });

  // ── Step 1: Add Power button with NEC code ────────────────────────────────

  test('Step 1: Add Power button with NEC code', async () => {
    test.setTimeout(25_000);

    const card = page.locator('[data-tour-id="device-card"]', { hasText: 'Samsung TV' });
    await expect(card).toBeVisible();
    await scrollTo(page, card);

    // Expand the card (collapsed by default on API-created devices)
    await card.locator('[data-tour-id="device-expand-toggle"]').click();
    await delay(400);

    await card.locator('[data-tour-id="add-button-to-device"]').click();
    await delay(500);

    const nameInput = page.locator('[data-tour-id="button-name-input"] input');
    await scrollTo(page, nameInput);
    await nameInput.fill('Power');
    await delay(500);

    const protocolSelect = page.locator('[data-tour-id="button-protocol-select"]');
    await scrollTo(page, protocolSelect);
    await protocolSelect.selectOption('nec');
    await delay(500);

    const addressInput = page.locator('[data-tour-id="button-address-input"]');
    await scrollTo(page, addressInput);
    await addressInput.fill('0x0707');
    await delay(400);

    const commandInput = page.locator('[data-tour-id="button-command-input"]');
    await scrollTo(page, commandInput);
    await commandInput.fill('0x02');
    await delay(500);

    // Show capabilities before saving
    const capabilitiesSection = page.locator('[data-tour-id="button-capabilities"]');
    if (await capabilitiesSection.isVisible({ timeout: 1500 })) {
      await scrollTo(page, capabilitiesSection);
      await delay(600);
    }

    const saveBtn = page.locator('[data-tour-id="button-save-button"]');
    await scrollTo(page, saveBtn);
    await naturalClick(saveBtn);

    await expect(card.getByText('Power')).toBeVisible();
    await delay(800);
  });

  // ── Step 2: Add Mute button and quick-learn its code ──────────────────────

  test('Step 2: Add Mute button then quick-learn its code', async () => {
    test.setTimeout(25_000);

    const card = page.locator('[data-tour-id="device-card"]', { hasText: 'Samsung TV' });

    await card.locator('[data-tour-id="add-button-to-device"]').click();
    await delay(500);

    const nameInput = page.locator('[data-tour-id="button-name-input"] input');
    await scrollTo(page, nameInput);
    await nameInput.fill('Mute');
    await delay(500);

    const saveBtn = page.locator('[data-tour-id="button-save-button"]');
    await scrollTo(page, saveBtn);
    await naturalClick(saveBtn);
    await expect(card.getByText('Mute')).toBeVisible();
    await delay(600);

    // Start quick-learn mode
    const quickLearnBtn = page.locator('[data-tour-id="quick-learn-button"]');
    await naturalClick(quickLearnBtn);
    await delay(1500);

    // Simulate IR code received from bridge via WebSocket
    if (wsRef.connection) {
      wsRef.connection.send(JSON.stringify({
        type: 'learned_code',
        bridge_id: BRIDGE_ID,
        bridge: BRIDGE_ID,
        code: {
          protocol: 'nec',
          payload: { address: '0x04', command: '0x0D' },
          raw_tolerance: 20,
        },
      }));
    }
    await delay(1500);

    // Assign learned code to Mute button
    const muteBtn = card.locator('.group', { hasText: 'Mute' });
    await muteBtn.hover();
    await delay(500);
    await muteBtn.locator('.absolute.inset-0').click({ force: true });
    await delay(500);
    await page.mouse.move(0, 0);
    await delay(1000);
  });

  // ── Step 3: Drag-and-drop reorder Power and Mute ──────────────────────────

  test('Step 3: Reorder buttons with drag-and-drop', async () => {
    test.setTimeout(15_000);

    const card = page.locator('[data-tour-id="device-card"]', { hasText: 'Samsung TV' });

    // Hover the first button group to reveal drag handle (opacity-0 → group-hover:opacity-100)
    const powerGroup = card.locator('.group', { hasText: 'Power' }).first();
    const muteGroup  = card.locator('.group', { hasText: 'Mute' }).first();

    await scrollTo(page, powerGroup);
    await powerGroup.hover();
    await delay(400);

    const srcHandle = powerGroup.locator('[draggable="true"]');
    const dstHandle = muteGroup.locator('[draggable="true"]');

    const srcBox = await srcHandle.boundingBox();
    const dstBox = await dstHandle.boundingBox();
    if (srcBox && dstBox) {
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
    await page.mouse.move(0, 0);
    await delay(1000);
  });

  // ── Step 4: Edit Power button — enable Input capability ───────────────────

  test('Step 4: Edit Power button capabilities', async () => {
    test.setTimeout(20_000);

    const card = page.locator('[data-tour-id="device-card"]', { hasText: 'Samsung TV' });
    const powerGroup = card.locator('.group', { hasText: 'Power' }).first();
    await powerGroup.hover();
    await delay(400);

    await powerGroup.getByTitle('Edit Button').click();
    await delay(500);

    const capabilitiesSection = page.locator('[data-tour-id="button-capabilities"]');
    if (await capabilitiesSection.isVisible({ timeout: 2000 })) {
      await scrollTo(page, capabilitiesSection);
      await delay(400);

      const inputToggle = capabilitiesSection.locator('label', { hasText: /input|receive/i }).first();
      if (await inputToggle.isVisible({ timeout: 1500 })) {
        await inputToggle.click();
        await delay(600);
      }
    }

    const saveBtn = page.locator('[data-tour-id="button-save-button"]');
    await scrollTo(page, saveBtn);
    await naturalClick(saveBtn);
    await delay(800);
  });

  // ── Step 5: Send the Power button ─────────────────────────────────────────

  test('Step 5: Send the Power button', async () => {
    test.setTimeout(10_000);

    const card = page.locator('[data-tour-id="device-card"]', { hasText: 'Samsung TV' });
    const powerBtn = card.locator('.group', { hasText: 'Power' }).first();
    await powerBtn.hover();
    await delay(500);

    const sendBtn = card.locator('button[title="Send IR Code"]').first();
    await naturalClick(sendBtn);
    await delay(1200);
  });
});
