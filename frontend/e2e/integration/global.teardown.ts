/**
 * Integration test global teardown.
 * Kills python subprocesses and stops the Docker Mosquitto container.
 */

import { execSync } from 'child_process';
import { readFileSync, existsSync, rmSync } from 'fs';
import { join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const PIDS_FILE    = join(__dirname, '.pids.json');
const RUNTIME_FILE = join(__dirname, '.runtime.json');

function log(msg: string) {
  process.stdout.write(`[teardown] ${msg}\n`);
}

export default async function globalTeardown() {
  if (!existsSync(PIDS_FILE)) {
    log('No PIDs file found — nothing to clean up.');
    return;
  }

  const { pids, dockerContainers = [] } =
    JSON.parse(readFileSync(PIDS_FILE, 'utf-8')) as {
      pids: number[];
      dockerContainers: string[];
    };

  // Kill python subprocesses
  for (const pid of pids) {
    try {
      process.kill(-pid, 'SIGTERM');
      log(`Killed process group ${pid}`);
    } catch {
      try {
        process.kill(pid, 'SIGTERM');
        log(`Killed process ${pid}`);
      } catch {
        log(`Process ${pid} already gone`);
      }
    }
  }

  // Stop Docker containers
  for (const name of dockerContainers) {
    try {
      execSync(`docker rm -f ${name}`, { stdio: 'ignore' });
      log(`Removed Docker container ${name}`);
    } catch {
      log(`Container ${name} already gone`);
    }
  }

  await new Promise(r => setTimeout(r, 600));

  for (const f of [PIDS_FILE, RUNTIME_FILE]) {
    if (existsSync(f)) rmSync(f);
  }

  log('Teardown complete.');
}
