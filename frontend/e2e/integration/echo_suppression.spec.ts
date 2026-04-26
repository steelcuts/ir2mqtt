/**
 * Integration tests — Echo Suppression
 *
 * Tests the per-bridge echo suppression feature:
 *   - A code sent TO a bridge and immediately received back (loopback) is suppressed
 *     and does NOT appear in last_received or trigger automations
 *   - Smart suppression (default): only the exact same code is suppressed;
 *     a different code received within the timeout window is NOT suppressed
 *   - After the timeout window expires the next received code is NOT suppressed
 *   - Without echo suppression enabled the loopback code appears normally in last_received
 *
 * The simulator's loopback mode is used to generate realistic echo traffic:
 * any IR command the backend sends to a bridge is re-published back by the
 * simulator on the bridge's "received" topic, exactly as real hardware does.
 */

import { test, expect } from './fixtures';

// ─── Helpers ──────────────────────────────────────────────────────────────────

interface BridgeSettings {
  echo_enabled: boolean;
  echo_timeout?: number;
  echo_smart?: boolean;
  echo_ignore_self?: boolean;
  echo_ignore_others?: boolean;
}

async function setBridgeSettings(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
  bridgeId: string,
  settings: BridgeSettings,
): Promise<void> {
  const res = await request.put(
    `${backendUrl}/api/bridges/${encodeURIComponent(bridgeId)}/settings`,
    {
      headers: { 'Content-Type': 'application/json' },
      data: settings,
    },
  );
  expect(res.ok()).toBeTruthy();
}

async function createDeviceWithButton(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
  bridgeId: string,
  code: { protocol: string; address: string; command: string } = { protocol: 'nec', address: '0x04', command: '0x08' },
): Promise<{ deviceId: string; buttonId: string }> {
  const devRes = await request.post(`${backendUrl}/api/devices`, {
    headers: { 'Content-Type': 'application/json' },
    data: {
      name: `Echo Test Device ${Date.now()}`,
      icon: 'television',
      buttons: [],
      target_bridges: [bridgeId],
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
      code: { protocol: code.protocol, payload: { address: code.address, command: code.command } },
    },
  });
  expect(btnRes.ok()).toBeTruthy();
  const button = await btnRes.json();

  return { deviceId: device.id, buttonId: button.id };
}

async function triggerButton(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
  deviceId: string,
  buttonId: string,
): Promise<void> {
  const res = await request.post(
    `${backendUrl}/api/devices/${deviceId}/buttons/${buttonId}/trigger`,
  );
  expect(res.ok()).toBeTruthy();
}

/**
 * Polls GET /api/bridges until the bridge's last_received has at least minCount entries.
 * Throws if the deadline is exceeded.
 */
async function waitForReceived(
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
      const bridges: Array<{ id: string; last_received?: unknown[] }> = await res.json();
      const bridge = bridges.find(b => b.id === bridgeId);
      if ((bridge?.last_received?.length ?? 0) >= minCount) return bridge!.last_received!;
    }
    await new Promise(r => setTimeout(r, 300));
  }
  throw new Error(`Bridge ${bridgeId} did not accumulate ${minCount} received entry/entries within ${timeoutMs}ms`);
}

// ─── Tests ────────────────────────────────────────────────────────────────────

test.describe('Echo Suppression (Integration)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ resetAll }) => {
    await resetAll();
  });

  // ── Core suppression behaviour ────────────────────────────────────────────

  test('loopback echo is suppressed when echo suppression is enabled', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-echo-basic-1' });

    // Enable echo suppression with self-echo detection
    await setBridgeSettings(request, backendUrl, bridge.id, {
      echo_enabled: true,
      echo_timeout: 500,
      echo_smart: true,
      echo_ignore_self: true,
    });

    // Enable loopback: the simulator will re-publish any sent command as a received event
    await sim.setLoopback(true);
    try {
      const { deviceId, buttonId } = await createDeviceWithButton(request, backendUrl, bridge.id);
      await triggerButton(request, backendUrl, deviceId, buttonId);

      // The echo suppression marks the loopback as ignored but still logs it
      const received = await waitForReceived(request, backendUrl, bridge.id, 1);
      expect((received[0] as { ignored?: boolean }).ignored).toBe(true);
    } finally {
      await sim.setLoopback(false);
    }
  });

  test('without echo suppression the loopback code appears in received history', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-echo-disabled-1' });

    // Explicitly disable echo suppression (default is already off, but be explicit)
    await setBridgeSettings(request, backendUrl, bridge.id, {
      echo_enabled: false,
    });

    await sim.setLoopback(true);
    try {
      const { deviceId, buttonId } = await createDeviceWithButton(request, backendUrl, bridge.id);
      await triggerButton(request, backendUrl, deviceId, buttonId);

      // With no suppression the loopback echo must appear in last_received
      const received = await waitForReceived(request, backendUrl, bridge.id, 1);
      expect(received.length).toBeGreaterThan(0);
    } finally {
      await sim.setLoopback(false);
    }
  });

  // ── Smart mode (code matching) ────────────────────────────────────────────

  test('smart suppression: only matching code is suppressed, different code passes through', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-echo-smart-1' });

    // Enable smart echo suppression — only exact code match is suppressed
    await setBridgeSettings(request, backendUrl, bridge.id, {
      echo_enabled: true,
      echo_timeout: 500,
      echo_smart: true,
      echo_ignore_self: true,
    });

    // Send code A (0x04/0x08) — records in sent_codes_history, NO loopback
    const { deviceId, buttonId } = await createDeviceWithButton(request, backendUrl, bridge.id, {
      protocol: 'nec', address: '0x04', command: '0x08',
    });
    await triggerButton(request, backendUrl, deviceId, buttonId);

    // Immediately inject code B (0x01/0x02) — different code, must NOT be suppressed
    await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x01', command: '0x02' });

    const received = await waitForReceived(request, backendUrl, bridge.id, 1);
    const entry = received[0] as { payload?: { address?: string; command?: string } };
    // Received code is B, not A — smart suppression left it through
    expect(entry?.payload?.address).toBe('0x01');
    expect(entry?.payload?.command).toBe('0x02');
  });

  test('smart suppression: exact same code injected within timeout is suppressed', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-echo-smart-2' });

    await setBridgeSettings(request, backendUrl, bridge.id, {
      echo_enabled: true,
      echo_timeout: 500,
      echo_smart: true,
      echo_ignore_self: true,
    });

    // Send code A — records it
    const { deviceId, buttonId } = await createDeviceWithButton(request, backendUrl, bridge.id, {
      protocol: 'nec', address: '0x04', command: '0x08',
    });
    await triggerButton(request, backendUrl, deviceId, buttonId);

    // Immediately inject the exact same code A — should be suppressed
    await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x04', command: '0x08' });

    const received = await waitForReceived(request, backendUrl, bridge.id, 1);
    expect((received[0] as { ignored?: boolean }).ignored).toBe(true);
  });

  // ── Timeout window ────────────────────────────────────────────────────────

  test('echo no longer suppressed after timeout window expires', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-echo-timeout-1' });

    // Use a short 200ms timeout
    await setBridgeSettings(request, backendUrl, bridge.id, {
      echo_enabled: true,
      echo_timeout: 200,
      echo_smart: true,
      echo_ignore_self: true,
    });

    // Send code — records timestamp in sent_codes_history
    const { deviceId, buttonId } = await createDeviceWithButton(request, backendUrl, bridge.id, {
      protocol: 'nec', address: '0x04', command: '0x08',
    });
    await triggerButton(request, backendUrl, deviceId, buttonId);

    // Wait longer than the suppression timeout
    await new Promise(r => setTimeout(r, 400));

    // Now inject the same code — timeout has passed, should NOT be suppressed
    await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x04', command: '0x08' });

    const received = await waitForReceived(request, backendUrl, bridge.id, 1);
    expect(received.length).toBeGreaterThan(0);
  });

  // ── Automations ───────────────────────────────────────────────────────────

  test('echoed code does not trigger automation when echo suppression is enabled', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-echo-auto-1' });

    await setBridgeSettings(request, backendUrl, bridge.id, {
      echo_enabled: true,
      echo_timeout: 500,
      echo_smart: true,
      echo_ignore_self: true,
    });

    // Trigger device/button: the code we will send AND inject
    const trigDevRes = await request.post(`${backendUrl}/api/devices`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        name: 'Echo Auto Trigger TV',
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
        name: 'Power',
        icon: 'power',
        is_output: false,
        code: { protocol: 'nec', payload: { address: '0x04', command: '0x08' } },
      },
    });
    const trigBtn = await trigBtnRes.json();

    // Action device/button (what the automation would send)
    const actDevRes = await request.post(`${backendUrl}/api/devices`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        name: 'Echo Auto Action TV',
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

    // Create automation: trigger code → send action code
    await request.post(`${backendUrl}/api/automations`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        name: 'Echo Should Not Fire',
        enabled: true,
        triggers: [{ type: 'single', device_id: trigDev.id, button_id: trigBtn.id }],
        actions: [{ type: 'ir_send', device_id: actDev.id, button_id: actBtn.id }],
      },
    });

    // Send the trigger code to the bridge (records in sent_codes_history)
    await request.post(
      `${backendUrl}/api/devices/${trigDev.id}/buttons/${trigBtn.id}/trigger`,
    );

    // Small delay so the send is committed to history before the inject arrives
    await new Promise(r => setTimeout(r, 100));

    // Inject the same code — should be suppressed; automation must NOT fire
    await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x04', command: '0x08' });

    await new Promise(r => setTimeout(r, 1_200));

    // Check that the action code was NOT sent (automation did not fire)
    const bridgesRes = await request.get(`${backendUrl}/api/bridges`);
    const bridges: Array<{ id: string; last_sent?: unknown[] }> = await bridgesRes.json();
    const b = bridges.find(br => br.id === bridge.id);

    // last_sent should only contain the original trigger send, not an automation-fired send.
    // Filter to only action code (0x01/0x02) entries — there should be none.
    const actionSends = (b?.last_sent ?? []).filter(
      (s: unknown) => {
        const entry = s as { payload?: { address?: string } };
        return entry?.payload?.address === '0x01';
      },
    );
    expect(actionSends.length).toBe(0);
  });

  // ── cross-bridge (ignore_others) ──────────────────────────────────────────

  test('ignore_others: code sent to bridge A and received on bridge B is suppressed', async ({
    sim, request, backendUrl,
  }) => {
    const bridgeA = await sim.spawn({ bridge_id: 'test-echo-cross-a' });
    const bridgeB = await sim.spawn({ bridge_id: 'test-echo-cross-b' });

    // Enable cross-talk suppression on bridge B (the receiver)
    await setBridgeSettings(request, backendUrl, bridgeB.id, {
      echo_enabled: true,
      echo_timeout: 500,
      echo_smart: true,
      echo_ignore_self: false,   // not self — bridgeA sent it
      echo_ignore_others: true,  // suppress codes sent to *other* bridges
    });

    // Send to bridge A — records bridgeA as target in sent_codes_history
    const { deviceId, buttonId } = await createDeviceWithButton(
      request, backendUrl, bridgeA.id,
      { protocol: 'nec', address: '0x04', command: '0x08' },
    );
    await triggerButton(request, backendUrl, deviceId, buttonId);

    // Simulate crosstalk: the same code arrives on bridge B within the timeout
    await sim.inject({ bridge_id: bridgeB.id, protocol: 'nec', address: '0x04', command: '0x08' });

    const received = await waitForReceived(request, backendUrl, bridgeB.id, 1);
    expect((received[0] as { ignored?: boolean }).ignored).toBe(true);
  });
});
