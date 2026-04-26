import { test, expect } from '@playwright/test';

test.describe('Config Transfer', () => {
  test.beforeEach(async ({ page }) => {
    const resetResponse = await page.request.post('/api/reset');
    expect(resetResponse.ok()).toBeTruthy();
    await page.goto('/#Settings');
  });

  test('should allow exporting configuration', async ({ page }) => {
    // Mock export API
    await page.route('**/api/config/export', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          devices: [{ id: 'd1', name: 'Test Device', buttons: [] }],
          automations: []
        })
      });
    });

    await page.locator('[data-tour-id="settings-config-card"] button').click();
    await expect(page.locator('[data-tour-id="config-transfer-modal"]')).toBeVisible();

    // Check if tree view shows the device
    await expect(page.getByText('Test Device')).toBeVisible();

    // Check if download button is visible
    await expect(page.locator('[data-tour-id="config-action-button"]', { hasText: 'Download Selected' })).toBeVisible();
  });
});