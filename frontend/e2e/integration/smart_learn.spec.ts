/**
 * Integration tests — Smart Learn mode
 *
 * Tests the smart learning flow:
 *   POST /api/learn?smart=true → backend enters smart mode
 *   → each received IR code is added to the current_burst
 *   → after 500ms silence a burst is committed to smart_samples
 *   → after 5 bursts, _analyze_smart_samples picks the most common code
 *   → learned_code + learning_status WS events fire
 *   → POST /api/devices/{id}/buttons/{id}/assign_code stores the result
 *
 * Burst timing:
 *   The backend burst timer fires after 500ms of silence.
 *   Tests inject one code per burst with ≥600ms gaps to guarantee 5 distinct bursts.
 */

import { test, expect } from './fixtures';

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function startSmartLearn(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
  bridges: string[] = ['any'],
): Promise<void> {
  const params = new URLSearchParams({ smart: 'true' });
  bridges.forEach(b => params.append('bridges', b));
  const res = await request.post(`${backendUrl}/api/learn?${params.toString()}`);
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  expect(body.mode).toBe('smart');
}

async function cancelLearn(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
): Promise<void> {
  const res = await request.post(`${backendUrl}/api/learn/cancel`);
  expect(res.ok()).toBeTruthy();
}

/** Creates a device with one button that has no IR code assigned yet. */
async function createDeviceWithEmptyButton(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
): Promise<{ deviceId: string; buttonId: string }> {
  const devRes = await request.post(`${backendUrl}/api/devices`, {
    headers: { 'Content-Type': 'application/json' },
    data: { name: `Smart Learn TV ${Date.now()}`, icon: 'television', buttons: [] },
  });
  expect(devRes.ok()).toBeTruthy();
  const device = await devRes.json();

  const btnRes = await request.post(`${backendUrl}/api/devices/${device.id}/buttons`, {
    headers: { 'Content-Type': 'application/json' },
    data: { name: 'Power', icon: 'power', is_output: true },
  });
  expect(btnRes.ok()).toBeTruthy();
  const button = await btnRes.json();

  return { deviceId: device.id, buttonId: button.id };
}

/**
 * Polls assign_code (no payload → uses last_learned_code) until it succeeds or times out.
 * Returns the code that was assigned to the button.
 */
async function waitForLearnedCodeAndAssign(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
  deviceId: string,
  buttonId: string,
  timeoutMs = 8_000,
): Promise<{ protocol: string; payload: Record<string, string> }> {
  const deadline = Date.now() + timeoutMs;
  let lastError = '';
  while (Date.now() < deadline) {
    const assignRes = await request.post(
      `${backendUrl}/api/devices/${deviceId}/buttons/${buttonId}/assign_code`,
      { headers: { 'Content-Type': 'application/json' } },
    );
    if (assignRes.ok()) {
      const devRes = await request.get(`${backendUrl}/api/devices`);
      expect(devRes.ok()).toBeTruthy();
      const devices: Array<{
        id: string;
        buttons: Array<{ id: string; code: { protocol: string; payload: Record<string, string> } | null }>;
      }> = await devRes.json();
      const dev = devices.find(d => d.id === deviceId);
      const btn = dev?.buttons.find(b => b.id === buttonId);
      if (btn?.code) return btn.code;
    } else {
      lastError = await assignRes.text();
    }
    await new Promise(r => setTimeout(r, 300));
  }
  throw new Error(`waitForLearnedCodeAndAssign timed out. Last error: ${lastError}`);
}

type InjectedCode = { protocol?: string; address?: string; command?: string };

/**
 * Injects `count` bursts separated by `gapMs` of silence.
 * One inject call per burst — the backend burst timer fires after 500ms of silence.
 */
async function injectBursts(
  sim: import('./fixtures').SimHelper,
  bridgeId: string,
  count: number,
  code: InjectedCode = {},
  gapMs = 600,
): Promise<void> {
  for (let i = 0; i < count; i++) {
    await sim.inject({ bridge_id: bridgeId, protocol: 'nec', address: '0x04', command: '0x08', ...code });
    await new Promise(r => setTimeout(r, gapMs));
  }
}

// ─── Tests ────────────────────────────────────────────────────────────────────

test.describe('Smart Learn (Integration)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ resetAll }) => {
    await resetAll();
  });

  // ── API mode flag ─────────────────────────────────────────────────────────

  test('POST /api/learn?smart=true returns mode "smart"', async ({
    sim, request, backendUrl,
  }) => {
    await sim.spawn({ bridge_id: 'test-smart-mode-1' });

    const res = await request.post(`${backendUrl}/api/learn?smart=true&bridges=any`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.mode).toBe('smart');
    expect(body.bridges).toContain('any');

    await cancelLearn(request, backendUrl);
  });

  // ── Core happy path ───────────────────────────────────────────────────────

  test('5 bursts complete smart learning and make code available for assignment', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-smart-basic-1' });
    const { deviceId, buttonId } = await createDeviceWithEmptyButton(request, backendUrl);

    await startSmartLearn(request, backendUrl);

    // 5 bursts, one NEC code per burst, 600ms gap between bursts
    await injectBursts(sim, bridge.id, 5, { address: '0x04', command: '0x08' });

    // After 5 bursts last_learned_code is set — assign it and verify
    const code = await waitForLearnedCodeAndAssign(request, backendUrl, deviceId, buttonId);
    expect(code.protocol).toBe('nec');
    expect(code.payload.address).toBe('0x04');
    expect(code.payload.command).toBe('0x08');
  });

  // ── Majority vote ─────────────────────────────────────────────────────────

  test('majority vote: code appearing in most bursts wins', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-smart-vote-1' });
    const { deviceId, buttonId } = await createDeviceWithEmptyButton(request, backendUrl);

    await startSmartLearn(request, backendUrl);

    const codeA: InjectedCode = { address: '0x04', command: '0x08' }; // 3 bursts
    const codeB: InjectedCode = { address: '0x01', command: '0x02' }; // 2 bursts

    // Burst 1–3: code A
    await injectBursts(sim, bridge.id, 3, codeA);
    // Burst 4–5: code B
    await injectBursts(sim, bridge.id, 2, codeB);

    // Code A appeared in 3 of 5 bursts — it should win
    const code = await waitForLearnedCodeAndAssign(request, backendUrl, deviceId, buttonId);
    expect(code.protocol).toBe('nec');
    expect(code.payload.address).toBe('0x04');
    expect(code.payload.command).toBe('0x08');
  });

  // ── Cancel ────────────────────────────────────────────────────────────────

  test('cancelling before 5 bursts leaves no learned code available', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-smart-cancel-1' });
    const { deviceId, buttonId } = await createDeviceWithEmptyButton(request, backendUrl);

    await startSmartLearn(request, backendUrl);

    // Only 2 bursts — not enough to complete
    await injectBursts(sim, bridge.id, 2, { address: '0x04', command: '0x08' });

    // Cancel before remaining bursts
    await cancelLearn(request, backendUrl);

    // assign_code with no payload should fail (no last_learned_code)
    const assignRes = await request.post(
      `${backendUrl}/api/devices/${deviceId}/buttons/${buttonId}/assign_code`,
      { headers: { 'Content-Type': 'application/json' } },
    );
    expect(assignRes.status()).toBe(400);
  });

  // ── New session resets state ──────────────────────────────────────────────

  test('starting a new smart learn session resets the previous burst collection', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-smart-restart-1' });
    const { deviceId, buttonId } = await createDeviceWithEmptyButton(request, backendUrl);

    // First session — 2 bursts with code B, then cancel
    await startSmartLearn(request, backendUrl);
    await injectBursts(sim, bridge.id, 2, { address: '0x01', command: '0x02' });
    await cancelLearn(request, backendUrl);

    // Second session — 5 bursts with code A (samples from first session must be cleared)
    await startSmartLearn(request, backendUrl);
    await injectBursts(sim, bridge.id, 5, { address: '0x04', command: '0x08' });

    // The result must be code A only — no contamination from the first session
    const code = await waitForLearnedCodeAndAssign(request, backendUrl, deviceId, buttonId);
    expect(code.payload.address).toBe('0x04');
    expect(code.payload.command).toBe('0x08');
  });

  // ── Bridge targeting ──────────────────────────────────────────────────────

  test('targeted smart learn ignores injections on other bridges', async ({
    sim, request, backendUrl,
  }) => {
    const bridgeA = await sim.spawn({ bridge_id: 'test-smart-target-a' });
    const bridgeB = await sim.spawn({ bridge_id: 'test-smart-target-b' });
    const { deviceId, buttonId } = await createDeviceWithEmptyButton(request, backendUrl);

    // Target only bridge A
    await startSmartLearn(request, backendUrl, [bridgeA.id]);

    // Inject 5 bursts on bridge B — must be ignored
    await injectBursts(sim, bridgeB.id, 5, { address: '0x01', command: '0x02' });

    // No learned code yet
    await new Promise(r => setTimeout(r, 300));
    const assignRes = await request.post(
      `${backendUrl}/api/devices/${deviceId}/buttons/${buttonId}/assign_code`,
      { headers: { 'Content-Type': 'application/json' } },
    );
    expect(assignRes.status()).toBe(400);

    // Now inject 5 bursts on bridge A — must be counted
    await injectBursts(sim, bridgeA.id, 5, { address: '0x04', command: '0x08' });

    const code = await waitForLearnedCodeAndAssign(request, backendUrl, deviceId, buttonId);
    expect(code.payload.address).toBe('0x04');
    expect(code.payload.command).toBe('0x08');
  });

  // ── UI: progress indicator ────────────────────────────────────────────────

  test('smart_learn_progress WS events show a progress indicator in the UI', async ({
    page, sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-smart-ui-1' });
    await createDeviceWithEmptyButton(request, backendUrl);

    await page.goto('/');
    await expect(page.locator('[data-tour-id="device-card"]')).toBeVisible({ timeout: 10_000 });

    await page.locator('[data-tour-id="configure-learn-button"]').click();
    await expect(page.getByRole('heading', { name: 'Learn IR Code' })).toBeVisible();

    // Enable Smart Learn mode by clicking the "Smart Learn" label (Switch component, not a checkbox)
    // Use exact: true so the device name "Smart Learn TV …" is not matched as well
    await page.getByText('Smart Learn', { exact: true }).click();

    // Start learning — modal closes automatically, devices page shows "Learning Mode Active" overlay
    const learnReq = page.waitForRequest(r => r.url().includes('/api/learn'));
    await page.getByRole('button', { name: 'Start Learning' }).click();
    await learnReq;

    // Wait for the learning overlay to confirm smart mode is active
    await expect(page.getByText('Learning Mode Active')).toBeVisible({ timeout: 8_000 });

    // Inject one burst to trigger a smart_learn_progress WS event
    await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x04', command: '0x08' });
    await new Promise(r => setTimeout(r, 700)); // wait for burst timer to fire

    // The UI shows "Press N more time(s)" (e.g. "Press 4 more time(s)" after 1 of 5 bursts)
    await expect(page.getByText(/Press \d+ more time\(s\)/)).toBeVisible({ timeout: 8_000 });

    await cancelLearn(request, backendUrl);
  });
});
