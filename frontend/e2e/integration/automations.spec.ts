/**
 * Integration tests — Automation Engine
 *
 * Tests the full automation chain:
 *   IR inject → backend matches button code → process_ir_event
 *   → automation trigger fires → ir_send action → MQTT command to bridge
 *   → bridge sent history updated → WS bridges_updated → frontend reflects state
 *
 * Also covers:
 *   - API-triggered automations
 *   - Disabled automations (must NOT fire)
 *   - Multi-action automations (delay + send)
 */

import { test, expect } from './fixtures';

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Creates a device with two buttons:
 *   - triggerBtn: stores the IR code that the simulator will inject (NEC 0x04/0x08)
 *   - actionBtn:  stores a different IR code (NEC 0x01/0x02) that the automation sends
 *
 * Both devices target the given bridge so trigger detection and send both work.
 */
async function createAutomationDevices(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
  bridgeId: string,
) {
  // Trigger device — receives IR code 0x04/0x08 from the bridge
  const triggerDevRes = await request.post(`${backendUrl}/api/devices`, {
    headers: { 'Content-Type': 'application/json' },
    data: {
      name: 'Automation Trigger TV',
      icon: 'television',
      buttons: [],
      target_bridges: [bridgeId],
      allowed_bridges: [bridgeId],
    },
  });
  expect(triggerDevRes.ok()).toBeTruthy();
  const triggerDev = await triggerDevRes.json();

  const triggerBtnRes = await request.post(`${backendUrl}/api/devices/${triggerDev.id}/buttons`, {
    headers: { 'Content-Type': 'application/json' },
    data: {
      name: 'Power',
      icon: 'power',
      is_output: false,
      code: { protocol: 'nec', payload: { address: '0x04', command: '0x08' } },
    },
  });
  expect(triggerBtnRes.ok()).toBeTruthy();
  const triggerBtn = await triggerBtnRes.json();

  // Action device — sends IR code 0x01/0x02 to the bridge when automation fires
  const actionDevRes = await request.post(`${backendUrl}/api/devices`, {
    headers: { 'Content-Type': 'application/json' },
    data: {
      name: 'Automation Action TV',
      icon: 'television',
      buttons: [],
      target_bridges: [bridgeId],
    },
  });
  expect(actionDevRes.ok()).toBeTruthy();
  const actionDev = await actionDevRes.json();

  const actionBtnRes = await request.post(`${backendUrl}/api/devices/${actionDev.id}/buttons`, {
    headers: { 'Content-Type': 'application/json' },
    data: {
      name: 'Volume Up',
      icon: 'volume-plus',
      is_output: true,
      code: { protocol: 'nec', payload: { address: '0x01', command: '0x02' } },
    },
  });
  expect(actionBtnRes.ok()).toBeTruthy();
  const actionBtn = await actionBtnRes.json();

  return { triggerDev, triggerBtn, actionDev, actionBtn };
}

async function createAutomation(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
  opts: {
    name: string;
    enabled?: boolean;
    triggerDeviceId: string;
    triggerButtonId: string;
    actions: Array<{ type: string; device_id?: string; button_id?: string; delay_ms?: number }>;
  },
) {
  const res = await request.post(`${backendUrl}/api/automations`, {
    headers: { 'Content-Type': 'application/json' },
    data: {
      name: opts.name,
      enabled: opts.enabled ?? true,
      triggers: [{ type: 'single', device_id: opts.triggerDeviceId, button_id: opts.triggerButtonId }],
      actions: opts.actions,
    },
  });
  expect(res.ok()).toBeTruthy();
  return res.json();
}

/** Polls GET /api/bridges until bridge.last_sent has at least minCount entries. */
async function waitForSent(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
  bridgeId: string,
  minCount = 1,
  timeoutMs = 8_000,
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

// ─── Tests ────────────────────────────────────────────────────────────────────

test.describe('Automation Engine (Integration)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ resetAll }) => {
    await resetAll();
  });

  // ── Full IR chain: inject → trigger → send ────────────────────────────────

  test('IR code injection triggers automation and sends IR command to bridge', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-auto-trigger-1' });
    const { triggerDev, triggerBtn, actionDev, actionBtn } = await createAutomationDevices(
      request, backendUrl, bridge.id,
    );

    await createAutomation(request, backendUrl, {
      name: 'Power → Volume Up',
      triggerDeviceId: triggerDev.id,
      triggerButtonId: triggerBtn.id,
      actions: [{ type: 'ir_send', device_id: actionDev.id, button_id: actionBtn.id }],
    });

    // Inject the trigger code — backend matches it to triggerBtn → fires automation
    await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x04', command: '0x08' });

    // Automation fires synchronously via asyncio queue — wait for the send to arrive
    const sent = await waitForSent(request, backendUrl, bridge.id);
    expect(sent.length).toBeGreaterThan(0);

    // The sent entry must be the action code (0x01/0x02), not the trigger code (0x04/0x08)
    const sentEntry = sent[0] as { protocol?: string; payload?: { address?: string; command?: string } };
    expect(sentEntry.protocol).toBe('nec');
    expect(sentEntry.payload?.address).toBe('0x01');
    expect(sentEntry.payload?.command).toBe('0x02');
  });

  test('automation trigger fires and sent code appears in bridge history panel in the UI', async ({
    page, sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-auto-ui-1' });
    const { triggerDev, triggerBtn, actionDev, actionBtn } = await createAutomationDevices(
      request, backendUrl, bridge.id,
    );

    await createAutomation(request, backendUrl, {
      name: 'UI Trigger Test',
      triggerDeviceId: triggerDev.id,
      triggerButtonId: triggerBtn.id,
      actions: [{ type: 'ir_send', device_id: actionDev.id, button_id: actionBtn.id }],
    });

    // Navigate to bridges before injecting so the WS update arrives live
    await page.goto('/#Bridges');
    const bridgeCard = page.locator(`.card:has-text("${bridge.name}")`);
    await expect(bridgeCard).toBeVisible({ timeout: 10_000 });

    await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x04', command: '0x08' });

    // Give MQTT → automation → send → WS time to propagate
    await new Promise(r => setTimeout(r, 1_200));

    await bridgeCard.getByTitle(/History/).click();
    const sentSection = bridgeCard.locator('h4').filter({ hasText: 'Sent' });
    await expect(sentSection).toBeVisible({ timeout: 8_000 });
    await expect(bridgeCard.getByText('nec', { exact: true }).first()).toBeVisible({ timeout: 8_000 });
  });

  // ── Disabled automation must not fire ─────────────────────────────────────

  test('disabled automation does not fire when trigger code is injected', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-auto-disabled-1' });
    const { triggerDev, triggerBtn, actionDev, actionBtn } = await createAutomationDevices(
      request, backendUrl, bridge.id,
    );

    await createAutomation(request, backendUrl, {
      name: 'Disabled Auto',
      enabled: false,
      triggerDeviceId: triggerDev.id,
      triggerButtonId: triggerBtn.id,
      actions: [{ type: 'ir_send', device_id: actionDev.id, button_id: actionBtn.id }],
    });

    await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x04', command: '0x08' });

    // Wait a generous amount — if a send were to happen, it would have by now
    await new Promise(r => setTimeout(r, 1_500));

    const bridgesRes = await request.get(`${backendUrl}/api/bridges`);
    const bridges: Array<{ id: string; last_sent?: unknown[] }> = await bridgesRes.json();
    const b = bridges.find(b => b.id === bridge.id);
    expect(b?.last_sent?.length ?? 0).toBe(0);
  });

  // ── API trigger ───────────────────────────────────────────────────────────

  test('automation triggered via API sends IR command to bridge', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-auto-api-1' });
    const { triggerDev, triggerBtn, actionDev, actionBtn } = await createAutomationDevices(
      request, backendUrl, bridge.id,
    );

    const automation = await createAutomation(request, backendUrl, {
      name: 'API Triggered Auto',
      triggerDeviceId: triggerDev.id,
      triggerButtonId: triggerBtn.id,
      actions: [{ type: 'ir_send', device_id: actionDev.id, button_id: actionBtn.id }],
    });

    // Trigger directly via REST API (no IR inject needed)
    const triggerRes = await request.post(`${backendUrl}/api/automations/${automation.id}/trigger`);
    expect(triggerRes.ok()).toBeTruthy();

    const sent = await waitForSent(request, backendUrl, bridge.id);
    expect(sent.length).toBeGreaterThan(0);
  });

  test('API trigger shows automation_progress event in frontend', async ({
    page, sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-auto-progress-1' });
    const { triggerDev, triggerBtn, actionDev, actionBtn } = await createAutomationDevices(
      request, backendUrl, bridge.id,
    );

    const automation = await createAutomation(request, backendUrl, {
      name: 'Progress Test Auto',
      triggerDeviceId: triggerDev.id,
      triggerButtonId: triggerBtn.id,
      // Small delay gives the frontend time to receive the "running" WS event
      actions: [
        { type: 'delay', delay_ms: 300 },
        { type: 'ir_send', device_id: actionDev.id, button_id: actionBtn.id },
      ],
    });

    await page.goto('/#Automations');
    await expect(page.getByRole('heading', { name: 'Automations' })).toBeVisible();
    await expect(page.locator('[data-tour-id="automation-card"]', { hasText: automation.name })).toBeVisible();

    // Trigger via API — the 300ms delay action keeps it "running" long enough for WS to arrive
    await request.post(`${backendUrl}/api/automations/${automation.id}/trigger`);

    // The card should show a running indicator while the delay action executes
    const autoCard = page.locator('[data-tour-id="automation-card"]', { hasText: automation.name });
    await expect(autoCard.locator('.animate-pulse, [class*="running"], [class*="progress"]'))
      .toBeVisible({ timeout: 5_000 });
  });

  // ── Multi-action: delay + send ────────────────────────────────────────────

  test('multi-action automation executes delay then sends IR command', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-auto-multi-1' });
    const { triggerDev, triggerBtn, actionDev, actionBtn } = await createAutomationDevices(
      request, backendUrl, bridge.id,
    );

    const automation = await createAutomation(request, backendUrl, {
      name: 'Delay + Send Auto',
      triggerDeviceId: triggerDev.id,
      triggerButtonId: triggerBtn.id,
      actions: [
        { type: 'delay', delay_ms: 200 },
        { type: 'ir_send', device_id: actionDev.id, button_id: actionBtn.id },
      ],
    });

    const t0 = Date.now();
    await request.post(`${backendUrl}/api/automations/${automation.id}/trigger`);

    // Wait for the send — it must take at least 200ms (the delay action)
    const sent = await waitForSent(request, backendUrl, bridge.id);
    const elapsed = Date.now() - t0;

    expect(sent.length).toBeGreaterThan(0);
    expect(elapsed).toBeGreaterThanOrEqual(200);
  });

  // ── Multiple triggers in one burst ────────────────────────────────────────

  test('two inject calls produce two automation fires and two sent entries', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-auto-multi-fire-1' });
    const { triggerDev, triggerBtn, actionDev, actionBtn } = await createAutomationDevices(
      request, backendUrl, bridge.id,
    );

    const automation = await createAutomation(request, backendUrl, {
      name: 'Double Fire Auto',
      triggerDeviceId: triggerDev.id,
      triggerButtonId: triggerBtn.id,
      actions: [{ type: 'ir_send', device_id: actionDev.id, button_id: actionBtn.id }],
    });

    void automation; // id not needed — bridge history is the ground truth

    await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x04', command: '0x08' });
    await new Promise(r => setTimeout(r, 600));
    await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x04', command: '0x08' });

    const sent = await waitForSent(request, backendUrl, bridge.id, 2);
    expect(sent.length).toBeGreaterThanOrEqual(2);
  });
});
