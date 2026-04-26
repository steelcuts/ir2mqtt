// frontend/e2e/devices.spec.ts

import { test, expect } from '@playwright/test';

test.describe('Device CRUD operations', () => {
  test.describe.configure({ mode: 'serial' });

  // Use a unique name for the device in each test file run to avoid collisions across parallel workers
  let deviceName: string;
  let editedDeviceName: string;

  test.beforeEach(async ({ page }, testInfo) => {
    deviceName = `Test Device ${testInfo.parallelIndex}`;
    editedDeviceName = `${deviceName} Edited`;

    // Ensure we are starting from a clean state
    const resetResponse = await page.request.post('/api/reset');
    expect(resetResponse.ok()).toBeTruthy();
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Devices' })).toBeVisible();
  });

  test('should allow a user to create and delete a new device', async ({ page }) => {
    // ------------------- CREATE -------------------
    await page.locator('[data-tour-id="add-device-button"]').click();

    // Fill in device name
    await page.locator('[data-tour-id="device-name-input"] input').fill(deviceName);

    // Save the device
    await page.locator('[data-tour-id="device-save-button"]').click();

    // Wait for the modal to close before proceeding
    await expect(page.locator('[data-tour-id="device-modal-cancel"]')).not.toBeVisible();

    // Verify the new device is in the list
    await expect(page.locator('[data-tour-id="device-card"]', { hasText: deviceName })).toBeVisible();

    // ------------------- DELETE -------------------
    const deviceCard = page.locator('[data-tour-id="device-card"]', { hasText: deviceName });
    
    await deviceCard.locator('[data-tour-id="device-delete-button"]').click();

    // The app uses a custom confirmation modal, not a browser dialog
    await page.locator('.btn-danger', { hasText: 'Confirm' }).click();

    // Verify the device is no longer in the list
    await expect(page.getByText(deviceName)).not.toBeVisible();
  });

  test('should allow a user to edit a device', async ({ page }) => {
    // ------------------- CREATE a device to edit -------------------
    await page.locator('[data-tour-id="add-device-button"]').click();
    await page.locator('[data-tour-id="device-name-input"] input').fill(deviceName);
    await page.locator('[data-tour-id="device-save-button"]').click();
    
    // Wait for modal to close
    await expect(page.locator('[data-tour-id="device-modal-cancel"]')).not.toBeVisible();
    await expect(page.getByText(deviceName)).toBeVisible();
    
    // ------------------- EDIT -------------------
    const deviceCard = page.locator('[data-tour-id="device-card"]', { hasText: deviceName });
    await deviceCard.locator('[data-tour-id="device-edit-button"]').click();

    // Edit the name
    const nameInput = page.locator('[data-tour-id="device-name-input"] input');
    await nameInput.fill(editedDeviceName);

    // Save changes
    await page.locator('[data-tour-id="device-save-button"]').click();

    // Wait for modal to close
    await expect(page.locator('[data-tour-id="device-modal-cancel"]')).not.toBeVisible();

    // Verify the name has been updated
    await expect(page.getByText(editedDeviceName)).toBeVisible();
    await expect(page.getByText(deviceName, { exact: true })).not.toBeVisible();

    // ------------------- CLEANUP: DELETE -------------------
    const editedDeviceCard = page.locator('[data-tour-id="device-card"]', { hasText: editedDeviceName });
    await editedDeviceCard.locator('[data-tour-id="device-delete-button"]').click();
    await page.locator('.btn-danger', { hasText: 'Confirm' }).click();
    await expect(page.getByText(editedDeviceName)).not.toBeVisible();
  });

  test('should allow managing buttons on a device', async ({ page }) => {
    // Create device
    await page.locator('[data-tour-id="add-device-button"]').click();
    await page.locator('[data-tour-id="device-name-input"] input').fill(deviceName);
    await page.locator('[data-tour-id="device-save-button"]').click();
    await expect(page.locator('[data-tour-id="device-modal-cancel"]')).not.toBeVisible();

    const deviceCard = page.locator('[data-tour-id="device-card"]', { hasText: deviceName });
    
    // --- Add Button ---
    await deviceCard.locator('[data-tour-id="add-button-to-device"]').click();
    
    // Button Modal
    const nameInput = page.locator('[data-tour-id="button-name-input"] input');
    await expect(nameInput).toBeVisible();
    await nameInput.fill('Power');
    
    // Select Protocol NEC (assuming standard protocols are available)
    await page.locator('[data-tour-id="button-protocol-select"]').selectOption('nec');
    await page.locator('[data-tour-id="button-address-input"]').fill('0x04');
    await page.locator('[data-tour-id="button-command-input"]').fill('0x01');

    await page.locator('[data-tour-id="button-save-button"]').click();
    
    // Verify creation
    await expect(deviceCard.getByText('Power')).toBeVisible();

    // --- Edit Button ---
    const btn = deviceCard.locator('.group', { hasText: 'Power' });
    await btn.hover();
    await btn.getByTitle('Edit Button').click();
    
    await expect(nameInput).toHaveValue('Power');
    await nameInput.fill('Power Edited');
    await page.locator('[data-tour-id="button-save-button"]').click();
    
    await expect(deviceCard.getByText('Power Edited')).toBeVisible();
    
    // --- Delete Button ---
    await btn.hover();
    await btn.getByTitle(/Delete Button/).click();
    await page.locator('.btn-danger', { hasText: 'Confirm' }).click();
    
    await expect(deviceCard.getByText('Power Edited')).not.toBeVisible();
  });

  test('should allow duplicating a device', async ({ page }) => {
    // Create device
    await page.locator('[data-tour-id="add-device-button"]').click();
    await page.locator('[data-tour-id="device-name-input"] input').fill(deviceName);
    await page.locator('[data-tour-id="device-save-button"]').click();
    await expect(page.locator('[data-tour-id="device-modal-cancel"]')).not.toBeVisible();

    const deviceCard = page.locator('[data-tour-id="device-card"]', { hasText: deviceName });
    
    // Duplicate
    await deviceCard.locator('[data-tour-id="device-duplicate-button"]').click();
    
    // Verify copy exists
    const copyName = `${deviceName} (Copy)`;
    await expect(page.locator('[data-tour-id="device-card"]', { hasText: copyName })).toBeVisible();
  });

  test('should allow duplicating a button', async ({ page }) => {
    // Setup: Create device and button
    await page.locator('[data-tour-id="add-device-button"]').click();
    await page.locator('[data-tour-id="device-name-input"] input').fill(deviceName);
    await page.locator('[data-tour-id="device-save-button"]').click();
    await expect(page.locator('[data-tour-id="device-modal-cancel"]')).not.toBeVisible();
    const deviceCard = page.locator('[data-tour-id="device-card"]', { hasText: deviceName });
    await deviceCard.locator('[data-tour-id="add-button-to-device"]').click();
    await page.locator('[data-tour-id="button-name-input"] input').fill('Power');
    
    // Add protocol to ensure button is valid and visible
    await page.locator('[data-tour-id="button-protocol-select"]').selectOption('nec');
    await page.locator('[data-tour-id="button-address-input"]').fill('0x04');
    await page.locator('[data-tour-id="button-command-input"]').fill('0x01');

    await page.locator('[data-tour-id="button-save-button"]').click();
    
    // Wait for the button to appear in the list (handles refresh/render timing)
    await expect(deviceCard.getByText('Power')).toBeVisible();

    // Duplicate Button
    const btn = deviceCard.locator('.group', { hasText: 'Power' });
    await expect(btn).toBeVisible();
    await btn.hover();
    await btn.getByTitle('Duplicate Button').click();
    
    // Verify copy
    await expect(deviceCard.getByText('Power (Copy)')).toBeVisible();
  });
});

// ─── Send Button Edge Cases ────────────────────────────────────────────────────

test.describe('Device send button behaviour', () => {
  test.describe.configure({ mode: 'serial' });

  const BRIDGE = { id: 'bx1', name: 'Test Bridge', status: 'online' };
  const OFFLINE_BRIDGE = { id: 'bx2', name: 'Offline Bridge', status: 'offline' };

  /** Route the WS so bridges_updated always reports the given bridge list.
   *  Without this, the real backend pushes bridges_updated:{bridges:[]} which
   *  overwrites the REST mock and makes hasOnlineBridges flicker to false. */
  async function mockWsBridges(page: import('@playwright/test').Page, bridges: typeof BRIDGE[]) {
    await page.routeWebSocket('**/ws/events', ws => {
      const server = ws.connectToServer();
      ws.onMessage(msg => server.send(msg));
      server.onMessage(message => {
        try {
          const data = JSON.parse(message as string);
          if (data.type === 'bridges_updated') {
            ws.send(JSON.stringify({ ...data, bridges }));
            return;
          }
        } catch { /* non-JSON frame */ }
        ws.send(message);
      });
    });
  }

  test.beforeEach(async ({ page }) => {
    const reset = await page.request.post('/api/reset');
    expect(reset.ok()).toBeTruthy();
  });

  async function createDeviceWithButton(
    page: import('@playwright/test').Page,
    name: string,
  ) {
    await page.goto('/');
    await page.locator('[data-tour-id="add-device-button"]').click();
    await page.locator('[data-tour-id="device-name-input"] input').fill(name);
    await page.locator('[data-tour-id="device-save-button"]').click();
    await expect(page.locator('[data-tour-id="device-modal-cancel"]')).not.toBeVisible();

    const card = page.locator('[data-tour-id="device-card"]', { hasText: name });
    await card.locator('[data-tour-id="add-button-to-device"]').click();
    await page.locator('[data-tour-id="button-name-input"] input').fill('Power');
    await page.locator('[data-tour-id="button-protocol-select"]').selectOption('nec');
    await page.locator('[data-tour-id="button-address-input"]').fill('0x04');
    await page.locator('[data-tour-id="button-command-input"]').fill('0x01');
    await page.locator('[data-tour-id="button-save-button"]').click();
    await expect(card.getByText('Power')).toBeVisible();
    return card;
  }

  test('send button is enabled in broadcast mode when online bridges exist', async ({ page }) => {
    await mockWsBridges(page, [BRIDGE]);
    await page.route('**/api/bridges', async route => {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify([BRIDGE]),
      });
    });
    await createDeviceWithButton(page, 'No-Target TV');

    // No target bridge selected = broadcast mode: button must be enabled if bridges are online
    const card = page.locator('[data-tour-id="device-card"]', { hasText: 'No-Target TV' });
    const sendBtn = card.locator('button[title="Send IR Code"]');
    await expect(sendBtn).not.toBeDisabled();
  });

  test('send button is disabled in broadcast mode when no bridges are online', async ({ page }) => {
    await page.route('**/api/bridges', async route => {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify([OFFLINE_BRIDGE]),
      });
    });
    await createDeviceWithButton(page, 'No-Bridges TV');

    // No target bridge selected, no online bridges → disabled
    const card = page.locator('[data-tour-id="device-card"]', { hasText: 'No-Bridges TV' });
    const sendBtn = card.locator('button[title="Send IR Code"]');
    await expect(sendBtn).toBeDisabled();
  });

  test('send button is enabled after target bridge is configured', async ({ page }) => {
    await mockWsBridges(page, [BRIDGE]);
    await page.route('**/api/bridges', async route => {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify([BRIDGE]),
      });
    });
    const card = await createDeviceWithButton(page, 'Target TV');

    // Edit device to add a target bridge
    await card.locator('[data-tour-id="device-edit-button"]').click();
    // Select the bridge in target bridge selector
    const targetCheckbox = page.locator('[data-tour-id="device-target-bridges"]')
      .locator('input[type="checkbox"]').first();
    await targetCheckbox.check();
    await page.locator('[data-tour-id="device-save-button"]').click();
    await expect(page.locator('[data-tour-id="device-modal-cancel"]')).not.toBeVisible();

    // Device grid remains visible; verify send button is now enabled
    const sendBtn = card.locator('button[title="Send IR Code"]');
    await expect(sendBtn).not.toBeDisabled();
  });

  test('send button is disabled when target bridge is offline', async ({ page }) => {
    await page.route('**/api/bridges', async route => {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify([OFFLINE_BRIDGE]),
      });
    });
    const card = await createDeviceWithButton(page, 'Offline-Target TV');

    // Edit device — target the offline bridge
    await card.locator('[data-tour-id="device-edit-button"]').click();
    const targetCheckbox = page.locator('[data-tour-id="device-target-bridges"]')
      .locator('input[type="checkbox"]').first();
    await targetCheckbox.check();
    await page.locator('[data-tour-id="device-save-button"]').click();
    await expect(page.locator('[data-tour-id="device-modal-cancel"]')).not.toBeVisible();

    const sendBtn = card.locator('button[title="Send IR Code"]');
    await expect(sendBtn).toBeDisabled();
  });

  test('button without code has send button disabled', async ({ page }) => {
    await page.route('**/api/bridges', async route => {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify([BRIDGE]),
      });
    });
    await page.goto('/');
    await page.locator('[data-tour-id="add-device-button"]').click();
    await page.locator('[data-tour-id="device-name-input"] input').fill('No-Code TV');
    await page.locator('[data-tour-id="device-save-button"]').click();
    await expect(page.locator('[data-tour-id="device-modal-cancel"]')).not.toBeVisible();

    const card = page.locator('[data-tour-id="device-card"]', { hasText: 'No-Code TV' });
    await card.locator('[data-tour-id="add-button-to-device"]').click();
    await page.locator('[data-tour-id="button-name-input"] input').fill('Empty');
    // Do NOT select a protocol — button has no code
    await page.locator('[data-tour-id="button-save-button"]').click();
    await expect(card.getByText('Empty')).toBeVisible();

    // Edit device to add target bridge
    await card.locator('[data-tour-id="device-edit-button"]').click();
    await page.locator('[data-tour-id="device-target-bridges"]')
      .locator('input[type="checkbox"]').first().check();
    await page.locator('[data-tour-id="device-save-button"]').click();
    await expect(page.locator('[data-tour-id="device-modal-cancel"]')).not.toBeVisible();

    const sendBtn = card.locator('button[title="Send IR Code"]');
    await expect(sendBtn).toBeDisabled();
  });
});
