#!/usr/bin/env python3
"""Manage the native WSL services. Build/install dependencies before running up."""
import argparse
import configparser
from datetime import datetime
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
COLLECTOR = ROOT / 'collector'
PREFIX = 'derivatives-monitor-'
SERVICES = [PREFIX + x + '.service' for x in ('collector', 'query', 'dashboard')]
TIMER = PREFIX + 'universe.timer'


def systemctl(*args, check=True):
    return subprocess.run(['systemctl', '--user', *args], check=check)


def quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('\n', '\\n') + '"'


def executable(name, candidates):
    for value in candidates:
        if value and Path(value).is_file() and os.access(value, os.X_OK):
            return str(Path(value).resolve())
    raise RuntimeError('Missing ' + name + '; see collector/README.md native setup')


def install():
    binary = executable('Collector', [COLLECTOR / 'build/Release/bin/data_collector'])
    python = executable('Python 3.12 venv', [ROOT / 'query/.venv/bin/python'])
    # Keep the venv path: resolving its symlink would discard the environment.
    python = str(ROOT / 'query/.venv/bin/python')
    node = executable('Node 22.12+', [os.environ.get('DM_NODE'), shutil.which('node'),
        COLLECTOR / 'build/deps/node-v22.16.0-linux-x64/bin/node'])
    subprocess.run([python, '-c', 'import fastapi, uvicorn; import sys; assert sys.version_info[:2] == (3,12)'], check=True)
    subprocess.run([node, '-e', 'const [a,b]=process.versions.node.split(".").map(Number); if(a<22||(a===22&&b<12))process.exit(1)'], check=True)
    if not (ROOT / 'dashboard/node_modules/vite/bin/vite.js').is_file():
        raise RuntimeError('Run npm ci in dashboard first')
    config = COLLECTOR / 'config.ini'
    if not config.is_file():
        raise RuntimeError('collector/config.ini is required')
    parsed = configparser.ConfigParser(interpolation=None)
    parsed.read(config)
    for key, default in [('DataDirectory', 'data'), ('RunSeconds', '0')]:
        if parsed['config'].get(key, default) != default:
            raise RuntimeError('Native manager requires ' + key + '=' + default)
    units = Path.home() / '.config/systemd/user'
    units.mkdir(parents=True, exist_ok=True)
    updater = f'{quote(python)} {quote(COLLECTOR / "scripts/universe.py")} --data-dir {quote(COLLECTOR / "data")}'
    common = '[Unit]\nStartLimitIntervalSec=0\n\n[Service]\nType=simple\nRestart=on-failure\nRestartSec=10\nTimeoutStopSec=60\nKillSignal=SIGTERM\n'
    definitions = {
        SERVICES[0]: common + f'WorkingDirectory={str(ROOT).replace("%", "%%")}\nExecStartPre=-{updater} --if-needed\nTimeoutStartSec=600\nExecStart={quote(binary)} --config {quote(config)}\n',
        SERVICES[1]: common + f'WorkingDirectory={str(ROOT / "query").replace("%", "%%")}\nEnvironment={quote("DATA_DIR=" + str(COLLECTOR / "data"))}\nExecStart={quote(python)} -m uvicorn app:app --host 127.0.0.1 --port 8000 --no-proxy-headers\n',
        SERVICES[2]: common + f'WorkingDirectory={str(ROOT / "dashboard").replace("%", "%%")}\nExecStart={quote(node)} node_modules/vite/bin/vite.js --host 127.0.0.1 --port 8101 --strictPort\n',
    }
    proxies = ''.join('Environment=' + quote(k + '=' + os.environ[k]) + '\n'
        for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy') if k in os.environ)
    # Startup discovery also needs the same public-network settings.
    definitions[SERVICES[0]] += proxies
    definitions[PREFIX + 'universe.service'] = ('[Unit]\nDescription=Refresh CFFEX public contract universe\n'
        '[Service]\nType=oneshot\nTimeoutStartSec=600\nSuccessExitStatus=2\n' + proxies
        + f'ExecStart={updater} --scheduled --restart-service {SERVICES[0]}\n')
    for name in SERVICES:
        definitions[name] += '\n[Install]\nWantedBy=default.target\n'
    definitions[TIMER] = ('[Unit]\nDescription=CFFEX daily discovery and bounded retries\n[Timer]\n'
        'OnCalendar=*-*-* 08:45:00 Asia/Shanghai\nOnCalendar=*-*-* 09:00,15:00 Asia/Shanghai\n'
        'Persistent=true\nAccuracySec=1s\nUnit=' + PREFIX + 'universe.service\n'
        '[Install]\nWantedBy=timers.target\n')
    # Reject silently taking over another checkout's native units.
    existing = units / SERVICES[0]
    if existing.exists() and str(ROOT) not in existing.read_text():
        raise RuntimeError('Existing native deployment belongs to another checkout')
    for name, text in definitions.items():
        path = units / name
        path.write_text(text)
        path.chmod(0o600)
    subprocess.run(['systemd-analyze', '--user', 'verify', *[str(units / name) for name in definitions]], check=True)
    systemctl('daemon-reload')
    return binary, python


def stop_legacy():
    for name, signature in [('collector', 'data_collector'), ('query', 'uvicorn'), ('dashboard', 'vite')]:
        path = COLLECTOR / 'tmp/runtime' / (name + '.pid')
        if not path.exists():
            continue
        pid = int(path.read_text())
        proc = Path('/proc') / str(pid)
        try:
            cmd = (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode()
            cwd = (proc / 'cwd').resolve()
        except FileNotFoundError:
            path.unlink()
            continue
        if signature not in cmd or not (str(ROOT) in cmd or cwd == ROOT or ROOT in cwd.parents):
            raise RuntimeError('Legacy PID identity changed; refusing to signal ' + str(pid))
        os.kill(pid, signal.SIGTERM)
        for _ in range(600):
            try:
                if (proc / 'stat').read_text().split()[2] == 'Z':
                    break
            except FileNotFoundError:
                break
            time.sleep(.1)
        else:
            raise RuntimeError('Legacy process did not stop normally')
        path.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('up', 'stop', 'status', 'logs', 'update'))
    args = parser.parse_args()
    if args.action == 'up':
        binary, python = install()
        # Prepare the complete candidate before touching the running legacy collector.
        subprocess.run([python, str(COLLECTOR / 'scripts/universe.py'), '--data-dir', str(COLLECTOR / 'data'), '--if-needed'], check=False)
        if not (COLLECTOR / 'data/universe/current/instruments.txt').is_file():
            raise RuntimeError('No discovered universe; current processes unchanged')
        config = COLLECTOR / 'config.ini'
        content = config.read_text()
        lines, section = [], ''
        for line in content.splitlines():
            if line.strip().startswith('['):
                section = line.strip()
            if section == '[config]' and line.partition('=')[0].strip() == 'InstrumentsFile':
                continue
            lines.append(line)
            if line.strip() == '[config]':
                lines.append('InstrumentsFile=data/universe/current/instruments.txt')
        candidate = COLLECTOR / '.config-native.tmp'
        candidate.write_text('\n'.join(lines) + '\n'); candidate.chmod(0o600)
        try:
            subprocess.run([binary, '--config', str(candidate), '--check-config'], check=True)
            backup = COLLECTOR / 'tmp/native-backups'
            backup.mkdir(parents=True, exist_ok=True)
            saved = backup / ('config-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.ini')
            saved.write_text(content); saved.chmod(0o600)
            os.replace(candidate, config)
        finally:
            candidate.unlink(missing_ok=True)
        stop_legacy()
        systemctl('enable', *SERVICES, TIMER)
        systemctl('restart', *SERVICES)
        systemctl('start', TIMER)
        print('看板 http://localhost:8101 ; API http://localhost:8000/docs')
    elif args.action == 'stop':
        systemctl('stop', TIMER, PREFIX + 'universe.service', *SERVICES)
    elif args.action == 'update':
        subprocess.run([str(ROOT / 'query/.venv/bin/python'), str(COLLECTOR / 'scripts/universe.py'),
            '--data-dir', str(COLLECTOR / 'data'), '--restart-service', SERVICES[0]], check=True)
    elif args.action == 'logs':
        subprocess.run(['journalctl', '--user', '-f', '-n', '50', *[x for service in SERVICES for x in ('-u', service)]], check=True)
    else:
        systemctl('status', '--no-pager', *SERVICES, TIMER, check=False)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
