"""Run as root on the user's ECS, with a staged release directory argument."""
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request


def run(*args):
    subprocess.run(args,check=True)


def main():
    release=Path(sys.argv[1]).resolve()
    if not str(release).startswith("/opt/anki-analysis/releases/") or not (release/"server/mcp/personal.py").is_file():
        raise ValueError("Invalid isolated release directory")
    root=Path("/opt/anki-analysis")
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup=root/"backups"/stamp
    backup.mkdir(parents=True)
    try:
        subprocess.run(["id","anki-analysis"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        run("useradd","--system","--home-dir","/var/lib/anki-analysis","--shell","/sbin/nologin","anki-analysis")
    run("install","-d","-m","700","-o","anki-analysis","-g","anki-analysis","/var/lib/anki-analysis")
    database=Path("/var/lib/anki-analysis/analysis.sqlite3")
    if database.exists():
        with sqlite3.connect(database) as source, sqlite3.connect(backup/"analysis.sqlite3") as dest:
            source.backup(dest)
    run("python3","-m","venv",str(release/"venv"))
    python=str(release/"venv/bin/python")
    run(python,"-m","pip","install","--disable-pip-version-check","-r",str(release/"server/requirements-personal.txt"))
    subprocess.run([python,"-m","unittest","server.tests.test_personal","-v"],cwd=release,check=True)
    snippet=Path("/etc/nginx/snippets/anki-analysis.inc")
    zone=Path("/etc/nginx/conf.d/anki-analysis-limits.conf")
    service=Path("/etc/systemd/system/anki-analysis.service")
    paths=[snippet,zone,service,Path("/etc/nginx/conf.d/exam-kailang.conf"),Path("/etc/nginx/conf.d/aa-47-109-157-25.sslip.io.conf")]
    original={p:p.read_bytes() if p.exists() else None for p in paths}
    for index,(path,data) in enumerate(original.items()):
        if data is not None: (backup/f"config-{index}-{path.name}").write_bytes(data)
    current=root/"current"
    previous=os.readlink(current) if current.is_symlink() else None
    (backup/"previous-release.txt").write_text(previous or "none")
    try:
        snippet.write_text('''location = /anki-analysis/v1/pair {
    limit_req zone=anki_pair burst=3 nodelay;
    client_max_body_size 2k;
    proxy_pass http://127.0.0.1:8766/v1/pair;
    proxy_read_timeout 35s;
    proxy_set_header Host $host;
    access_log off;
}
location /anki-analysis/ {
    limit_conn anki_analysis_conn 3;
    client_max_body_size 8m;
    client_body_timeout 60s;
    proxy_pass http://127.0.0.1:8766/;
    proxy_request_buffering on;
    proxy_read_timeout 120s;
    proxy_send_timeout 120s;
    proxy_set_header Host $host;
    access_log off;
}
''')
        zone.write_text('''limit_req_zone $binary_remote_addr zone=anki_pair:1m rate=6r/m;
limit_conn_zone $binary_remote_addr zone=anki_analysis_conn:1m;
''')
        for config in paths[3:]:
            text=config.read_text()
            include="include /etc/nginx/snippets/anki-analysis.inc;"
            if include not in text:
                anchor="include /etc/nginx/snippets/anki-updates.inc;"
                if anchor not in text: raise ValueError(f"Missing verified location anchor: {config}")
                config.write_text(text.replace(anchor,anchor+"\n    "+include))
        service.write_text('''[Unit]
Description=Personal Anki analysis snapshots (manual query)
After=network.target
[Service]
User=anki-analysis
Group=anki-analysis
WorkingDirectory=/opt/anki-analysis/current/server
ExecStart=/opt/anki-analysis/current/venv/bin/python -m mcp.personal --database /var/lib/anki-analysis/analysis.sqlite3
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/anki-analysis
MemoryMax=256M
TasksMax=24
[Install]
WantedBy=multi-user.target
''')
        run("nginx","-t")
        temporary=root/"current.next"
        temporary.symlink_to(release)
        temporary.replace(current)
        run("systemctl","daemon-reload")
        run("systemctl","enable","anki-analysis")
        run("systemctl","restart","anki-analysis")
        for attempt in range(15):
            try:
                with urllib.request.urlopen("http://127.0.0.1:8766/healthz",timeout=3) as response:
                    if response.status==200: break
            except OSError:
                if attempt==14: raise
                time.sleep(1)
        run("systemctl","reload","nginx")
        print(f"DEPLOYED {release}\nBACKUP {backup}")
    except BaseException:
        for path,data in original.items():
            if data is None: path.unlink(missing_ok=True)
            else: path.write_bytes(data)
        if previous:
            if current.is_symlink(): current.unlink()
            current.symlink_to(previous)
            run("systemctl","daemon-reload")
            run("systemctl","restart","anki-analysis")
        else:
            subprocess.run(["systemctl","stop","anki-analysis"])
        run("nginx","-t")
        run("systemctl","reload","nginx")
        raise


if __name__=="__main__": main()
