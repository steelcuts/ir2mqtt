/**
 * Integration tests — Input Buttons & allowed_bridges filter
 *
 * Tests the IR receive path for input-configured buttons:
 *   - Buttons marked is_input receive IR codes from bridges
 *   - allowed_bridges controls which bridges can trigger a device's buttons
 *   - allowed_bridges: ["any"] lets any bridge trigger
 *   - Injecting from a disallowed bridge must NOT fire automations
 *   - known_code_received WS event fires (and flashes button) when a code matches
 */

import { test, expect } from './fixtures';

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Polls GET /api/bridges until bridge.last_sent has at least minCount entries. */
async function waitForSent(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
  bridgeId: string,
  minCount = 1,
  timeoutMs = 6_000,
): Promise<unknown[]> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const res = await request.get(`${backendUrl}/api/bridges`);
    if (res.ok()) {
      const bridges: Array<{ id: string; last_sent?: unknown[] }> = await res.json();
      const bridge = bridges.find(b => b.id === bridgeId);
      if ((bridge?.last_sent?.length ?? 0) >= minCount) return bridge!.last_sent!;
    }
    await new Promise(r => setTimeout(r, 300));
  }
  throw new Error(`Bridge ${bridgeId} did not accumulate ${minCount} sent entry/entries within ${timeoutMs}ms`);
}

interface DeviceSetupResult {
  deviceId: string;
  triggerButtonId: string;
  actionButtonId: string;
}

/**
 * Creates a device with:
 *   - triggerBtn: is_input button with a known IR code (NEC 0x04/0x08)
 *   - actionBtn:  is_output button for the automation action
 *
 * `allowedBridges` controls which bridges can receive IR for this device.
 */
async function createInputDevice(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
  targetBridgeId: string,
  allowedBridges: string[],
): Promise<DeviceSetupResult> {
  const devRes = await request.post(`${backendUrl}/api/devices`, {
    headers: { 'Content-Type': 'application/json' },
    data: {
      name: `Input Test TV ${Date.now()}`,
      icon: 'television',
      buttons: [],
      target_bridges: [targetBridgeId],
      allowed_bridges: allowedBridges,
    },
  });
  expect(devRes.ok()).toBeTruthy();
  const device = await devRes.json();

  const trigBtnRes = await request.post(`${backendUrl}/api/devices/${device.id}/buttons`, {
    headers: { 'Content-Type': 'application/json' },
    data: {
      name: 'Power Trigger',
      icon: 'power',
      is_input: true,
      is_output: false,
      code: { protocol: 'nec', payload: { address: '0x04', command: '0x08' } },
    },
  });
  expect(trigBtnRes.ok()).toBeTruthy();
  const trigBtn = await trigBtnRes.json();

  const actBtnRes = await request.post(`${backendUrl}/api/devices/${device.id}/buttons`, {
    headers: { 'Content-Type': 'application/json' },
    data: {
      name: 'Volume Up',
      icon: 'volume-plus',
      is_output: true,
      code: { protocol: 'nec', payload: { address: '0x01', command: '0x02' } },
    },
  });
  expect(actBtnRes.ok()).toBeTruthy();
  const actBtn = await actBtnRes.json();

  return { deviceId: device.id, triggerButtonId: trigBtn.id, actionButtonId: actBtn.id };
}

async function createAutomation(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
  deviceId: string,
  triggerButtonId: string,
  actionButtonId: string,
  name = 'Input Automation',
): Promise<string> {
  const res = await request.post(`${backendUrl}/api/automations`, {
    headers: { 'Content-Type': 'application/json' },
    data: {
      name,
      enabled: true,
      triggers: [{ type: 'single', device_id: deviceId, button_id: triggerButtonId }],
      actions: [{ type: 'ir_send', device_id: deviceId, button_id: actionButtonId }],
    },
  });
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  return body.id;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

test.describe('Input Buttons & allowed_bridges (Integration)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ resetAll }) => {
    await resetAll();
  });

  // ── allowed_bridges: specific bridge ──────────────────────────────────────

  test('IR code from allowed bridge triggers automation via input button', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-input-allowed-1' });

    const { deviceId, triggerButtonId, actionButtonId } = await createInputDevice(
      request, backendUrl, bridge.id, [bridge.id],
    );
    await createAutomation(request, backendUrl, deviceId, triggerButtonId, actionButtonId);

    // Inject the trigger code on the allowed bridge
    await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x04', command: '0x08' });

    // Automation must fire and send the action code
    const sent = await waitForSent(request, backendUrl, bridge.id);
    expect(sent.length).toBeGreaterThan(0);

    const entry = sent[0] as { payload?: { address?: string; command?: string } };
    expect(entry.payload?.address).toBe('0x01');
    expect(entry.payload?.command).toBe('0x02');
  });

  test('IR code from disallowed bridge does NOT trigger automation', async ({
    sim, request, backendUrl,
  }) => {
    const allowedBridge = await sim.spawn({ bridge_id: 'test-input-disallowed-a' });
    const otherBridge  = await sim.spawn({ bridge_id: 'test-input-disallowed-b' });

    // Device only allowed to receive from allowedBridge
    const { deviceId, triggerButtonId, actionButtonId } = await createInputDevice(
      request, backendUrl, allowedBridge.id, [allowedBridge.id],
    );
    await createAutomation(request, backendUrl, deviceId, triggerButtonId, actionButtonId);

    // Inject the trigger code on the OTHER (disallowed) bridge
    await sim.inject({ bridge_id: otherBridge.id, protocol: 'nec', address: '0x04', command: '0x08' });

    // Wait generously — automation must NOT fire
    await new Promise(r => setTimeout(r, 1_500));

    const res = await request.get(`${backendUrl}/api/bridges`);
    const bridges: Array<{ id: string; last_sent?: unknown[] }> = await res.json();
    const b = bridges.find(br => br.id === allowedBridge.id);
    expect(b?.last_sent?.length ?? 0).toBe(0);
  });

  // ── allowed_bridges: "any" ────────────────────────────────────────────────

  test('allowed_bridges "any" lets any bridge trigger the automation', async ({
    sim, request, backendUrl,
  }) => {
    const bridgeA = await sim.spawn({ bridge_id: 'test-input-any-a' });
    const bridgeB = await sim.spawn({ bridge_id: 'test-input-any-b' });

    // Device allows any bridge to trigger it; target bridgeA for the action send
    const { deviceId, triggerButtonId, actionButtonId } = await createInputDevice(
      request, backendUrl, bridgeA.id, ['any'],
    );
    await createAutomation(request, backendUrl, deviceId, triggerButtonId, actionButtonId);

    // Inject on bridge B — allowed_bridges "any" should still match
    await sim.inject({ bridge_id: bridgeB.id, protocol: 'nec', address: '0x04', command: '0x08' });

    // The action code must be sent to bridgeA (the device's target)
    const sent = await waitForSent(request, backendUrl, bridgeA.id);
    expect(sent.length).toBeGreaterThan(0);
  });

  // ── is_input: true still feeds automations ────────────────────────────────

  test('is_input button fires automations the same as is_output buttons', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-input-isinput-1' });

    // Create trigger device with an explicit is_input trigger button
    const trigDevRes = await request.post(`${backendUrl}/api/devices`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        name: 'Input Only TV',
        icon: 'television',
        buttons: [],
        target_bridges: [bridge.id],
        allowed_bridges: [bridge.id],
      },
    });
    const trigDev = await trigDevRes.json();

    const trigBtnRes = await request.post(`${backendUrl}/api/devices/${trigDev.id}/buttons`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        name: 'Power In',
        icon: 'power',
        is_input: true,
        is_output: false,   // pure input — cannot be sent
        code: { protocol: 'nec', payload: { address: '0x04', command: '0x08' } },
      },
    });
    const trigBtn = await trigBtnRes.json();

    // Action device (separate, to avoid ambiguity)
    const actDevRes = await request.post(`${backendUrl}/api/devices`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        name: 'Input Action TV',
        icon: 'television',
        buttons: [],
        target_bridges: [bridge.id],
      },
    });
    const actDev = await actDevRes.json();

    const actBtnRes = await request.post(`${backendUrl}/api/devices/${actDev.id}/buttons`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        name: 'Vol Up',
        icon: 'volume-plus',
        is_output: true,
        code: { protocol: 'nec', payload: { address: '0x01', command: '0x02' } },
      },
    });
    const actBtn = await actBtnRes.json();

    await request.post(`${backendUrl}/api/automations`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        name: 'Input Triggers Action',
        enabled: true,
        triggers: [{ type: 'single', device_id: trigDev.id, button_id: trigBtn.id }],
        actions: [{ type: 'ir_send', device_id: actDev.id, button_id: actBtn.id }],
      },
    });

    // Inject trigger code
    await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x04', command: '0x08' });

    // Automation must fire
    const sent = await waitForSent(request, backendUrl, bridge.id);
    expect(sent.length).toBeGreaterThan(0);
    const entry = sent[0] as { payload?: { address?: string } };
    expect(entry.payload?.address).toBe('0x01');
  });

  // ── No code on button → no match ─────────────────────────────────────────

  test('input button without code never matches received IR codes', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-input-nocode-1' });

    const devRes = await request.post(`${backendUrl}/api/devices`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        name: 'No Code TV',
        icon: 'television',
        buttons: [],
        target_bridges: [bridge.id],
        allowed_bridges: [bridge.id],
      },
    });
    const dev = await devRes.json();

    // Button without code
    const trigBtnRes = await request.post(`${backendUrl}/api/devices/${dev.id}/buttons`, {
      headers: { 'Content-Type': 'application/json' },
      data: { name: 'Power', icon: 'power', is_input: true, is_output: false },
    });
    const trigBtn = await trigBtnRes.json();

    // Action button
    const actBtnRes = await request.post(`${backendUrl}/api/devices/${dev.id}/buttons`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        name: 'Vol Up',
        icon: 'volume-plus',
        is_output: true,
        code: { protocol: 'nec', payload: { address: '0x01', command: '0x02' } },
      },
    });
    const actBtn = await actBtnRes.json();

    await request.post(`${backendUrl}/api/automations`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        name: 'No Code Auto',
        enabled: true,
        triggers: [{ type: 'single', device_id: dev.id, button_id: trigBtn.id }],
        actions: [{ type: 'ir_send', device_id: dev.id, button_id: actBtn.id }],
      },
    });

    await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x04', command: '0x08' });

    // Must NOT trigger automation
    await new Promise(r => setTimeout(r, 1_500));
    const res = await request.get(`${backendUrl}/api/bridges`);
    const bridges: Array<{ id: string; last_sent?: unknown[] }> = await res.json();
    const b = bridges.find(br => br.id === bridge.id);
    expect(b?.last_sent?.length ?? 0).toBe(0);
  });

  // ── UI: button flashes on known_code_received ─────────────────────────────

  test('known_code_received WS event flashes the matching button in the UI', async ({
    page, sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-input-flash-1' });

    const devRes = await request.post(`${backendUrl}/api/devices`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        name: 'Flash TV',
        icon: 'television',
        buttons: [],
        target_bridges: [bridge.id],
        allowed_bridges: [bridge.id],
      },
    });
    const dev = await devRes.json();

    await request.post(`${backendUrl}/api/devices/${dev.id}/buttons`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        name: 'Power',
        icon: 'power',
        is_input: true,
        is_output: false,
        code: { protocol: 'nec', payload: { address: '0x04', command: '0x08' } },
      },
    });

    // Navigate to devices, expand the card
    await page.goto('/');
    const card = page.locator('[data-tour-id="device-card"]', { hasText: 'Flash TV' });
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.locator('[data-tour-id="device-expand-toggle"]').click();

    const powerBtn = card.locator('.group', { hasText: 'Power' }).first();
    await expect(powerBtn).toBeVisible({ timeout: 5_000 });

    // Inject the matching code — should trigger known_code_received WS → button flash
    await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x04', command: '0x08' });

    // The outer button div should briefly gain the flash-receive class (lasts ~300ms)
    await expect(powerBtn).toHaveClass(/flash-receive/, { timeout: 5_000 });
  });
});
