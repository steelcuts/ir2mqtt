/**
 * Integration tests — Bridge Ignore / Unignore
 *
 * Tests the ignore lifecycle for MQTT bridges:
 *   - Ignored bridge disappears from GET /api/bridges (filtered by backend)
 *   - Ignored bridge ID is stored in GET /api/bridges/ignored
 *   - Frontend Bridges view hides ignored bridge via WS bridges_updated event
 *   - Unignore restores bridge in API response and frontend
 *
 * Note: ignoring is a UI/display filter — the backend still processes IR codes
 * from ignored bridges internally. These tests only verify the display contract.
 */

import { test, expect } from './fixtures';

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function ignoreBridge(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
  bridgeId: string,
) {
  const res = await request.post(
    `${backendUrl}/api/bridges/ignored/${encodeURIComponent(bridgeId)}`,
  );
  expect(res.ok()).toBeTruthy();
}

async function unignoreBridge(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
  bridgeId: string,
) {
  const res = await request.delete(
    `${backendUrl}/api/bridges/ignored/${encodeURIComponent(bridgeId)}`,
  );
  expect(res.ok()).toBeTruthy();
}

async function getIgnoredList(
  request: import('@playwright/test').APIRequestContext,
  backendUrl: string,
): Promise<string[]> {
  const res = await request.get(`${backendUrl}/api/bridges/ignored`);
  expect(res.ok()).toBeTruthy();
  const body: { ignored: string[] } = await res.json();
  return body.ignored;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

test.describe('Bridge Ignore / Unignore (Integration)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ resetAll }) => {
    await resetAll();
  });

  // ── API-level behaviour ───────────────────────────────────────────────────

  test('ignored bridge is absent from GET /api/bridges', async ({ sim, request, backendUrl }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-ignore-absent-1' });

    // Confirm bridge is present before ignoring
    const before = await request.get(`${backendUrl}/api/bridges`);
    const bridgesBefore: Array<{ id: string }> = await before.json();
    expect(bridgesBefore.some(b => b.id === bridge.id)).toBe(true);

    await ignoreBridge(request, backendUrl, bridge.id);

    const after = await request.get(`${backendUrl}/api/bridges`);
    const bridgesAfter: Array<{ id: string }> = await after.json();
    expect(bridgesAfter.some(b => b.id === bridge.id)).toBe(false);
  });

  test('ignored bridge ID appears in GET /api/bridges/ignored', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-ignore-list-1' });

    // Not ignored yet
    const before = await getIgnoredList(request, backendUrl);
    expect(before).not.toContain(bridge.id);

    await ignoreBridge(request, backendUrl, bridge.id);

    const after = await getIgnoredList(request, backendUrl);
    expect(after).toContain(bridge.id);
  });

  test('ignoring the same bridge twice is idempotent', async ({ sim, request, backendUrl }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-ignore-idempotent-1' });

    await ignoreBridge(request, backendUrl, bridge.id);
    await ignoreBridge(request, backendUrl, bridge.id); // second call must not error

    const ignored = await getIgnoredList(request, backendUrl);
    // Still only one entry for this bridge
    expect(ignored.filter(id => id === bridge.id)).toHaveLength(1);
  });

  test('unignore removes bridge from ignored list and restores it in GET /api/bridges', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-ignore-restore-1' });

    await ignoreBridge(request, backendUrl, bridge.id);

    // Verify it is gone
    const mid = await request.get(`${backendUrl}/api/bridges`);
    const midBridges: Array<{ id: string }> = await mid.json();
    expect(midBridges.some(b => b.id === bridge.id)).toBe(false);

    await unignoreBridge(request, backendUrl, bridge.id);

    // Give the backend a moment to process the get_config round-trip
    await new Promise(r => setTimeout(r, 800));

    const restored = await getIgnoredList(request, backendUrl);
    expect(restored).not.toContain(bridge.id);

    const after = await request.get(`${backendUrl}/api/bridges`);
    const bridgesAfter: Array<{ id: string }> = await after.json();
    expect(bridgesAfter.some(b => b.id === bridge.id)).toBe(true);
  });

  test('unignoring a bridge that is not ignored returns 404', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-ignore-404-1' });

    const res = await request.delete(
      `${backendUrl}/api/bridges/ignored/${encodeURIComponent(bridge.id)}`,
    );
    expect(res.status()).toBe(404);
  });

  // ── RX processing is suppressed for ignored bridges ──────────────────────

  test('IR code injected on ignored bridge does not appear in received history', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-ignore-rx-1' });

    await ignoreBridge(request, backendUrl, bridge.id);

    // Inject an IR signal — backend must drop it because the bridge is ignored
    await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x04', command: '0x08' });

    // Wait generously — if processing were to happen it would be done by now
    await new Promise(r => setTimeout(r, 1_000));

    // The bridge itself is filtered from GET /api/bridges, but we can verify
    // via the raw internal state by temporarily unignoring and re-checking
    await unignoreBridge(request, backendUrl, bridge.id);
    await new Promise(r => setTimeout(r, 400));

    const res = await request.get(`${backendUrl}/api/bridges`);
    const bridges: Array<{ id: string; last_received?: unknown[] }> = await res.json();
    const b = bridges.find(b => b.id === bridge.id);
    expect(b?.last_received?.length ?? 0).toBe(0);
  });

  test('IR code injected on ignored bridge does not trigger automations', async ({
    sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-ignore-auto-1' });

    // Create a trigger device/button matching the code we will inject
    const devRes = await request.post(`${backendUrl}/api/devices`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        name: 'Ignore Auto TV',
        icon: 'television',
        buttons: [],
        target_bridges: [bridge.id],
        allowed_bridges: [bridge.id],
      },
    });
    const dev = await devRes.json();
    const trigBtnRes = await request.post(`${backendUrl}/api/devices/${dev.id}/buttons`, {
      headers: { 'Content-Type': 'application/json' },
      data: { name: 'Power', icon: 'power', is_output: true,
        code: { protocol: 'nec', payload: { address: '0x04', command: '0x08' } } },
    });
    const trigBtn = await trigBtnRes.json();

    const actionBtnRes = await request.post(`${backendUrl}/api/devices/${dev.id}/buttons`, {
      headers: { 'Content-Type': 'application/json' },
      data: { name: 'Vol Up', icon: 'volume-plus', is_output: true,
        code: { protocol: 'nec', payload: { address: '0x01', command: '0x02' } } },
    });
    const actionBtn = await actionBtnRes.json();

    await request.post(`${backendUrl}/api/automations`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        name: 'Should Not Fire',
        enabled: true,
        triggers: [{ type: 'single', device_id: dev.id, button_id: trigBtn.id }],
        actions: [{ type: 'ir_send', device_id: dev.id, button_id: actionBtn.id }],
      },
    });

    await ignoreBridge(request, backendUrl, bridge.id);

    // Inject trigger code on the now-ignored bridge
    await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x04', command: '0x08' });

    await new Promise(r => setTimeout(r, 1_000));

    // Unignore to make the bridge visible in the API again
    await unignoreBridge(request, backendUrl, bridge.id);
    await new Promise(r => setTimeout(r, 400));

    const res = await request.get(`${backendUrl}/api/bridges`);
    const bridges: Array<{ id: string; last_sent?: unknown[] }> = await res.json();
    const b = bridges.find(b => b.id === bridge.id);
    // Automation must NOT have fired — no send entry
    expect(b?.last_sent?.length ?? 0).toBe(0);
  });

  // ── Multiple bridges — only ignored one is hidden ─────────────────────────

  test('ignoring one bridge does not affect other bridges in the list', async ({
    sim, request, backendUrl,
  }) => {
    const bridgeA = await sim.spawn({ bridge_id: 'test-ignore-multi-a' });
    const bridgeB = await sim.spawn({ bridge_id: 'test-ignore-multi-b' });

    await ignoreBridge(request, backendUrl, bridgeA.id);

    const res = await request.get(`${backendUrl}/api/bridges`);
    const bridges: Array<{ id: string }> = await res.json();

    expect(bridges.some(b => b.id === bridgeA.id)).toBe(false); // ignored
    expect(bridges.some(b => b.id === bridgeB.id)).toBe(true);  // still visible
  });

  // ── Frontend UI ───────────────────────────────────────────────────────────

  test('frontend hides ignored bridge without page reload (via WS)', async ({
    page, sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-ignore-ws-1' });

    await page.goto('/#Bridges');
    await expect(page.getByRole('heading', { name: 'Bridges' })).toBeVisible();

    // Bridge card must be visible before ignore
    const card = page.locator(`.card:has-text("${bridge.name}")`);
    await expect(card).toBeVisible({ timeout: 10_000 });

    // Ignore via API — backend broadcasts bridges_updated via WS
    await ignoreBridge(request, backendUrl, bridge.id);

    // No page reload — the WS event should remove the card
    await expect(card).not.toBeVisible({ timeout: 8_000 });
  });

  test('frontend shows bridge again after unignore (via WS)', async ({
    page, sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-ignore-unignore-ws-1' });

    // Ignore before loading the page
    await ignoreBridge(request, backendUrl, bridge.id);

    await page.goto('/#Bridges');
    await expect(page.getByRole('heading', { name: 'Bridges' })).toBeVisible();

    // Should not be visible initially
    const card = page.locator(`.card:has-text("${bridge.name}")`);
    await expect(card).not.toBeVisible({ timeout: 5_000 });

    // Unignore — backend broadcasts bridges_updated
    await unignoreBridge(request, backendUrl, bridge.id);

    // Card should reappear via WS without a reload
    await expect(card).toBeVisible({ timeout: 10_000 });
  });

  test('ignored bridge does not show in the frontend even after page reload', async ({
    page, sim, request, backendUrl,
  }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-ignore-reload-1' });

    await ignoreBridge(request, backendUrl, bridge.id);

    // Hard reload — initial state from GET /api/bridges must also exclude the bridge
    await page.goto('/#Bridges');
    await expect(page.getByRole('heading', { name: 'Bridges' })).toBeVisible();

    await expect(
      page.locator(`.card:has-text("${bridge.name}")`),
    ).not.toBeVisible({ timeout: 5_000 });
  });
});
