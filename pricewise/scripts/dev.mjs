import { spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';

const apiPort = process.env.API_PORT || '8000';
const candidates = [
  path.join(process.cwd(), '.venv', 'Scripts', 'python.exe'),
  path.join(process.cwd(), '.venv', 'bin', 'python'),
  process.env.PYTHON,
  'python',
].filter(Boolean);
const pythonCmd = candidates.find(cmd => !cmd.includes(path.sep) || fs.existsSync(cmd)) || 'python';

const api = spawn(pythonCmd, ['server/app.py'], {
  stdio: 'inherit',
  env: { ...process.env, API_PORT: apiPort, PYTHONUNBUFFERED: '1' },
});
const children = [api];
let stopping = false;

function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  children.forEach(child => {
    try { child.kill('SIGTERM'); } catch {}
  });
  setTimeout(() => process.exit(code), 300);
}

api.on('error', err => {
  console.error(`Could not start the Python backend (${pythonCmd}): ${err.message}`);
  stop(1);
});
api.on('exit', code => {
  if (!stopping) {
    console.error(`The Python backend exited (code ${code ?? 1}). Make sure Python packages from requirements.txt are installed.`);
    stop(code || 1);
  }
});

function waitForBackend(attempts = 40) {
  const req = http.get(`http://127.0.0.1:${apiPort}/api/health`, res => {
    res.resume();
    if (res.statusCode === 200) {
      const vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js'], {
        stdio: 'inherit',
        env: { ...process.env, API_PORT: apiPort },
      });
      children.push(vite);
      vite.on('exit', code => { if (!stopping) stop(code || 0); });
    } else if (attempts > 0 && !stopping) {
      setTimeout(() => waitForBackend(attempts - 1), 250);
    }
  });
  req.on('error', () => {
    if (attempts > 0 && !stopping) setTimeout(() => waitForBackend(attempts - 1), 250);
    else if (!stopping) {
      console.error(`Backend did not respond on http://127.0.0.1:${apiPort}/api/health.`);
      stop(1);
    }
  });
}

waitForBackend();
process.on('SIGINT', () => stop());
process.on('SIGTERM', () => stop());
