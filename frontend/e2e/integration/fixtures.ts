/**
 * Shared Playwright fixtures for integration tests.
 *
 * Provides:
 *   - `api`       — typed BackendClient for all backend endpoints (no URL construction in tests)
 *   - `sim`       — SimHelper for controlling the simulator
 *   - `resetAll`  — resets backend state + deletes all simulator bridges
 *
 * URL constants (backendUrl, simUrl) are still exposed for the rare case where
 * a test needs them directly (e.g. page.route() interception).
 */

import { test as base, expect, type APIRequestContext } from '@playwright/test';
import { readFileSync, existsSync } from 'fs';
import { join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const RUNTIME_FILE = join(__dirname, '.runtime.json');

interface Runtime {
  backendUrl: string;
  simUrl: string;
}

function readRuntime(): Runtime {
  if (!existsSync(RUNTIME_FILE)) {
    throw new Error(
      '[fixtures] .runtime.json not found. Did globalSetup run?\n' +
      'Run: npm run test:e2e:integration',
    );
  }
  return JSON.parse(readFileSync(RUNTIME_FILE, 'utf-8'));
}

// ─── Backend model types (minimal, only what tests need) ────────────────────

export interface ApiDevice {
  id: string;
  name: string;
  icon: string;
  buttons: ApiButton[];
  target_bridges: string[];
}

export interface ApiButton {
  id: string;
  name: string;
  icon: string;
  is_output: boolean;
  is_input: boolean;
  code: Record<string, unknown> | null;
}

export interface ApiBridge {
  id: string;
  name: string;
  status: 'online' | 'offline';
  last_sent?: unknown[];
  last_received?: unknown[];
}

// ─── BackendClient ───────────────────────────────────────────────────────────
//
// Single place that knows all backend API paths.
// Tests call typed methods — no manual URL construction needed.

export class BackendClient {
  constructor(private readonly req: APIRequestContext, readonly baseUrl: string) {}

  // ── Devices ──────────────────────────────────────────────────────────────

  async getDevices(): Promise<ApiDevice[]> {
    const res = await this.req.get(`${this.baseUrl}/api/devices`);
    expect(res.ok()).toBeTruthy();
    return res.json();
  }

  async createDevice(data: { name: string; icon?: string; target_bridges?: string[] }): Promise<ApiDevice> {
    const res = await this.req.post(`${this.baseUrl}/api/devices`, {
      data: { icon: 'television', buttons: [], target_bridges: [], ...data },
    });
    expect(res.ok()).toBeTruthy();
    return res.json();
  }

  async deleteDevice(deviceId: string): Promise<void> {
    const res = await this.req.delete(`${this.baseUrl}/api/devices/${deviceId}`);
    expect(res.ok()).toBeTruthy();
  }

  // ── Buttons ───────────────────────────────────────────────────────────────

  async addButton(
    deviceId: string,
    data: {
      name: string;
      icon?: string;
      is_output?: boolean;
      code?: { protocol: string; address?: string; command?: string };
    },
  ): Promise<ApiButton> {
    const res = await this.req.post(`${this.baseUrl}/api/devices/${deviceId}/buttons`, {
      data: { icon: 'power', is_output: true, ...data },
    });
    expect(res.ok()).toBeTruthy();
    return res.json();
  }

  async triggerButton(deviceId: string, buttonId: string, targets?: string[]): Promise<void> {
    const url = new URL(`${this.baseUrl}/api/devices/${deviceId}/buttons/${buttonId}/trigger`);
    if (targets?.length) targets.forEach(t => url.searchParams.append('targets', t));
    const res = await this.req.post(url.toString());
    if (!res.ok()) {
      const body = await res.text();
      throw new Error(`triggerButton ${buttonId} failed ${res.status()}: ${body}`);
    }
  }

  // ── Bridges ───────────────────────────────────────────────────────────────

  async getBridges(): Promise<ApiBridge[]> {
    const res = await this.req.get(`${this.baseUrl}/api/bridges`);
    expect(res.ok()).toBeTruthy();
    return res.json();
  }

  async deleteBridge(bridgeId: string): Promise<void> {
    const res = await this.req.delete(`${this.baseUrl}/api/bridges/${bridgeId}`);
    // 404 is fine — bridge may already be gone
    if (!res.ok() && res.status() !== 404) {
      throw new Error(`deleteBridge ${bridgeId} failed ${res.status()}`);
    }
  }

  // ── Status / Reset ────────────────────────────────────────────────────────

  async getStatus(): Promise<{ mqtt_connected: boolean }> {
    const res = await this.req.get(`${this.baseUrl}/api/status`);
    expect(res.ok()).toBeTruthy();
    return res.json();
  }

  async reset(): Promise<void> {
    const res = await this.req.post(`${this.baseUrl}/api/reset`);
    expect(res.ok()).toBeTruthy();
  }
}

// ─── SimBridge / SimHelper ───────────────────────────────────────────────────

export interface SimBridge {
  id: string;
  name: string;
  online: boolean;
  receivers: string[];
  transmitters: string[];
  enabled_protocols: string[];
}

export class SimHelper {
  constructor(
    private readonly req: APIRequestContext,
    readonly url: string,
    private readonly backend: BackendClient,
  ) {}

  async spawn(opts: { bridge_id?: string; bridge_type?: string } = {}): Promise<SimBridge> {
    const res = await this.req.post(`${this.url}/spawn`, { data: opts });
    expect(res.ok()).toBeTruthy();
    const bridge: SimBridge = await res.json();
    await this.waitForBridgeInBackend(bridge.id);
    return bridge;
  }

  async waitForBridgeInBackend(bridgeId: string, timeoutMs = 15_000): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      try {
        const bridges = await this.backend.getBridges();
        if (bridges.some(b => b.id === bridgeId && b.status === 'online')) return;
      } catch { /* retry */ }
      await new Promise(r => setTimeout(r, 400));
    }
    throw new Error(`Bridge ${bridgeId} did not appear as online in backend within ${timeoutMs}ms`);
  }

  async inject(opts: {
    bridge_id: string;
    protocol?: string;
    address?: string;
    command?: string;
    receiver_id?: string;
  }): Promise<void> {
    const res = await this.req.post(`${this.url}/inject`, {
      data: { protocol: 'nec', address: '0x04', command: '0x08', ...opts },
    });
    expect(res.ok()).toBeTruthy();
  }

  async setLoopback(enabled: boolean): Promise<void> {
    const res = await this.req.post(`${this.url}/loopback`, { data: { enabled } });
    expect(res.ok()).toBeTruthy();
  }

  async deleteAll(): Promise<void> {
    const res = await this.req.delete(`${this.url}/bridges`);
    expect(res.ok()).toBeTruthy();
  }

  async deleteBridge(bridgeId: string): Promise<void> {
    const res = await this.req.delete(`${this.url}/bridges/${bridgeId}`);
    if (!res.ok() && res.status() !== 404) {
      throw new Error(`sim.deleteBridge ${bridgeId} failed ${res.status()}`);
    }
  }

  async list(): Promise<SimBridge[]> {
    const res = await this.req.get(`${this.url}/bridges`);
    expect(res.ok()).toBeTruthy();
    return res.json();
  }
}

// ─── Fixture types ────────────────────────────────────────────────────────────

type IntegrationFixtures = {
  backendUrl: string;
  simUrl: string;
  api: BackendClient;
  sim: SimHelper;
  resetAll: () => Promise<void>;
};

// ─── Extended test / expect exports ──────────────────────────────────────────

export const test = base.extend<IntegrationFixtures>({
  // eslint-disable-next-line no-empty-pattern
  backendUrl: async ({}, use) => {
    await use(readRuntime().backendUrl);
  },

  // eslint-disable-next-line no-empty-pattern
  simUrl: async ({}, use) => {
    await use(readRuntime().simUrl);
  },

  api: async ({ request, backendUrl }, use) => {
    await use(new BackendClient(request, backendUrl));
  },

  sim: async ({ request, simUrl, api }, use) => {
    await use(new SimHelper(request, simUrl, api));
  },

  resetAll: async ({ sim, api }, use) => {
    const reset = async () => {
      await sim.deleteAll();
      await new Promise(r => setTimeout(r, 400));
      await api.reset();
    };
    await use(reset);
  },
});

export { expect };
