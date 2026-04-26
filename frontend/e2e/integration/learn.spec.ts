/**
 * Integration tests — Learn IR Code flow
 *
 * Tests the full learn chain:
 *   Frontend (Start Learning) → POST /api/learn → Backend sets learning_bridges
 *   → Simulator injects IR code → MQTT received topic
 *   → Backend processes code → WS learned_code event → Frontend updates
 */

import { test, expect } from './fixtures';

// Helper to set up a device and open the learn modal
async function setupLearnFlow(page: import('@playwright/test').Page, request: import('@playwright/test').APIRequestContext, backendUrl: string) {
  // Create a device via the backend API directly (faster than UI clicks)
  const devRes = await request.post(`${backendUrl}/api/devices`, {
    headers: { 'Content-Type': 'application/json' },
    data: { name: 'Learn Test TV', icon: 'television', buttons: [] },
  });
  expect(devRes.ok()).toBeTruthy();
  const device = await devRes.json();

  // Add a button to learn into
  const btnRes = await request.post(`${backendUrl}/api/devices/${device.id}/buttons`, {
    headers: { 'Content-Type': 'application/json' },
    data: { name: 'Power', icon: 'power', is_output: true },
  });
  expect(btnRes.ok()).toBeTruthy();
  const button = await btnRes.json();

  return { device, button };
}

test.describe('Learn IR Code Flow (Integration)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ resetAll }) => {
    await resetAll();
  });

  // ─── Happy path ───────────────────────────────────────────────────────────

  test('learned code arrives in frontend after simulated remote press', async ({ page, sim, request, backendUrl }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-learn-1' });
    await setupLearnFlow(page, request, backendUrl);

    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Devices' })).toBeVisible();
    // Wait for device to render
    await expect(page.locator('[data-tour-id="device-card"]', { hasText: 'Learn Test TV' })).toBeVisible();

    // Click "Configure Learn" button to open the learn modal
    await page.locator('[data-tour-id="configure-learn-button"]').click();
    await expect(page.getByRole('heading', { name: 'Learn IR Code' })).toBeVisible();

    // The online bridge should appear in BridgeSelector
    await expect(page.getByText(bridge.name)).toBeVisible({ timeout: 8_000 });

    // Start learning — this POSTs to /api/learn and sets backend into listening mode
    const learnReq = page.waitForRequest(r => r.url().includes('/api/learn'));
    await page.getByRole('button', { name: 'Start Learning' }).click();
    await learnReq;

    // Quick-learn button should show "Listening..."
    await expect(page.locator('[data-tour-id="quick-learn-button"]')).toContainText('Listening...', { timeout: 8_000 });

    // Simulate a remote press from the bridge
    await sim.inject({
      bridge_id: bridge.id,
      protocol: 'nec',
      address: '0x04',
      command: '0x08',
    });

    // Backend processes the MQTT message and sends learned_code via WebSocket
    // The quick-learn button should revert from "Listening..." back to normal
    await expect(page.locator('[data-tour-id="quick-learn-button"]')).not.toContainText('Listening...', { timeout: 12_000 });
  });

  test('learned code can be assigned to a button', async ({ page, sim, request, backendUrl }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-learn-assign-1' });
    const { button } = await setupLearnFlow(page, request, backendUrl);

    await page.goto('/');
    await expect(page.locator('[data-tour-id="device-card"]', { hasText: 'Learn Test TV' })).toBeVisible();

    // Start learning via quick-learn button (directly, without opening modal)
    const learnReq = page.waitForRequest(r => r.url().includes('/api/learn'));
    await page.locator('[data-tour-id="quick-learn-button"]').click();
    await learnReq;

    // Inject code from simulator
    await sim.inject({
      bridge_id: bridge.id,
      protocol: 'nec',
      address: '0x04',
      command: '0x08',
    });

    // Wait for learned_code WS event to arrive (quick-learn button resets)
    await expect(page.locator('[data-tour-id="quick-learn-button"]'))
      .not.toContainText('Listening...', { timeout: 12_000 });

    // Expand the device card (loaded from DB, not auto-expanded)
    const deviceCard = page.locator('[data-tour-id="device-card"]', { hasText: 'Learn Test TV' });
    await deviceCard.locator('[data-tour-id="device-expand-toggle"]').click();
    const powerBtn = deviceCard.locator('.group', { hasText: 'Power' }).first();
    await powerBtn.hover();

    // Click to assign the learned code to this button
    await expect(powerBtn.locator('text=Assign Code')).toBeVisible({ timeout: 5_000 });
    await powerBtn.locator('text=Assign Code').click();

    // Verify the button now shows the protocol
    await expect(powerBtn.getByText('nec')).toBeVisible({ timeout: 5_000 });
    void button; // button ID used for setup — assignment verified via UI
  });

  // ─── Bridge selector ──────────────────────────────────────────────────────

  test('learn modal shows only online bridges', async ({ page, sim, request, backendUrl }) => {
    const onlineBridge = await sim.spawn({ bridge_id: 'test-learn-online-1' });
    await setupLearnFlow(page, request, backendUrl);

    await page.goto('/');
    await page.locator('[data-tour-id="configure-learn-button"]').click();
    await expect(page.getByRole('heading', { name: 'Learn IR Code' })).toBeVisible();

    // Online bridge should be visible in the BridgeSelector
    await expect(page.getByText(onlineBridge.name)).toBeVisible({ timeout: 8_000 });

    // Start Learning should NOT be disabled
    await expect(page.getByRole('button', { name: 'Start Learning' })).not.toBeDisabled();
  });

  test('learning on a specific bridge sends bridge ID as query param', async ({ page, sim, request, backendUrl }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-learn-specific-1' });
    await setupLearnFlow(page, request, backendUrl);

    await page.goto('/');
    await page.locator('[data-tour-id="configure-learn-button"]').click();
    await expect(page.getByRole('heading', { name: 'Learn IR Code' })).toBeVisible();

    // Select only this bridge in the BridgeSelector
    const checkbox = page.locator('input[type="checkbox"]').first();
    await checkbox.check();

    let learnUrl = '';
    const learnReq = page.waitForRequest(r => {
      if (r.url().includes('/api/learn')) {
        learnUrl = r.url();
        return true;
      }
      return false;
    });

    await page.getByRole('button', { name: 'Start Learning' }).click();
    await learnReq;

    expect(learnUrl).toContain(`bridges=${bridge.id}`);
  });

  // ─── No bridges ───────────────────────────────────────────────────────────

  test('start learning is disabled when no bridge is online', async ({ page, request, backendUrl }) => {
    // No bridge spawned
    await setupLearnFlow(page, request, backendUrl);

    await page.goto('/');
    await page.locator('[data-tour-id="configure-learn-button"]').click();
    await expect(page.getByRole('heading', { name: 'Learn IR Code' })).toBeVisible();

    // Should show disabled select with "No bridges online"
    await expect(page.locator('select[disabled]')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start Learning' })).toBeDisabled();
  });
});
