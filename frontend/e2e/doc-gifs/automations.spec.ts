/**
 * Doc GIF: automations
 *
 * Shows:
 *   1. Create a Multi Press automation ("Double Tap → Cinema Mode") with 3 actions → run it
 *   2. Duplicate the automation → drag-and-drop reorder the two → delete the copy
 *
 * Device + buttons are pre-created via API so the GIF stays focused on automations.
 * Output: test-results/doc-gifs/automations/*.webm → docs/public/gifs/automations.gif
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

test.describe.serial('doc-gif: automations', () => {
  let context: BrowserContext;
  let page: Page;
  const wsRef: { connection: WebSocketRoute | null } = { connection: null };

  test.beforeAll(async ({ browser, request }) => {
    test.setTimeout(60_000);
    await request.post('/api/reset?keep_irdb=true');

    // Pre-create device + buttons via API
    const devRes = await request.post('/api/devices', {
      data: { name: 'Samsung TV', icon: 'television', buttons: [], target_bridges: [] },
    });
    const device = await devRes.json();
    await request.post(`/api/devices/${device.id}/buttons`, {
      data: { name: 'Power', icon: 'power', is_output: true, code: { protocol: 'nec', address: '0x0707', command: '0x02' } },
    });
    await request.post(`/api/devices/${device.id}/buttons`, {
      data: { name: 'Volume Up', icon: 'volume-plus', is_output: true, code: { protocol: 'nec', address: '0x0707', command: '0x10' } },
    });

    ({ context, page } = await setupDocGifContext(browser, 'automations', wsRef));
    await page.goto('/');
    await delay(600);

    await page.locator('[data-tour-id="nav-Automations"]').click();
    await expect(page.getByRole('heading', { name: 'Automations' })).toBeVisible();
    await delay(600);
  });

  test.afterAll(async () => {
    await context?.close();
  });

  // ── Step 1: Create a Multi Press automation ────────────────────────────────

  test('Step 1: Create Double Tap automation', async () => {
    test.setTimeout(40_000);

    const createBtn = page.locator('[data-tour-id="create-automation-button"]');
    await naturalClick(createBtn);
    await delay(500);

    const modal = page.locator('[data-tour-id="automation-modal"]');

    // Name
    const nameInput = modal.locator('[data-tour-id="automation-name-input"] input');
    await scrollTo(page, nameInput);
    await nameInput.fill('Double Tap → Cinema Mode');
    await delay(600);

    // Trigger type: Multi Press
    const triggerTypeSelect = modal.locator('[data-tour-id="automation-trigger-type"] select');
    await scrollTo(page, triggerTypeSelect);
    await triggerTypeSelect.selectOption('multi');
    await delay(600);

    // Trigger device + button
    const trigger = modal.locator('[data-tour-id="automation-trigger-device-selection"]');
    await scrollTo(page, trigger);
    await trigger.locator('select').first().selectOption({ label: 'Samsung TV' });
    await delay(400);
    await trigger.locator('select').last().selectOption({ label: 'Power' });
    await delay(600);

    // Action 1: Fire HA Event
    const addEventBtn = modal.getByRole('button', { name: /Add (HA )?Event/i });
    await scrollTo(page, addEventBtn);
    await naturalClick(addEventBtn);
    await delay(500);

    const eventInput = modal.locator('[draggable="true"]').last().locator('input').first();
    await scrollTo(page, eventInput);
    await eventInput.fill('cinema_mode');
    await delay(600);

    // Action 2: Delay
    const addDelayBtn = modal.getByRole('button', { name: 'Add Delay' });
    await scrollTo(page, addDelayBtn);
    await naturalClick(addDelayBtn);
    await delay(400);
    const delayInput = modal.locator('[draggable="true"]').last().locator('input').first();
    await scrollTo(page, delayInput);
    await delayInput.fill('1500');
    await delay(500);

    // Action 3: Send IR command
    const addCommandBtn = modal.getByRole('button', { name: 'Add Command' });
    await scrollTo(page, addCommandBtn);
    await naturalClick(addCommandBtn);
    await delay(400);
    const actionCmd = modal.locator('[draggable="true"]').last();
    await scrollTo(page, actionCmd);
    await actionCmd.locator('select').first().selectOption({ label: 'Samsung TV' });
    await delay(400);
    await actionCmd.locator('select').last().selectOption({ label: 'Volume Up' });
    await delay(500);

    // Save
    const saveBtn = modal.locator('[data-tour-id="automation-save-button"]');
    await scrollTo(page, saveBtn);
    await naturalClick(saveBtn);
    await expect(modal).not.toBeVisible();
    await delay(800);

    await expect(
      page.locator('[data-tour-id="automation-card"]', { hasText: 'Double Tap → Cinema Mode' }),
    ).toBeVisible();
    await delay(600);
  });

  // ── Step 2: Run the automation ─────────────────────────────────────────────

  test('Step 2: Trigger automation and watch execution', async () => {
    test.setTimeout(15_000);

    const autoCard = page.locator('[data-tour-id="automation-card"]', { hasText: 'Double Tap → Cinema Mode' });
    await scrollTo(page, autoCard);

    const playBtn = autoCard.locator('button').filter({ has: page.locator('.mdi-play-circle-outline') });
    await naturalClick(playBtn);

    // Watch the visual execution progress (delay action is 1500ms)
    await delay(3500);
  });

  // ── Step 3: Duplicate → reorder → delete copy ─────────────────────────────

  test('Step 3: Duplicate, reorder, and delete automation', async () => {
    test.setTimeout(25_000);

    const autoCard = page.locator('[data-tour-id="automation-card"]', { hasText: 'Double Tap → Cinema Mode' });

    // Hover to reveal action buttons, then hover duplicate specifically
    const dupBtn = autoCard.locator('[data-tour-id="automation-action-buttons"] button').filter({
      has: page.locator('.mdi-content-copy'),
    });
    await scrollTo(page, autoCard);
    await autoCard.hover();
    await delay(400);
    await dupBtn.hover();
    await delay(400);
    await dupBtn.click();
    await delay(800);

    // Wait for copy to appear
    const cards = page.locator('[data-tour-id="automation-card"]');
    await expect(cards).toHaveCount(2);
    await delay(600);

    // Drag-and-drop reorder: move copy above original
    const firstHandle = cards.nth(0).locator('[draggable="true"]');
    const secondHandle = cards.nth(1).locator('[draggable="true"]');
    await scrollTo(page, firstHandle);
    await delay(300);
    await smoothDrag(page, secondHandle, firstHandle);
    await delay(1000);

    // Delete the copy (now at index 1)
    const copyCard = cards.nth(1);
    const delBtn = copyCard.locator('[data-tour-id="automation-action-buttons"] button').filter({
      has: page.locator('.mdi-delete-outline'),
    });
    await copyCard.hover();
    await delay(400);
    await delBtn.hover();
    await delay(400);
    await delBtn.click();
    await delay(400);

    await page.locator('.btn-danger', { hasText: 'Confirm' }).click();
    await delay(800);

    await expect(cards).toHaveCount(1);
    await delay(500);
  });
});
