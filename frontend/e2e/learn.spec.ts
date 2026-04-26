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

test.describe('Learning Flow', () => {
  test.beforeEach(async ({ page }) => {
    const resetResponse = await page.request.post('/api/reset');
    expect(resetResponse.ok()).toBeTruthy();
    await page.addInitScript(MOCK_WS_SCRIPT);
    await page.goto('/');
  });

  async function createDevice(page: import('@playwright/test').Page, name = 'Dev1') {
    await page.locator('[data-tour-id="add-device-button"]').click();
    await page.locator('[data-tour-id="device-name-input"] input').fill(name);
    await page.locator('[data-tour-id="device-save-button"]').click();
    await expect(page.locator('[data-tour-id="device-modal-cancel"]')).not.toBeVisible();
  }

  async function mockOnlineBridges(page: import('@playwright/test').Page) {
    await page.route('**/api/bridges', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'b1', name: 'Bridge 1', status: 'online', receivers: [{ id: 'rx_1' }] },
          { id: 'b2', name: 'Bridge 2', status: 'online', receivers: [{ id: 'rx_1' }] },
        ]),
      });
    });
    await page.reload();
  }

  // ─── Happy Path ─────────────────────────────────────────────────────────────

  test('opens modal, shows bridge in selector, starts and closes', async ({ page }) => {
    await mockOnlineBridges(page);
    await createDevice(page);

    await page.locator('[data-tour-id="configure-learn-button"]').click();
    await expect(page.getByRole('heading', { name: 'Learn IR Code' })).toBeVisible();

    // BridgeSelector shows online bridges
    await expect(page.getByText('Bridge 1')).toBeVisible();
    await expect(page.getByText('Bridge 2')).toBeVisible();

    await page.route('**/api/learn?*', async route => {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ status: 'listening' }),
      });
      await page.evaluate(() => {
        (window as { mockWS?: { receive: (d: Record<string, unknown>) => void } })
          .mockWS?.receive({ type: 'learning_status', active: true, bridges: ['any'], mode: 'simple' });
      });
    });

    await page.getByRole('button', { name: 'Start Learning' }).click();
    await expect(page.getByRole('heading', { name: 'Learn IR Code' })).not.toBeVisible();
    await expect(page.locator('[data-tour-id="quick-learn-button"]')).toContainText('Listening...');
  });

  test('sends selected bridge ID as query param when a specific bridge is chosen', async ({ page }) => {
    await mockOnlineBridges(page);
    await createDevice(page);
    await page.locator('[data-tour-id="configure-learn-button"]').click();

    // Select only Bridge 1 in BridgeSelector
    const checkboxes = page.locator('input[type="checkbox"]');
    await checkboxes.first().check();

    let learnUrl = '';
    await page.route('**/api/learn?*', async (route, request) => {
      learnUrl = request.url();
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    await page.getByRole('button', { name: 'Start Learning' }).click();
    await expect.poll(() => learnUrl).toContain('bridges=b1');
    expect(learnUrl).not.toContain('bridges=any');
  });

  // ─── No Bridges Edge Case ───────────────────────────────────────────────────

  test('start button is disabled and select shows no bridges when none online', async ({ page }) => {
    await page.route('**/api/bridges', async route => {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });
    await page.reload();
    await createDevice(page);

    await page.locator('[data-tour-id="configure-learn-button"]').click();
    await expect(page.getByRole('heading', { name: 'Learn IR Code' })).toBeVisible();

    await expect(page.getByRole('button', { name: 'Start Learning' })).toBeDisabled();
    await expect(page.locator('select[disabled]')).toBeVisible();
  });

  // ─── Cancel ─────────────────────────────────────────────────────────────────

  test('cancel button closes the modal without starting learning', async ({ page }) => {
    await mockOnlineBridges(page);
    await createDevice(page);

    await page.locator('[data-tour-id="configure-learn-button"]').click();
    await expect(page.getByRole('heading', { name: 'Learn IR Code' })).toBeVisible();

    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByRole('heading', { name: 'Learn IR Code' })).not.toBeVisible();
    // Quick-learn button should NOT show "Listening..."
    await expect(page.locator('[data-tour-id="quick-learn-button"]')).not.toContainText('Listening...');
  });

  test('clicking backdrop closes the modal', async ({ page }) => {
    await mockOnlineBridges(page);
    await createDevice(page);

    await page.locator('[data-tour-id="configure-learn-button"]').click();
    await expect(page.getByRole('heading', { name: 'Learn IR Code' })).toBeVisible();

    await page.locator('.fixed.inset-0').click({ position: { x: 10, y: 10 } });
    await expect(page.getByRole('heading', { name: 'Learn IR Code' })).not.toBeVisible();
  });

  // ─── Smart Learn ────────────────────────────────────────────────────────────

  test('smart learn toggle enables smart mode', async ({ page }) => {
    await mockOnlineBridges(page);
    await createDevice(page);
    await page.locator('[data-tour-id="configure-learn-button"]').click();

    // Smart learn switch starts off
    const smartToggle = page.locator('.cursor-pointer', { hasText: 'Smart Learn' });
    await smartToggle.click();

    let learnUrl = '';
    await page.route('**/api/learn?*', async (route, request) => {
      learnUrl = request.url();
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    await page.getByRole('button', { name: 'Start Learning' }).click();
    await expect.poll(() => learnUrl).toContain('smart=true');
  });

  test('smart learn is disabled when learning is already active', async ({ page }) => {
    await mockOnlineBridges(page);
    await createDevice(page);

    // Simulate active learning state via WebSocket
    await page.evaluate(() => {
      (window as { mockWS?: { receive: (d: Record<string, unknown>) => void } })
        .mockWS?.receive({ type: 'learning_status', active: true, bridges: ['b1'], mode: 'simple' });
    });

    // When learning is active the quick-learn button reflects "Listening..." state
    await expect(page.locator('[data-tour-id="quick-learn-button"]')).toContainText('Listening...');
  });

  // ─── Learned Code ───────────────────────────────────────────────────────────

  test('received code appears in configure-learn section', async ({ page }) => {
    await mockOnlineBridges(page);
    await createDevice(page);

    // Simulate receiving a learned code via WebSocket
    await page.evaluate(() => {
      (window as { mockWS?: { receive: (d: Record<string, unknown>) => void } })
        .mockWS?.receive({
          type: 'learned_code',
          code: { protocol: 'nec', address: '0x04', command: '0x08' },
          bridge: 'b1',
        });
    });

    // Wait for the floating received-code panel to appear, then dismiss it
    const dismissBtn = page.locator('[data-testid="learn-panel-dismiss"]');
    await dismissBtn.waitFor({ state: 'visible', timeout: 5000 });
    await dismissBtn.click();
    await dismissBtn.waitFor({ state: 'hidden', timeout: 3000 });

    await page.locator('[data-tour-id="configure-learn-button"]').click();
    // After learning, configure dialog should reflect the received code
    await expect(page.getByRole('heading', { name: 'Learn IR Code' })).toBeVisible();
  });
});
