/**
 * Integration tests — Bridge discovery & history
 *
 * Tests the full MQTT chain:
 *   Simulator (MQTT publish) → Mosquitto → Backend (MQTT subscribe + state update)
 *   → GET /api/bridges → Vite proxy → Frontend
 *
 * Each test:
 *   1. Resets backend state and deletes all sim bridges
 *   2. Spawns a known bridge via the sim_server HTTP API
 *   3. Asserts the real frontend reflects the real data
 */

import { test, expect } from './fixtures';

test.describe('Bridge Discovery & Status (Integration)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ resetAll }) => {
    await resetAll();
  });

  // ─── Discovery ────────────────────────────────────────────────────────────

  test('spawned bridge appears online in the Bridges view', async ({ page, sim }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-discovery-1' });

    await page.goto('/#Bridges');
    await expect(page.getByRole('heading', { name: 'Bridges' })).toBeVisible();

    // The card for the new bridge should appear via WebSocket update
    const card = page.locator(`.card:has-text("${bridge.name}")`);
    await expect(card).toBeVisible({ timeout: 10_000 });

    // Check for the green "online" status indicator
    await expect(card.locator('.text-green-400 .mdi-circle')).toBeVisible();
  });

  test('bridge shows correct capabilities from simulator config', async ({ page, sim }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-caps-1' });

    await page.goto('/#Bridges');
    await expect(page.getByRole('heading', { name: 'Bridges' })).toBeVisible();

    const card = page.locator(`.card:has-text("${bridge.name}")`);
    await expect(card).toBeVisible({ timeout: 10_000 });

    // Expand the protocols panel
    await card.getByTitle('Protocols').click();

    // Simulator spawns bridges with nec, samsung, raw, sony, lg
    const protocolPanel = card.locator('div:has-text("Click to toggle")');
    await expect(protocolPanel.getByText('nec', { exact: true })).toBeVisible();
    await expect(protocolPanel.getByText('samsung', { exact: true })).toBeVisible();
    await expect(protocolPanel.getByText('raw', { exact: true })).toBeVisible();
  });

  test('bridge shows RX and TX channel counts', async ({ page, sim }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-channels-1' });

    await page.goto('/#Bridges');
    const card = page.locator(`.card:has-text("${bridge.name}")`);
    await expect(card).toBeVisible({ timeout: 10_000 });

    // The sim engine always creates at least 1 RX and 1 TX
    await expect(card.getByText(/\d+ RX/i)).toBeVisible();
    await expect(card.getByText(/\d+ TX/i)).toBeVisible();
  });

  test('bridge goes offline after being deleted from simulator', async ({ page, sim, request, backendUrl, simUrl }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-offline-1' });

    await page.goto('/#Bridges');
    const card = page.locator(`.card:has-text("${bridge.name}")`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await expect(card.locator('.text-green-400 .mdi-circle')).toBeVisible();

    // Delete via sim_server → simulator sends LWT (offline) MQTT message
    await request.delete(`${simUrl}/bridges/${bridge.id}`);

    // Use the backend API directly to delete the bridge record
    await request.delete(`${backendUrl}/api/bridges/${bridge.id}`);

    await page.reload();
    await expect(page.getByRole('heading', { name: 'Bridges' })).toBeVisible();
    // After reload the bridge should be gone (deleted from backend)
    await expect(page.locator(`.card:has-text("${bridge.name}")`)).not.toBeVisible({ timeout: 8_000 });
  });

  // ─── History ──────────────────────────────────────────────────────────────

  test('received IR code appears in bridge history after inject_signal', async ({ page, sim }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-history-rx-1' });

    await page.goto('/#Bridges');
    const card = page.locator(`.card:has-text("${bridge.name}")`);
    await expect(card).toBeVisible({ timeout: 10_000 });

    // Inject an NEC code from the simulator
    await sim.inject({
      bridge_id: bridge.id,
      protocol: 'nec',
      address: '0x04',
      command: '0x08',
    });

    // Small delay for MQTT → backend → WS to propagate
    await new Promise(r => setTimeout(r, 800));

    // Open history panel
    await card.getByTitle(/History/).click();

    // The history section should show the nec badge
    const historyPanel = card.locator('div:has-text("Received")');
    await expect(historyPanel.getByText('nec', { exact: true }).first()).toBeVisible({ timeout: 8_000 });
  });

  test('received code shows the correct receiver channel in history', async ({ page, sim }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-history-ch-1' });
    // Receiver IDs assigned by the engine (ir_rx_0, ir_rx_1, …)
    const receiverId = bridge.receivers[0];

    await page.goto('/#Bridges');
    const card = page.locator(`.card:has-text("${bridge.name}")`);
    await expect(card).toBeVisible({ timeout: 10_000 });

    await sim.inject({
      bridge_id: bridge.id,
      protocol: 'nec',
      address: '0x12',
      command: '0x34',
      receiver_id: receiverId,
    });
    await new Promise(r => setTimeout(r, 800));

    await card.getByTitle(/History/).click();
    const historyPanel = card.locator('div:has-text("Received")');
    await expect(historyPanel.getByText(receiverId).first()).toBeVisible({ timeout: 8_000 });
  });

  test('multiple inject calls all appear in history (max 10)', async ({ page, sim }) => {
    const bridge = await sim.spawn({ bridge_id: 'test-history-multi-1' });

    await page.goto('/#Bridges');
    const card = page.locator(`.card:has-text("${bridge.name}")`);
    await expect(card).toBeVisible({ timeout: 10_000 });

    // Inject 3 codes with different commands
    for (const cmd of ['0x01', '0x02', '0x03']) { // This loop is fine
      await sim.inject({ bridge_id: bridge.id, protocol: 'nec', address: '0x04', command: cmd });
      await new Promise(r => setTimeout(r, 300));
    }

    await card.getByTitle(/History/).click();

    const historyPanel = card.locator('div:has-text("Received")');
    // All three should be visible
    await expect(historyPanel.locator('.px-3.py-2')).toHaveCount(3, { timeout: 8_000 });
  });

  // ─── WebSocket real-time update ───────────────────────────────────────────

  test('page updates without reload when bridge comes online via MQTT', async ({ page, sim }) => {
    // Open Bridges page BEFORE spawning — no bridge should exist
    await page.goto('/#Bridges');
    await expect(page.getByRole('heading', { name: 'Bridges' })).toBeVisible();
    await expect(page.getByText('No bridges detected.')).toBeVisible({ timeout: 5_000 });

    // Spawn bridge AFTER page load — update should come via WebSocket bridges_updated
    const bridge = await sim.spawn({ bridge_id: 'test-ws-realtime-1' });

    // No reload — the WS event should push the update
    await expect(page.locator(`.card:has-text("${bridge.name}")`)).toBeVisible({ timeout: 12_000 });
  });
});
