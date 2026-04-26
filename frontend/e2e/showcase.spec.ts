/**
 * Showcase GIF spec.
 *
 * Requires the full simulation stack started by scripts/generate-gif.sh:
 *   Mosquitto → Backend (with real MQTT) → Sim-server → pre-spawned bridge
 *
 * No REST or WebSocket mocks are used. The only WS override is
 * mqtt_status → connected: true so the UI reliably shows the green indicator
 * regardless of connection timing.
 *
 * Environment variables set by generate-gif.sh:
 *   BACKEND_URL   Base URL of the backend (e.g. http://127.0.0.1:8198)
 *   SIM_URL       Sim-server control API  (e.g. http://127.0.0.1:8092)
 *   BRIDGE_ID     ID of the pre-spawned virtual bridge
 */

import { test, expect, BrowserContext, Page } from '@playwright/test';
import { delay, scrollTo, naturalClick, SIM_URL, BRIDGE_ID } from './doc-gifs/helpers';

test.describe.serial('Showcase UI', { tag: '@showcase' }, () => {
  let context: BrowserContext;
  let page: Page;

  test.beforeAll(async ({ browser, request }) => {
    test.setTimeout(30_000);
    console.log('--- Setup: Resetting backend ---');
    await request.post('/api/reset?keep_irdb=true');

    // After reset the sim-server bridge keeps broadcasting via MQTT — wait for
    // the backend to re-register it before we start recording.
    await expect(async () => {
      const res = await request.get('/api/bridges');
      const json = await res.json();
      expect(json.some((b: { status: string }) => b.status === 'online')).toBe(true);
    }).toPass({ timeout: 15_000 });
    console.log('--- Setup: Bridge online ---');

    context = await browser.newContext({
      recordVideo: { dir: 'test-results/' },
      viewport: { width: 1280, height: 720 },
    });
    page = await context.newPage();

    // Proxy WS to the real backend. Only override mqtt_status so the green
    // MQTT indicator is stable from frame 1 of the recording.
    await page.routeWebSocket('**/ws/events', ws => {
      const server = ws.connectToServer();
      ws.onMessage(msg => server.send(msg));
      server.onMessage(message => {
        try {
          const data = JSON.parse(message as string);
          if (data.type === 'mqtt_status') {
            data.connected = true;
            ws.send(JSON.stringify(data));
            return;
          }
        } catch { /* ignore binary frames */ }
        ws.send(message);
      });
      ws.send(JSON.stringify({ type: 'mqtt_status', connected: true }));
    });

    await page.goto('/#Bridges');
  });

  test.afterAll(async () => {
    if (context) await context.close();
  });

  // ── Step 1: View Bridges ───────────────────────────────────────────────────

  test('Step 1: View Bridges', async () => {
    test.setTimeout(10_000);
    console.log('--- Step 1: View Bridges ---');
    await delay(1500);
  });

  // ── Step 2: Create a device ────────────────────────────────────────────────

  test('Step 2: Go to Devices and Create a Device', async () => {
    test.setTimeout(20_000);
    console.log('--- Step 2: Go to Devices and Create a Device ---');

    await naturalClick(page.locator('[data-tour-id="nav-Devices"]'));
    await delay(500);

    await naturalClick(page.locator('[data-tour-id="add-device-button"]'));

    const deviceNameInput = page.locator('[data-tour-id="device-name-input"] input');
    await scrollTo(page, deviceNameInput);
    await deviceNameInput.fill('Samsung TV');
    await delay(500);

    const saveBtn = page.locator('[data-tour-id="device-save-button"]');
    await scrollTo(page, saveBtn);
    await naturalClick(saveBtn);
    await delay(1000);
  });

  // ── Step 3: Add a button manually ─────────────────────────────────────────

  test('Step 3: Add a Power Button', async () => {
    test.setTimeout(20_000);
    console.log('--- Step 3: Add a Power Button ---');

    const deviceCard = page.locator('[data-tour-id="device-card"]', { hasText: 'Samsung TV' });
    await naturalClick(deviceCard.locator('[data-tour-id="add-button-to-device"]'));
    await delay(500);

    const nameInput = page.locator('[data-tour-id="button-name-input"] input');
    await scrollTo(page, nameInput);
    await nameInput.fill('Power');
    await delay(500);

    const protocolSelect = page.locator('[data-tour-id="button-protocol-select"]');
    await scrollTo(page, protocolSelect);
    await protocolSelect.selectOption('nec');
    await delay(500);

    const addressInput = page.locator('[data-tour-id="button-address-input"]');
    await scrollTo(page, addressInput);
    await addressInput.fill('0x0707');
    await delay(500);

    const commandInput = page.locator('[data-tour-id="button-command-input"]');
    await scrollTo(page, commandInput);
    await commandInput.fill('0x02');
    await delay(500);

    const saveBtn = page.locator('[data-tour-id="button-save-button"]');
    await scrollTo(page, saveBtn);
    await naturalClick(saveBtn);
    await delay(1000);
  });

  // ── Step 4: Add a button from IR database ─────────────────────────────────

  test('Step 4: Add a Button from IRDB', async () => {
    test.setTimeout(40_000);
    console.log('--- Step 4: Add a Button from IRDB ---');

    const deviceCard = page.locator('[data-tour-id="device-card"]', { hasText: 'Samsung TV' });
    await naturalClick(deviceCard.locator('[data-tour-id="add-button-to-device"]'));
    await delay(500);

    const browseDbBtn = page.locator('[data-tour-id="button-browse-db"]');
    await scrollTo(page, browseDbBtn);
    await naturalClick(browseDbBtn);
    await delay(1000);

    // Search for a known file so we land on something with buttons
    const searchInput = page.locator('[data-tour-id="irdb-search-input"] input');
    await searchInput.waitFor({ state: 'visible', timeout: 5000 });
    await searchInput.fill('Samsung_TV');
    await delay(800);

    // Search results are files only — click the first one
    const firstFile = page.locator('.group').filter({ has: page.locator('.mdi-file-document-outline') }).first();
    await firstFile.waitFor({ state: 'visible', timeout: 8000 });
    await firstFile.evaluate(el => el.scrollIntoView({ block: 'center', behavior: 'smooth' }));
    await delay(300);
    await firstFile.click();
    await delay(800);

    // First button in the file view has data-tour-id="irdb-first-button"
    const firstDbButton = page.locator('[data-tour-id="irdb-first-button"]');
    await firstDbButton.waitFor({ state: 'visible', timeout: 10_000 });
    await scrollTo(page, firstDbButton);
    await naturalClick(firstDbButton);
    await delay(1000);

    const saveBtn = page.locator('[data-tour-id="button-save-button"]');
    await scrollTo(page, saveBtn);
    await naturalClick(saveBtn);
    await delay(1000);
  });

  // ── Step 5: Add a button without a code (to assign via quick-learn) ────────

  test('Step 5: Add a Mute Button (without code)', async () => {
    test.setTimeout(20_000);
    console.log('--- Step 5: Add a Mute Button (without code) ---');

    const deviceCard = page.locator('[data-tour-id="device-card"]', { hasText: 'Samsung TV' });
    await naturalClick(deviceCard.locator('[data-tour-id="add-button-to-device"]'));
    await delay(500);

    const nameInput = page.locator('[data-tour-id="button-name-input"] input');
    await scrollTo(page, nameInput);
    await nameInput.fill('Mute');
    await delay(500);

    const saveBtn = page.locator('[data-tour-id="button-save-button"]');
    await scrollTo(page, saveBtn);
    await naturalClick(saveBtn);
    await delay(1000);
  });

  // ── Step 6: Quick-learn — inject a real IR signal via sim-server ───────────

  test('Step 6: Show quick learn & Assign Code', async () => {
    test.setTimeout(25_000);
    console.log('--- Step 6: Show quick learn & Assign Code ---');

    const deviceCard = page.locator('[data-tour-id="device-card"]', { hasText: 'Samsung TV' });

    await naturalClick(page.locator('[data-tour-id="quick-learn-button"]'));
    await delay(1500);

    // Inject a real IR signal: sim-server → MQTT → backend → WebSocket → UI
    await page.request.post(`${SIM_URL}/inject`, {
      data: {
        bridge_id: BRIDGE_ID,
        protocol: 'nec',
        address: '0x04',
        command: '0x08',
      },
    });
    await delay(1500);

    // Assign the received code to the Mute button
    const muteBtn = deviceCard.locator('.group', { hasText: 'Mute' });
    await muteBtn.hover();
    await delay(500);
    await muteBtn.locator('.absolute.inset-0').click({ force: true });
    await delay(500);

    // Move the mouse away so the hover overlay disappears
    await page.mouse.move(0, 0);
    await delay(1500);
  });

  // ── Step 7: Send an IR command ─────────────────────────────────────────────

  test('Step 7: Click a button to show interaction', async () => {
    test.setTimeout(10_000);
    console.log('--- Step 7: Click a button to show interaction ---');

    const deviceCard = page.locator('[data-tour-id="device-card"]', { hasText: 'Samsung TV' });
    const powerBtn = deviceCard.locator('.group', { hasText: 'Power' }).first();
    await powerBtn.hover();
    await delay(500);

    const sendIrBtn = deviceCard.locator('button[title="Send IR Code"]').first();
    await naturalClick(sendIrBtn);
    await delay(1000);
  });

  // ── Step 8: Create an automation ──────────────────────────────────────────

  test('Step 8: Go to Automations', async () => {
    test.setTimeout(40_000);
    console.log('--- Step 8: Go to Automations ---');

    await naturalClick(page.locator('[data-tour-id="nav-Automations"]'));
    await delay(1500);

    await naturalClick(page.locator('[data-tour-id="create-automation-button"]'));
    await delay(500);

    const modal = page.locator('[data-tour-id="automation-modal"]');

    const nameInput = modal.locator('[data-tour-id="automation-name-input"] input');
    await scrollTo(page, nameInput);
    await nameInput.fill('Evening Setup');
    await delay(500);

    const trigger = modal.locator('[data-tour-id="automation-trigger-device-selection"]');
    await scrollTo(page, trigger);
    await trigger.locator('select').first().selectOption({ label: 'Samsung TV' });
    await delay(400);
    await trigger.locator('select').last().selectOption({ label: 'Power' });
    await delay(600);

    // Action 1: Event
    const addEventBtn = modal.getByRole('button', { name: /Add (HA )?Event/ });
    await scrollTo(page, addEventBtn);
    await naturalClick(addEventBtn);
    await delay(500);
    const eventInput = modal.locator('[draggable="true"]').last().locator('input').first();
    await scrollTo(page, eventInput);
    await eventInput.fill('cinema_mode');
    await delay(600);

    // Action 2: Delay
    const addDelayBtn = modal.getByRole('button', { name: 'Add Delay' });
    await scrollTo(page, addDelayBtn);
    await naturalClick(addDelayBtn);
    await delay(500);
    const delayInput = modal.locator('[draggable="true"]').last().locator('input').first();
    await scrollTo(page, delayInput);
    await delayInput.fill('2000');
    await delay(600);

    // Action 3: IR Command
    const addCommandBtn = modal.getByRole('button', { name: 'Add Command' });
    await scrollTo(page, addCommandBtn);
    await naturalClick(addCommandBtn);
    await delay(500);
    const actionCmd = modal.locator('[draggable="true"]').last();
    await scrollTo(page, actionCmd);
    await actionCmd.locator('select').first().selectOption({ label: 'Samsung TV' });
    await delay(400);
    await actionCmd.locator('select').last().selectOption({ index: 1 });
    await delay(600);

    const saveBtn = modal.locator('[data-tour-id="automation-save-button"]');
    await scrollTo(page, saveBtn);
    await naturalClick(saveBtn);
    await delay(1500);

    // Trigger the automation to show the visual progress flow
    console.log('--- Triggering automation to show visual flow ---');
    const autoCard = page.locator('[data-tour-id="automation-card"]', { hasText: 'Evening Setup' });
    await scrollTo(page, autoCard);
    const playBtn = autoCard.locator('button').filter({ has: page.locator('.mdi-play-circle-outline') });
    await naturalClick(playBtn);

    // Wait for the 2 s delay action + IR send to complete visually
    await delay(4000);
  });

  // ── Step 9: Status page ────────────────────────────────────────────────────

  test('Step 9: Go to Status', async () => {
    test.setTimeout(15_000);
    console.log('--- Step 9: Go to Status ---');

    await naturalClick(page.locator('[data-tour-id="nav-Status"]'));
    await delay(1500);

    const logBox = page.locator('#log-box');
    await scrollTo(page, logBox);
    await delay(2000);
  });

  // ── Step 10: Settings ──────────────────────────────────────────────────────

  test('Step 10: Go to Settings', async () => {
    test.setTimeout(10_000);
    console.log('--- Step 10: Go to Settings ---');

    await naturalClick(page.locator('[data-tour-id="nav-Settings"]'));
    await delay(1500);
  });

  // ── Step 11: Languages & themes ───────────────────────────────────────────

  test('Step 11: Show available languages and themes', async () => {
    test.setTimeout(20_000);
    console.log('--- Step 11: Show available languages and themes ---');

    const languageSelect = page.locator('.card').first().locator('select').first();
    await scrollTo(page, languageSelect);
    await languageSelect.focus();
    await delay(400);
    await languageSelect.selectOption('de');
    await delay(1500);
    await languageSelect.selectOption('en');
    await delay(1000);

    const themeSelect = page.locator('[data-tour-id="theme-selector"]');
    await scrollTo(page, themeSelect);
    await themeSelect.focus();
    await delay(400);
    await themeSelect.selectOption('theme-light');
    await delay(1500);
    await themeSelect.selectOption('theme-ha');
    await delay(1000);
  });

  // ── Step 12: Scroll through remaining settings ────────────────────────────

  test('Step 12: Scroll through the rest of the settings', async () => {
    test.setTimeout(15_000);
    console.log('--- Step 12: Scroll through the rest of the settings ---');

    await scrollTo(page, page.locator('[data-tour-id="settings-mqtt-card"]'));
    await delay(2000);

    await scrollTo(page, page.locator('[data-tour-id="settings-loopback-card"]'));
    await delay(2000);

    await page.locator('[data-tour-id="settings-danger-zone"]')
      .evaluate(el => el.scrollIntoView({ block: 'end', behavior: 'smooth' }));
    await delay(2000);

    console.log('--- Showcase UI Test Finished ---');
  });
});
