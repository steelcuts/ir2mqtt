import { test, expect } from '@playwright/test';

test.describe('Automation CRUD operations', () => {

  const deviceName = 'Test TV for Automations';
  const automationName = 'Test Automation';

  test.beforeEach(async ({ page }) => {
    // Factory reset to ensure a clean state
    const resetResponse = await page.request.post('/api/reset');
    expect(resetResponse.ok()).toBeTruthy();
    await page.goto('/');

    // Create a device from a template so we have triggers/actions available
    await page.locator('[data-tour-id="add-device-button"]').click();
    
    // Select the "TV" template
    await page.locator('select:near(:text("Initialize Device"))').selectOption({ label: 'TV' });
    
    // Fill in a unique name
    await page.locator('[data-tour-id="device-name-input"] input').fill(deviceName);

    // Save the device
    await page.locator('[data-tour-id="device-save-button"]').click();
    
    // Wait for the modal to close and verify the device is there
    await expect(page.locator('[data-tour-id="device-modal-cancel"]')).not.toBeVisible();
    await expect(page.getByText(deviceName)).toBeVisible();

    // Navigate to the automations page for the tests
    await page.locator('[data-tour-id="nav-Automations"]').click();
    await expect(page.getByRole('heading', { name: 'Automations' })).toBeVisible();
  });

  test('should allow a user to create and delete an automation', async ({ page }) => {
    // ------------------- CREATE -------------------
    await page.locator('[data-tour-id="create-automation-button"]').click();

    // --- Fill out the modal ---
    const modal = page.locator('[data-tour-id="automation-modal"]');
    
    // 1. Set name
    await modal.locator('[data-tour-id="automation-name-input"] input').fill(automationName);
    
    // 2. Configure Trigger
    const trigger = modal.locator('[data-tour-id="automation-trigger-device-selection"]');
    await trigger.locator('select').first().selectOption({ label: deviceName });
    await trigger.locator('select').last().selectOption({ label: 'Power' });

    // 3. Configure Action
    await modal.getByRole('button', { name: 'Add Command' }).click();
    
    // The action item is the only draggable element in this context
    const action = modal.locator('[draggable="true"]');
    await expect(action).toBeVisible();

    await action.locator('select').first().selectOption({ label: deviceName });
    await action.locator('select').last().selectOption({ label: 'Volume Up' });
    
    // 4. Save
    await modal.locator('[data-tour-id="automation-save-button"]').click();

    // --- Verify Creation ---
    await expect(modal).not.toBeVisible();
    
    const autoCard = page.locator('[data-tour-id="automation-card"]', { hasText: automationName });
    await expect(autoCard).toBeVisible();
    
    // Check if trigger and action are displayed correctly
    await expect(autoCard.getByText('Power')).toBeVisible();
    await expect(autoCard.getByText('Volume Up')).toBeVisible();

    // ------------------- DELETE -------------------
    const deleteButton = autoCard.getByTitle(/Delete Automation/);
    await expect(deleteButton).toBeVisible();
    await deleteButton.click();
    
    // Confirm deletion
    await page.locator('.btn-danger', { hasText: 'Confirm' }).click();

    // Verify the automation is gone
    await expect(autoCard).not.toBeVisible();
    await expect(page.getByText('No automations defined yet.')).toBeVisible();
  });

  test('should allow editing an automation', async ({ page }) => {
    // --- CREATE (Setup) ---
    await page.locator('[data-tour-id="create-automation-button"]').click();
    const modal = page.locator('[data-tour-id="automation-modal"]');
    
    await modal.locator('[data-tour-id="automation-name-input"] input').fill(automationName);
    
    const trigger = modal.locator('[data-tour-id="automation-trigger-device-selection"]');
    await trigger.locator('select').first().selectOption({ label: deviceName });
    await trigger.locator('select').last().selectOption({ label: 'Power' });

    await modal.getByRole('button', { name: 'Add Command' }).click();
    const action = modal.locator('[draggable="true"]');
    await action.locator('select').first().selectOption({ label: deviceName });
    await action.locator('select').last().selectOption({ label: 'Volume Up' });
    
    await modal.locator('[data-tour-id="automation-save-button"]').click();
    await expect(modal).not.toBeVisible();

    // --- EDIT ---
    const autoCard = page.locator('[data-tour-id="automation-card"]', { hasText: automationName });
    await autoCard.getByTitle('Edit Automation').click();
    
    await expect(modal).toBeVisible();
    
    // Change Name
    const newName = automationName + ' Edited';
    await modal.locator('[data-tour-id="automation-name-input"] input').fill(newName);
    
    // Save
    await modal.locator('[data-tour-id="automation-save-button"]').click();
    
    await expect(modal).not.toBeVisible();
    await expect(page.locator('[data-tour-id="automation-card"]', { hasText: newName })).toBeVisible();
  });

  test('should allow duplicating an automation', async ({ page }) => {
    // --- CREATE (Setup) ---
    await page.locator('[data-tour-id="create-automation-button"]').click();
    const modal = page.locator('[data-tour-id="automation-modal"]');
    await modal.locator('[data-tour-id="automation-name-input"] input').fill(automationName);
    
    const trigger = modal.locator('[data-tour-id="automation-trigger-device-selection"]');
    await trigger.locator('select').first().selectOption({ label: deviceName });
    await trigger.locator('select').last().selectOption({ label: 'Power' });

    await modal.getByRole('button', { name: 'Add Command' }).click();
    const action = modal.locator('[draggable="true"]');
    await action.locator('select').first().selectOption({ label: deviceName });
    await action.locator('select').last().selectOption({ label: 'Volume Up' });
    
    await modal.locator('[data-tour-id="automation-save-button"]').click();
    await expect(modal).not.toBeVisible();

    // --- DUPLICATE ---
    const autoCard = page.locator('[data-tour-id="automation-card"]', { hasText: automationName });
    await autoCard.getByTitle('Duplicate Automation').click();
    
    // Verify Copy
    const copyName = `${automationName} (Copy)`;
    await expect(page.locator('[data-tour-id="automation-card"]', { hasText: copyName })).toBeVisible();
  });
});