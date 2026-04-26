/**
 * Integration tests — Send IR Code
 *
 * Tests the full send chain using the simulator's loopback feature:
 *   Frontend (click Send) → POST /api/devices/{id}/buttons/{id}/trigger
 *   → Backend looks up target bridge → publishes MQTT command
 *   → Simulator receives command → loopback: re-publishes on received topic
 *   → Backend processes received → appends to last_sent / last_received
 *   → WS bridges_updated → Frontend history shows the sent code
 *
 * The loopback trick turns a one-way send verification into a fully observable
 * round-trip without requiring external MQTT tooling.
 */

import { test, expect } from './fixtures';

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function createDeviceWithButton(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
  name: string,
  targetBridgeId: string,
) {
  const devRes = await request.post(`${backendUrl}/api/devices`, {
    headers: { 'Content-Type': 'application/json' },
    data: {
      name,
      icon: 'television',
      buttons: [],
      target_bridges: [targetBridgeId],
    },
  });
  expect(devRes.ok()).toBeTruthy();
  const device = await devRes.json();

  const btnRes = await request.post(`${backendUrl}/api/devices/${device.id}/buttons`, {
    headers: { 'Content-Type': 'application/json' },
    data: {
      name: 'Power',
      icon: 'power',
      is_output: true,
      code: { protocol: 'nec', payload: { address: '0x04', command: '0x08' } },
    },
  });
  expect(btnRes.ok()).toBeTruthy();
  const button = await btnRes.json();

  return { device, button };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

test.describe('Send IR Code (Integration)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ resetAll }) => {
    await resetAll();
  });

  // ─── Basic send ──────────────────────────────────────────────────────────

  test('send button triggers MQTT command and code appears in bridge sent-history', async ({
    page, sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-send-basic-1' });
    await createDeviceWithButton(request, backendUrl, 'Send Test TV', bridge.id);

    await page.goto('/');
    const card = page.locator('[data-tour-id="device-card"]', { hasText: 'Send Test TV' });
    await expect(card).toBeVisible({ timeout: 8_000 });

    // Expand the device card (not auto-expanded when loaded from DB)
    await card.locator('[data-tour-id="device-expand-toggle"]').click();
    const sendBtn = card.locator('button[title="Send IR Code"]');
    await expect(sendBtn).not.toBeDisabled({ timeout: 5_000 });

    // Intercept the trigger API call
    const triggerReq = page.waitForRequest(r => r.url().includes('/trigger') && r.method() === 'POST');
    await sendBtn.click();
    const req = await triggerReq;
    expect(req.url()).toContain('/trigger');

    // Navigate to Bridges page and check sent history
    await page.goto('/#Bridges');
    const bridgeCard = page.locator(`.card:has-text("${bridge.name}")`);
    await expect(bridgeCard).toBeVisible({ timeout: 8_000 });

    await bridgeCard.getByTitle(/History/).click();

    // The "Sent" section should contain the nec badge
    await expect(bridgeCard.locator('h4').filter({ hasText: 'Sent' }).first()).toBeVisible();
    await expect(bridgeCard.getByText('nec', { exact: true }).first()).toBeVisible({ timeout: 10_000 });
  });

  test('loopback: sent code re-appears in received history', async ({
    page, sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-send-loopback-1' });
    await createDeviceWithButton(request, backendUrl, 'Loopback TV', bridge.id);

    // Enable loopback on the bridge — any "send" command echoes back as "received"
    await sim.setLoopback(true);

    await page.goto('/');
    const card = page.locator('[data-tour-id="device-card"]', { hasText: 'Loopback TV' });
    await expect(card).toBeVisible({ timeout: 8_000 });

    await card.locator('[data-tour-id="device-expand-toggle"]').click();
    const sendBtn = card.locator('button[title="Send IR Code"]');
    await expect(sendBtn).not.toBeDisabled({ timeout: 5_000 });
    await sendBtn.click();

    // Give MQTT roundtrip time: send → MQTT command → simulator loopback → received MQTT → backend → WS
    await new Promise(r => setTimeout(r, 1_500));

    // Check received history on the bridge
    await page.goto('/#Bridges');
    const bridgeCard = page.locator(`.card:has-text("${bridge.name}")`);
    await expect(bridgeCard).toBeVisible({ timeout: 8_000 });

    await bridgeCard.getByTitle(/History/).click();

    // Both sections should contain the nec code
    const necBadges = bridgeCard.getByText('nec', { exact: true });
    await expect(necBadges.first()).toBeVisible({ timeout: 10_000 });
    // Loopback means it also shows in received (at least 2 nec badges total)
    await expect(necBadges.nth(1)).toBeVisible({ timeout: 5_000 });

    // Clean up loopback state
    await sim.setLoopback(false);
  });

  // ─── Disabled states ──────────────────────────────────────────────────────

  test('send button is enabled in broadcast mode when online bridges exist', async ({
    page, sim, request, backendUrl,
  }) => {
    await sim.spawn({ bridge_id: 'test-send-disabled-1' });

    // Create device WITHOUT target_bridges — no target = broadcast to all online bridges
    const devRes = await request.post(`${backendUrl}/api/devices`, {
      headers: { 'Content-Type': 'application/json' },
      data: { name: 'No Target TV', icon: 'television', buttons: [] },
    });
    expect(devRes.ok()).toBeTruthy();
    const device = await devRes.json();
    await request.post(`${backendUrl}/api/devices/${device.id}/buttons`, {
      headers: { 'Content-Type': 'application/json' },
      data: { name: 'Power', icon: 'power', is_output: true, code: { protocol: 'nec', payload: { address: '0x04', command: '0x08' } } },
    });

    await page.goto('/');
    const card = page.locator('[data-tour-id="device-card"]', { hasText: 'No Target TV' });
    await expect(card).toBeVisible({ timeout: 8_000 });

    await card.locator('[data-tour-id="device-expand-toggle"]').click();
    const sendBtn = card.locator('button[title="Send IR Code"]');
    await expect(sendBtn).not.toBeDisabled({ timeout: 5_000 });
  });

  test('send button is disabled when target bridge is offline', async ({
    page, sim, request, backendUrl,
  }) => {
    // Spawn then immediately delete — bridge will be offline/gone
    const bridge = await sim.spawn({ bridge_id: 'test-send-offline-1' });
    await createDeviceWithButton(request, backendUrl, 'Offline Target TV', bridge.id);

    // Take the bridge offline by deleting it from simulator
    await request.delete(`http://localhost:8088/bridges/${bridge.id}`);
    // Also remove it from backend
    await request.delete(`${backendUrl}/api/bridges/${bridge.id}`);

    await page.goto('/');
    const card = page.locator('[data-tour-id="device-card"]', { hasText: 'Offline Target TV' });
    await expect(card).toBeVisible({ timeout: 8_000 });

    await card.locator('[data-tour-id="device-expand-toggle"]').click();
    const sendBtn = card.locator('button[title="Send IR Code"]');
    await expect(sendBtn).toBeDisabled({ timeout: 5_000 });
  });

  // ─── Multi-bridge send ────────────────────────────────────────────────────

  test('send with multiple target bridges triggers command on each bridge', async ({
    sim, request, backendUrl,
  }) => {
    const bridge1 = await sim.spawn({ bridge_id: 'test-send-multi-1' });
    const bridge2 = await sim.spawn({ bridge_id: 'test-send-multi-2' });

    // Create device targeting both bridges
    const devRes = await request.post(`${backendUrl}/api/devices`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        name: 'Multi Bridge TV',
        icon: 'television',
        buttons: [],
        target_bridges: [bridge1.id, bridge2.id],
      },
    });
    expect(devRes.ok()).toBeTruthy();
    const device = await devRes.json();

    const btnRes = await request.post(`${backendUrl}/api/devices/${device.id}/buttons`, {
      headers: { 'Content-Type': 'application/json' },
      data: { name: 'Power', icon: 'power', is_output: true, code: { protocol: 'nec', payload: { address: '0x04', command: '0x08' } } },
    });
    expect(btnRes.ok()).toBeTruthy();
    const button = await btnRes.json();

    // Trigger via API
    const triggerRes = await request.post(
      `${backendUrl}/api/devices/${device.id}/buttons/${button.id}/trigger`,
    );
    if (!triggerRes.ok()) {
      const body = await triggerRes.text();
      throw new Error(`Trigger failed ${triggerRes.status()}: ${body}`);
    }

    // Give MQTT time to deliver to both bridges
    await new Promise(r => setTimeout(r, 800));

    // Check both bridges have a sent entry
    const bridgesRes = await request.get(`${backendUrl}/api/bridges`);
    expect(bridgesRes.ok()).toBeTruthy();
    const bridges: Array<{ id: string; last_sent?: unknown[] }> = await bridgesRes.json();

    const b1 = bridges.find(b => b.id === bridge1.id);
    const b2 = bridges.find(b => b.id === bridge2.id);

    expect(b1?.last_sent?.length).toBeGreaterThan(0);
    expect(b2?.last_sent?.length).toBeGreaterThan(0);
  });
});
