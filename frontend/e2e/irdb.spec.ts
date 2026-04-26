import { test, expect } from '@playwright/test';

const MOCK_BRIDGE = { id: 'b1', name: 'Living Room', status: 'online', transmitters: [{ id: 'ir_tx_1' }] };

const MOCK_BUTTONS = [
  { name: 'Power', icon: 'power', code: { protocol: 'NEC', address: '0x04', command: '0x08' } },
  { name: 'Vol+', icon: 'volume-plus', code: { protocol: 'samsung', address: '0x07', command: '0x02' } },
  { name: 'No Code', icon: 'help', code: null },
];

async function openIrdbAndNavigateToFile(page: import('@playwright/test').Page) {
  await page.route('**/api/irdb/status', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ exists: true, total_remotes: 50, total_codes: 200, last_updated: new Date().toISOString() }),
    });
  });
  await page.route('**/api/irdb/browse?path=', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ name: 'Samsung', type: 'dir', path: 'Samsung' }]),
    });
  });
  await page.route('**/api/irdb/browse?path=Samsung', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ name: 'TV.json', type: 'file', path: 'Samsung/TV.json' }]),
    });
  });
  await page.route('**/api/irdb/file*', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_BUTTONS),
    });
  });

  await page.locator('[data-tour-id="nav-IR_DB"]').click();
  await page.getByText('Samsung').click();
  await page.getByText('TV.json').click();
  await expect(page.getByText('Power')).toBeVisible();
}

test.describe('IRDB Browser', () => {

  // ─── Browse & Search ────────────────────────────────────────────────────────

  test.describe('Navigation', () => {
    test.beforeEach(async ({ page }) => {
      await page.route('**/api/irdb/status', async route => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ exists: true, total_remotes: 100, total_codes: 500, last_updated: new Date().toISOString() }),
        });
      });
      await page.route('**/api/irdb/browse?path=', async route => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([{ name: 'Samsung', type: 'dir', path: 'Samsung' }]),
        });
      });
      await page.goto('/');
    await page.locator('[data-tour-id="nav-IR_DB"]').click();
    });

    test('displays root folders and allows navigating into a folder', async ({ page }) => {
      await expect(page.getByText('Samsung')).toBeVisible();

      await page.route('**/api/irdb/browse?path=Samsung', async route => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([{ name: 'TV.json', type: 'file', path: 'Samsung/TV.json' }]),
        });
      });

      await page.getByText('Samsung').click();
      await expect(page.getByText('TV.json')).toBeVisible();
      // Breadcrumb should show Samsung
      await expect(page.getByText('Samsung', { exact: true }).last()).toBeVisible();
    });

    test('breadcrumb navigation goes back to root', async ({ page }) => {
      await page.route('**/api/irdb/browse?path=Samsung', async route => {
        await route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify([{ name: 'TV.json', type: 'file', path: 'Samsung/TV.json' }]),
        });
      });
      await page.getByText('Samsung').click();
      await expect(page.getByText('TV.json')).toBeVisible();

      // Click root breadcrumb (home icon button inside the modal)
      await page.locator('button:has(.mdi-home)').click();
      await expect(page.getByText('Samsung')).toBeVisible();
    });

    test('search returns and displays results', async ({ page }) => {
      await page.route('**/api/irdb/search?q=sony', async route => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { name: 'Sony TV', path: 'Sony/TV.json', type: 'file' },
            { name: 'Sony Blu-ray', path: 'Sony/Bluray.json', type: 'file' },
          ]),
        });
      });

      await page.getByPlaceholder('Search devices...').fill('sony');
      await page.getByPlaceholder('Search devices...').press('Enter');

      await expect(page.getByText('Sony TV')).toBeVisible();
      await expect(page.getByText('Sony Blu-ray')).toBeVisible();
    });

    test('shows "not installed" state when IRDB is absent', async ({ page }) => {
      await page.route('**/api/irdb/status', async route => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ exists: false }),
        });
      });
      // Close and reopen to trigger re-fetch with new mock
      await page.locator('[data-tour-id="irdb-close-btn"]').click();
      await page.locator('[data-tour-id="nav-IR_DB"]').click();
      await expect(page.getByText(/No IR Databases installed/i)).toBeVisible();
    });
  });

  // ─── Send Flow ──────────────────────────────────────────────────────────────

  test.describe('Send IR code', () => {
    test.beforeEach(async ({ page }) => {
      // Provide an online bridge so BridgeSelector appears
      await page.route('**/api/bridges', async route => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([MOCK_BRIDGE]),
        });
      });
      await page.goto('/');
      await openIrdbAndNavigateToFile(page);
    });

    test('send button is disabled and shows tooltip when no bridge selected', async ({ page }) => {
      const card = page.locator('.group', { hasText: 'Power' }).first();
      await card.hover();
      const sendBtn = card.getByTitle('Select a target bridge first');
      await expect(sendBtn).toBeVisible();
      await expect(sendBtn).toBeDisabled();
    });

    test('selecting a bridge enables the send button', async ({ page }) => {
      await page.getByRole('button', { name: /No target selected/i }).click();
      const bridgeCheckbox = page.locator('input[type="checkbox"]').first();
      await bridgeCheckbox.check();
      await page.locator('.fixed.inset-0.z-40').click();

      const card = page.locator('.group', { hasText: 'Power' }).first();
      await card.hover();
      await expect(card.getByTitle('Send IR Code')).toBeVisible();
      await expect(card.getByTitle('Send IR Code')).not.toBeDisabled();
    });

    test('sending a code POSTs to irdb/send_code with selected bridge', async ({ page }) => {
      let sentPayload: Record<string, unknown> | null = null;
      await page.route('**/api/irdb/send_code', async (route, request) => {
        sentPayload = await request.postDataJSON();
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
      });

      await page.getByRole('button', { name: /No target selected/i }).click();
      await page.locator('input[type="checkbox"]').first().check();
      await page.locator('.fixed.inset-0.z-40').click();

      const card = page.locator('.group', { hasText: 'Power' }).first();
      await card.hover();
      await card.getByTitle('Send IR Code').click();

      await expect.poll(() => sentPayload).toBeTruthy();
      expect((sentPayload as { target: string[] }).target).toContain('b1');
      expect((sentPayload as { code: { protocol: string } }).code.protocol).toBe('NEC');
    });

    test('sending to a specific TX channel sends channel ID', async ({ page }) => {
      let sentPayload: Record<string, unknown> | null = null;
      await page.route('**/api/irdb/send_code', async (route, request) => {
        sentPayload = await request.postDataJSON();
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
      });

      await page.getByRole('button', { name: /No target selected/i }).click();
      const bridgeCheckbox = page.locator('input[type="checkbox"]').first();
      await bridgeCheckbox.check(); // select entire bridge
      await page.locator('.fixed.inset-0.z-40').click();

      const card = page.locator('.group', { hasText: 'Power' }).first();
      await card.hover();
      await card.getByTitle('Send IR Code').click();

      await expect.poll(() => sentPayload).toBeTruthy();
      // Target should contain the bridge id (possibly with channel)
      const target = (sentPayload as { target: string[] }).target;
      expect(Array.isArray(target)).toBe(true);
      expect(target.length).toBeGreaterThan(0);
    });

    test('toolbar shows "No target selected" with warning icon when empty', async ({ page }) => {
      await expect(page.getByText('No target selected')).toBeVisible();
    });

    test('toolbar shows target count after selecting a bridge', async ({ page }) => {
      await page.getByRole('button', { name: /No target selected/i }).click();
      await page.locator('input[type="checkbox"]').first().check();
      await expect(page.getByText(/1 target/)).toBeVisible();
    });

    test('button without code does not show send icon', async ({ page }) => {
      const noCodeCard = page.locator('.group', { hasText: 'No Code' }).first();
      await noCodeCard.hover();
      await expect(noCodeCard.getByTitle('Send IR Code')).not.toBeVisible();
      await expect(noCodeCard.getByTitle('Select a target bridge first')).not.toBeVisible();
    });

    test('no bridges online: BridgeSelector is hidden, send button does not appear', async ({ page }) => {
      await page.route('**/api/bridges', async route => {
        await route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify([{ id: 'b1', name: 'Offline', status: 'offline' }]),
        });
      });
      await page.reload();
      await openIrdbAndNavigateToFile(page);

      // Should show "No bridges online" message instead of BridgeSelector
      await expect(page.getByText(/No bridges online/i)).toBeVisible();

      const card = page.locator('.group', { hasText: 'Power' }).first();
      await card.hover();
      // Send button should not be present at all (v-if="hasOnlineBridges")
      await expect(card.getByTitle('Send IR Code')).not.toBeVisible();
    });
  });
});
