import { test, expect } from '@playwright/test';

test.describe('IR2MQTT App', () => {
  test.beforeEach(async ({ page }) => {
    // Factory reset before each test to ensure a clean state
    const resetResponse = await page.request.post('/api/reset');
    expect(resetResponse.ok()).toBeTruthy();
    await page.goto('/');
  });

  test('has title', async ({ page }) => {
    await expect(page).toHaveTitle(/IR2MQTT/);
  });

  test('shows devices page by default', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Devices' })).toBeVisible();
    
    await expect(page.locator('[data-tour-id="no-devices-message"]')).toBeVisible();
  });

  test('can navigate to Automations', async ({ page }) => {
    await page.locator('[data-tour-id="nav-Automations"]').click();
    
    await expect(page).toHaveURL(/.*#Automations/);
    await expect(page.getByRole('heading', { name: 'Automations' })).toBeVisible();
  });

  test('can navigate to Bridges', async ({ page }) => {
    await page.locator('[data-tour-id="nav-Bridges"]').click();
    
    await expect(page).toHaveURL(/.*#Bridges/);
    await expect(page.getByRole('heading', { name: 'Bridges' })).toBeVisible();
  });

  test('can navigate to Settings', async ({ page }) => {
    await page.locator('[data-tour-id="nav-Settings"]').click();
    
    await expect(page).toHaveURL(/.*#Settings/);
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
  });
});
