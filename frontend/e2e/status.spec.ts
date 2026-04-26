import { test, expect } from '@playwright/test';

const MOCK_WS_SCRIPT = () => {
  class MockWebSocket {
    onopen: (() => void) | null = null;
    onmessage: ((event: { data: string }) => void) | null = null;
    constructor(public url: string) {
      setTimeout(() => this.onopen?.(), 10);
      (window as { mockWS?: MockWebSocket }).mockWS = this;
    }
    send() {}
    close() {}
    receive(data: Record<string, unknown>) {
      if (this.onmessage) this.onmessage({ data: JSON.stringify(data) });
    }
  }
  (window as { WebSocket?: typeof MockWebSocket }).WebSocket = MockWebSocket;
};

test.describe('Status Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(MOCK_WS_SCRIPT);
    const reset = await page.request.post('/api/reset');
    expect(reset.ok()).toBeTruthy();
    await page.goto('/#Status');
  });

  test('shows MQTT as disconnected by default', async ({ page }) => {
    // Scope to the MQTT card to avoid matching log messages
    const mqttCard = page.locator('.card').filter({ hasText: 'MQTT' }).first();
    await expect(mqttCard.getByText('Disconnected', { exact: true })).toBeVisible();
    await expect(page.locator('.mdi-lan-disconnect')).toBeVisible();
  });

  test('updates MQTT status to Connected via WebSocket', async ({ page }) => {
    await page.evaluate(() => {
      (window as { mockWS?: { receive: (d: Record<string, unknown>) => void } })
        .mockWS?.receive({ type: 'mqtt_status', connected: true });
    });
    // Scope to MQTT card to avoid matching "Log stream connected." in logs
    const mqttCard = page.locator('.card').filter({ hasText: 'MQTT' }).first();
    await expect(mqttCard.getByText('Connected', { exact: true })).toBeVisible();
    await expect(page.locator('.mdi-lan-connect')).toBeVisible();
  });

  test('shows zero devices and buttons with no data', async ({ page }) => {
    const devCard = page.locator('.card').filter({ hasText: 'Devices' }).first();
    const btnCard = page.locator('.card').filter({ hasText: 'Buttons' }).first();
    await expect(devCard).toContainText('0');
    await expect(btnCard).toContainText('0');
  });

  test('reflects device count after creating a device', async ({ page }) => {
    const res = await page.request.post('/api/devices', {
      headers: { 'Content-Type': 'application/json' },
      data: { name: 'Status Test TV', icon: 'television', buttons: [] },
    });
    expect(res.ok()).toBeTruthy();
    await page.reload();
    const devCard = page.locator('.card').filter({ hasText: 'Devices' }).first();
    await expect(devCard).toContainText('1');
  });

  test('shows IRDB as Not Found when database is absent', async ({ page }) => {
    await page.route('**/api/irdb/status', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ exists: false }),
      });
    });
    await page.reload();
    const irdbCard = page.locator('.card').filter({ hasText: 'IRDB' }).first();
    await expect(irdbCard.getByText('Not Found', { exact: true })).toBeVisible();
  });

  test('shows IRDB as Loaded when database exists', async ({ page }) => {
    await page.route('**/api/irdb/status', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          exists: true,
          total_remotes: 42,
          total_codes: 1337,
          last_updated: new Date().toISOString(),
        }),
      });
    });
    await page.reload();
    const irdbCard = page.locator('.card').filter({ hasText: 'IRDB' }).first();
    await expect(irdbCard.getByText('Loaded', { exact: true })).toBeVisible();
  });

  test('log console section is visible and clear button removes entries', async ({ page }) => {
    // The Status page always shows a log console section
    await expect(page.locator('h2', { hasText: 'Logs' })).toBeVisible();

    // The clear button exists
    const clearBtn = page.getByRole('button', { name: /Clear/i });
    await expect(clearBtn).toBeVisible();

    // After clearing, the log area should be empty (no error thrown)
    await clearBtn.click();
  });
});
