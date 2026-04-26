import { test, expect } from '@playwright/test';
import type { BridgeSettings } from '../src/types';

const NOW_TS = Math.floor(Date.now() / 1000);

const MOCK_BRIDGE = {
  id: 'esp-mock-bridge',
  name: 'Mock Bridge',
  status: 'online',
  ip: '192.168.1.100',
  version: '1.2.3',
  capabilities: ['nec', 'samsung', 'raw'],
  receivers: [{ id: 'ir_rx_main' }],
  transmitters: [{ id: 'ir_tx_main' }],
  enabled_protocols: ['nec'],
  last_seen: new Date().toISOString(),
  settings: {
    echo_enabled: false,
    echo_timeout: 500,
  },
};

const MOCK_BRIDGE_WITH_HISTORY = {
  ...MOCK_BRIDGE,
  last_received: [
    {
      protocol: 'nec',
      payload: { address: '0x04', command: '0x01' },
      receiver_id: 'ir_rx_main',
      timestamp: NOW_TS - 5,
    },
    {
      protocol: 'samsung',
      payload: { address: '0x07', command: '0x02' },
      receiver_id: 'ir_rx_main',
      timestamp: NOW_TS - 60,
    },
  ],
  last_sent: [
    {
      protocol: 'nec',
      payload: { address: '0x04', command: '0x10' },
      channel: 'ir_tx_main',
      timestamp: NOW_TS - 10,
    },
  ],
};

const MOCK_OFFLINE_BRIDGE = {
  id: 'esp-offline-bridge',
  name: 'Offline Bridge',
  status: 'offline',
  capabilities: ['nec'],
  enabled_protocols: [],
  last_seen: new Date(Date.now() - 3600_000).toISOString(),
};

async function setupBridgesRoute(page: import('@playwright/test').Page, bridges: object[]) {
  await page.route('**/api/bridges', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(bridges),
    });
  });
}

test.describe('Bridges Page', () => {
  test.beforeEach(async ({ page }) => {
    const resetResponse = await page.request.post('/api/reset');
    expect(resetResponse.ok()).toBeTruthy();

    await setupBridgesRoute(page, [MOCK_BRIDGE]);
    // Set up waitForResponse before navigating so we don't miss the request
    const bridgesLoaded = page.waitForResponse('**/api/bridges');
    await page.goto('/#Bridges');
    await expect(page.getByRole('heading', { name: 'Bridges' })).toBeVisible();
    // Wait for the API response before asserting the card (avoids Firefox WS timing flakiness)
    await bridgesLoaded;
    await expect(page.locator(`.card:has-text("${MOCK_BRIDGE.name}")`)).toBeVisible();
  });

  // ─── Display ────────────────────────────────────────────────────────────────

  test('displays bridge info, status, and protocol badges', async ({ page }) => {
    const card = page.locator(`.card:has-text("${MOCK_BRIDGE.name}")`);
    await expect(card).toBeVisible();
    await expect(card.getByText(MOCK_BRIDGE.id)).toBeVisible();
    await expect(card.getByText(MOCK_BRIDGE.ip)).toBeVisible();
    await expect(card.locator('.text-green-400 .mdi-circle')).toBeVisible(); // Check for the status icon
    // Protocol badges
    await expect(card.getByText('protocols')).toBeVisible(); // Just check if the protocols section is there in collapsed view
    await card.getByTitle('Protocols').click(); // Expand protocols
    await expect(card.getByText('nec', { exact: true })).toBeVisible();
    await expect(card.getByText('samsung', { exact: true })).toBeVisible();
    await expect(card.getByText('raw', { exact: true })).toBeVisible();
    // RX/TX channel counts
    await expect(card.getByText(/1 RX/i)).toBeVisible();
    await expect(card.getByText(/1 TX/i)).toBeVisible();
  });

  test('shows "no bridges" message when bridge list is empty', async ({ page }) => {
    await setupBridgesRoute(page, []);
    await page.reload();
    await expect(page.locator('[data-tour-id="no-bridges-message"]')).toBeVisible();
    await expect(page.getByText('No bridges detected.')).toBeVisible();
  });

  test('shows offline bridge with correct styling', async ({ page }) => {
    await setupBridgesRoute(page, [MOCK_OFFLINE_BRIDGE]);
    await page.reload(); // Reload to apply the new mock
    const card = page.locator(`.card:has-text("${MOCK_OFFLINE_BRIDGE.name}")`);
    await expect(card.locator('.text-red-400 .mdi-circle')).toBeVisible(); // Check for the red offline status icon
    // Protocol toggle should be disabled (cursor-not-allowed) for offline bridges
    // The outer span (wrapper) carries cursor-not-allowed, not the inner text span
    await card.getByTitle('Protocols').click(); // Expand protocols
    const disabledProtocolChip = card.locator('span.cursor-not-allowed:has-text("nec")');
    await expect(disabledProtocolChip).toBeVisible();
  });

  test('displays both online and offline bridges simultaneously', async ({ page }) => {
    await setupBridgesRoute(page, [MOCK_BRIDGE, MOCK_OFFLINE_BRIDGE]);
    const bridgesLoaded = page.waitForResponse('**/api/bridges');
    await page.reload();
    await bridgesLoaded;
    const onlineCard = page.locator(`.card:has-text("${MOCK_BRIDGE.name}")`);
    const offlineCard = page.locator(`.card:has-text("${MOCK_OFFLINE_BRIDGE.name}")`);
    await expect(onlineCard).toBeVisible();
    await expect(offlineCard).toBeVisible();
    await expect(onlineCard.locator('.text-green-400 .mdi-circle')).toBeVisible();
    await expect(offlineCard.locator('.text-red-400 .mdi-circle')).toBeVisible();
  });

  // ─── Protocol Toggle ────────────────────────────────────────────────────────

  test('can toggle a protocol on and off', async ({ page }) => {
    let capturedBody: Record<string, unknown> | null = null;
    await page.route(`**/api/bridges/${MOCK_BRIDGE.id}/protocols`, async (route, request) => {
      capturedBody = await request.postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });

    const card = page.locator(`.card:has-text("${MOCK_BRIDGE.name}")`);
    await card.getByTitle('Protocols').click(); // Expand protocols
    
    // 'samsung' is currently disabled — click to enable
    // Need to find the specific chip for 'samsung'
    const samsungChip = card.locator('span.uppercase.select-none', { hasText: 'samsung' });
    await samsungChip.click();
    await expect.poll(() => capturedBody).toBeTruthy();
    expect((capturedBody as { protocols: string[] }).protocols).toContain('samsung');
    expect((capturedBody as { protocols: string[] }).protocols).toContain('nec');
  });

  test('shift+click enables protocol exclusively', async ({ page }) => {
    let capturedBody: Record<string, unknown> | null = null;
    await page.route(`**/api/bridges/${MOCK_BRIDGE.id}/protocols`, async (route, request) => {
      capturedBody = await request.postDataJSON();
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    const card = page.locator(`.card:has-text("${MOCK_BRIDGE.name}")`);
    await card.getByTitle('Protocols').click(); // Expand protocols
    const samsungChip = card.locator('span.uppercase.select-none', { hasText: 'samsung' });
    // Shift+click 'samsung' — should enable only samsung
    await samsungChip.click({ modifiers: ['Shift'] });
    await expect.poll(() => capturedBody).toBeTruthy();
    const sent = (capturedBody as { protocols: string[] }).protocols;
    expect(sent).toContain('samsung');
    expect(sent).not.toContain('nec');
    expect(sent).not.toContain('raw');
  });

  // ─── Bridge History ─────────────────────────────────────────────────────────

  test('history section is hidden by default and toggles open', async ({ page }) => {
    const card = page.locator(`.card:has-text("${MOCK_BRIDGE.name}")`);
    const historyBtn = card.locator('[data-tour-id="bridge-history-btn"]');
    await expect(historyBtn).toBeVisible();

    // History row should not be visible yet
    await expect(card.getByText('Received', { exact: false })).not.toBeVisible();

    await historyBtn.click();
    await expect(card.locator('h4').filter({ hasText: 'Received' }).first()).toBeVisible();
    await expect(card.locator('h4').filter({ hasText: 'Sent' }).first()).toBeVisible();
  });

  test('shows "no codes" placeholders when history is empty', async ({ page }) => {
    const card = page.locator(`.card:has-text("${MOCK_BRIDGE.name}")`);
    await card.locator('[data-tour-id="bridge-history-btn"]').click();
    await expect(card.getByText('No codes received yet.')).toBeVisible();
    await expect(card.getByText('No codes sent yet.')).toBeVisible();
  });

  test('history displays protocol badges, channel badges, and code fields', async ({ page }) => {
    await setupBridgesRoute(page, [MOCK_BRIDGE_WITH_HISTORY]);
    await page.reload();
    const card = page.locator(`.card:has-text("${MOCK_BRIDGE_WITH_HISTORY.name}")`);
    await card.locator('[data-tour-id="bridge-history-btn"]').click();

    // Protocol badges
    const historyPanel = card.locator('.divide-y.md\\:divide-y-0');
    await expect(historyPanel.getByText('nec', { exact: true }).first()).toBeVisible();
    await expect(historyPanel.getByText('samsung', { exact: true }).first()).toBeVisible();

    // RX channel badge
    await expect(historyPanel.getByText('ir_rx_main').first()).toBeVisible();

    // TX channel badge in sent section
    await expect(historyPanel.getByText('ir_tx_main')).toBeVisible();

    // Code fields: address and command
    const addrLabels = historyPanel.locator('span', { hasText: 'address' }).first();
    await expect(addrLabels).toBeVisible();
  });

  test('relative timestamps are shown ("s ago" or "m ago")', async ({ page }) => {
    await setupBridgesRoute(page, [MOCK_BRIDGE_WITH_HISTORY]);
    await page.reload();
    const card = page.locator(`.card:has-text("${MOCK_BRIDGE_WITH_HISTORY.name}")`);
    await card.locator('[data-tour-id="bridge-history-btn"]').click();
    // Recent entry should show seconds ago
    await expect(card.getByText(/\d+s ago/).first()).toBeVisible();
    // Older entry should show minutes ago
    await expect(card.getByText(/\d+m ago/).first()).toBeVisible();
  });

  test('history toggle closes when clicked again', async ({ page }) => {
    const card = page.locator(`.card:has-text("${MOCK_BRIDGE.name}")`);
    const historyBtn = card.locator('[data-tour-id="bridge-history-btn"]');
    await historyBtn.click();
    await expect(card.locator('h4').filter({ hasText: 'Received' }).first()).toBeVisible();
    await historyBtn.click();
    await expect(card.getByText('No codes received yet.')).not.toBeVisible();
  });

  // ─── Edit Settings ──────────────────────────────────────────────────────────

  test('edit panel saves settings and closes', async ({ page }) => {
    let settingsUpdateRequest: Partial<BridgeSettings> | null = null;
    await page.route(`**/api/bridges/${MOCK_BRIDGE.id}/settings`, async (route, request) => { // This route mock is correct
      settingsUpdateRequest = await request.postDataJSON() as Partial<BridgeSettings>;
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
    });

    const card = page.locator(`.card:has-text("${MOCK_BRIDGE.name}")`);
    await card.getByTitle('Echo Suppression Settings').click(); // Click the settings button on the card

    // The settings are now inline in the card, not a modal. So we interact with elements within the expanded settings panel.
    const settingsPanel = card.locator('.px-4.py-3.space-y-2');
    await expect(settingsPanel).toBeVisible();
    await expect(settingsPanel.getByText('Echo Suppression').first()).toBeVisible();

    const echoSwitch = settingsPanel.locator('label', { hasText: 'Echo Suppression' }).getByRole('checkbox');
    await echoSwitch.check(); // Check the switch to enable echo suppression

    const fetchPromise = page.waitForResponse('**/api/bridges');
    await settingsPanel.getByRole('button', { name: 'Save' }).click();
    await fetchPromise;

    await expect(settingsPanel).not.toBeVisible(); // The panel should collapse
    expect(settingsUpdateRequest?.echo_enabled).toBe(true);
  });

  // ─── Delete ─────────────────────────────────────────────────────────────────

  test('delete bridge with confirmation removes it from list', async ({ page }) => {
    await page.route(`**/api/bridges/${MOCK_BRIDGE.id}`, async route => { // This mock is correct
      await route.fulfill({ status: 200 });
    });

    const card = page.locator(`.card:has-text("${MOCK_BRIDGE.name}")`);
    await card.getByTitle(/Delete Bridge/).click(); // Click the delete button on the card

    const deleteReq = page.waitForRequest(
      r => r.url().includes(`/api/bridges/${MOCK_BRIDGE.id}`) && r.method() === 'DELETE'
    );
    await page.getByRole('button', { name: 'Confirm' }).click();
    await deleteReq;

    await setupBridgesRoute(page, []);
    await page.reload();
    await expect(page.locator('[data-tour-id="no-bridges-message"]')).toBeVisible();
  });

  test('cancel on delete confirmation keeps bridge in list', async ({ page }) => {
    const card = page.locator(`.card:has-text("${MOCK_BRIDGE.name}")`);
    await card.getByTitle(/Delete Bridge/).click();
    await page.getByRole('button', { name: 'Cancel' }).click();
    // Bridge should still be visible
    await expect(card).toBeVisible();
  });
});
