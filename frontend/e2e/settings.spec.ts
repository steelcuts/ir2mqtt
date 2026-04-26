import { test, expect } from '@playwright/test';

test.describe('Settings Page', () => {
  test.beforeEach(async ({ page }) => {
    // Ensure clean state (resets options.yaml too now)
    const resetResponse = await page.request.post('/api/reset');
    expect(resetResponse.ok()).toBeTruthy();
    await page.goto('/#Settings');
    await page.evaluate(() => window.localStorage.clear());
    // Reload to ensure the app initializes with a clean localStorage
    await page.reload();
  });

  test('can change the theme', async ({ page }) => {
    // Expect the default theme to be applied
    await expect(page.locator('body')).toHaveClass(/theme-ha/);

    // Change the theme to "Light"
    await page.locator('[data-tour-id="theme-selector"]').selectOption('theme-light');

    // Expect the new theme to be applied
    await expect(page.locator('body')).toHaveClass(/theme-light/);
    await expect(page.locator('body')).not.toHaveClass(/theme-ha/);

    // Change the theme back to "HA"
    await page.locator('[data-tour-id="theme-selector"]').selectOption('theme-ha');

    // Expect the default theme to be applied again
    await expect(page.locator('body')).toHaveClass(/theme-ha/);
    await expect(page.locator('body')).not.toHaveClass(/theme-light/);
  });

  test('can update log level', async ({ page }) => {
    const select = page.locator('[data-tour-id="settings-log-level"]');
    // Default is INFO
    await expect(select).toHaveValue('INFO');
    
    await Promise.all([
      page.waitForResponse('**/api/settings/log_level'),
      select.selectOption('DEBUG'),
    ]);

    // Reload to verify persistence
    await page.reload();
    await expect(select).toHaveValue('DEBUG');
  });

  test('can update mqtt settings', async ({ page }) => {
    const brokerInput = page.locator('input[placeholder*="192.168.1.10"]');
    await brokerInput.fill('10.0.0.1');
    
    await page.locator('[data-tour-id="settings-mqtt-save"]').click();
    await expect(page.getByText('MQTT settings saved and reloaded.')).toBeVisible();
    
    await page.reload();
    await expect(brokerInput).toHaveValue('10.0.0.1');
  });
  
  test('settings are locked in Home Assistant Add-on environment', async ({ page }) => {
      // Mock the app settings to simulate a locked environment (HA Add-on)
      await page.route('**/api/settings/app', async route => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            mode: 'home_assistant',
            topic_style: 'name',
            locked: true,
            log_level: 'INFO',
            echo_suppression_ms: 500
          })
        });
      });

      await page.reload();

      // Verify Operating Mode is locked
      await expect(page.getByText('Locked by Home Assistant Add-on environment.', { exact: true })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Standalone' })).toBeDisabled();

      // Verify MQTT Connection is locked
      await expect(page.getByText('Locked by Home Assistant Add-on environment. Configure via the Add-on page.')).toBeVisible();
      await expect(page.locator('input[placeholder*="192.168.1.10"]')).toBeDisabled();
      await expect(page.locator('[data-tour-id="settings-mqtt-save"]')).toBeDisabled();
    });

});
