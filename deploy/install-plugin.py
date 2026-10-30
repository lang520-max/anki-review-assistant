"""Isolated ChatGPT read-only bridge; preserve the existing phone upload service."""
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import urllib.request


def run(*args, **kwargs):
    subprocess.run(args,check=True,**kwargs)


def main():
    release = Path(sys.argv[1]).resolve()
    root = Path("/opt/anki-plugin")
    if release.parent != root/"releases" or not (release/"server/mcp/personal_plugin.py").is_file():
        raise ValueError("Invalid isolated plugin release")
    run("id","anki-analysis",stdout=subprocess.DEVNULL)
    run("install","-d","-m","700","-o","anki-analysis","-g","anki-analysis","/var/lib/anki-plugin")
    backup = root/"backups"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup.mkdir(parents=True)
    database = Path("/var/lib/anki-plugin/auth.sqlite3")
    if database.exists():
        with sqlite3.connect(database) as source, sqlite3.connect(backup/"auth.sqlite3") as target:
            source.backup(target)
    run("python3","-m","venv",str(release/"venv"))
    python = str(release/"venv/bin/python")
    run(python,"-m","pip","install","--disable-pip-version-check","-r",str(release/"server/requirements-plugin.txt"))
    run(python,"-m","unittest","server.tests.test_personal_plugin","-v",cwd=release)
    snippet = Path("/etc/nginx/snippets/anki-plugin.inc")
    zone = Path("/etc/nginx/conf.d/anki-plugin-limits.conf")
    service = Path("/etc/systemd/system/anki-plugin.service")
    sites = [Path("/etc/nginx/conf.d/exam-kailang.conf"),Path("/etc/nginx/conf.d/aa-47-109-157-25.sslip.io.conf")]
    paths = [snippet,zone,service,*sites]
    original = {p:p.read_bytes() if p.exists() else None for p in paths}
    for i,(p,content) in enumerate(original.items()):
        if content is not None:
            (backup/f"config-{i}-{p.name}").write_bytes(content)
    current = root/"current"
    previous = os.readlink(current) if current.is_symlink() else None
    (backup/"previous-release.txt").write_text(previous or "none")
    try:
        proxy = '''    client_max_body_size 8k;
    proxy_pass http://127.0.0.1:8767;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_buffering off;
    proxy_read_timeout 90s;
    access_log off;
'''
        snippet.write_text('''location = /anki-plugin/register {
    limit_req zone=anki_plugin_login burst=3 nodelay;
'''+proxy+'''}
location = /anki-plugin/connect {
    limit_req zone=anki_plugin_login burst=3 nodelay;
'''+proxy+'''}
location /anki-plugin/ {
    limit_req zone=anki_plugin_rpc burst=20 nodelay;
'''+proxy+'''}
location = /.well-known/oauth-authorization-server/anki-plugin {
'''+proxy+'''}
location = /.well-known/oauth-protected-resource/anki-plugin/mcp {
'''+proxy+'''}
''')
        zone.write_text('''limit_req_zone $binary_remote_addr zone=anki_plugin_login:1m rate=12r/m;
limit_req_zone $binary_remote_addr zone=anki_plugin_rpc:1m rate=120r/m;
''')
        for site in sites:
            content = site.read_text()
            include = "include /etc/nginx/snippets/anki-plugin.inc;"
            anchor = "include /etc/nginx/snippets/anki-analysis.inc;"
            if include not in content:
                if anchor not in content:
                    raise ValueError("Verified analysis location anchor missing")
                site.write_text(content.replace(anchor,anchor+"\n    "+include))
        service.write_text('''[Unit]
Description=Private Anki ChatGPT read-only plugin
After=network.target anki-analysis.service
[Service]
User=anki-analysis
Group=anki-analysis
WorkingDirectory=/opt/anki-plugin/current
ExecStart=/opt/anki-plugin/current/venv/bin/python -m server.mcp.personal_plugin
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/anki-plugin
ReadOnlyPaths=/var/lib/anki-analysis
MemoryMax=192M
TasksMax=32
[Install]
WantedBy=multi-user.target
''')
        run("nginx","-t")
        temporary = root/"current.next"
        temporary.symlink_to(release)
        temporary.replace(current)
        run("systemctl","daemon-reload")
        run("systemctl","enable","anki-plugin")
        run("systemctl","restart","anki-plugin")
        for attempt in range(20):
            try:
                with urllib.request.urlopen("http://127.0.0.1:8767/anki-plugin/healthz",timeout=3) as response:
                    if response.status==200:
                        break
            except OSError:
                if attempt==19:
                    raise
                time.sleep(1)
        run("systemctl","reload","nginx")
        print(f"DEPLOYED {release}\nBACKUP {backup}")
    except BaseException:
        for path,content in original.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        if previous:
            if current.is_symlink():
                current.unlink()
            current.symlink_to(previous)
            run("systemctl","daemon-reload")
            run("systemctl","restart","anki-plugin")
        else:
            subprocess.run(["systemctl","stop","anki-plugin"])
            subprocess.run(["systemctl","disable","anki-plugin"])
            # Remove the failed first release pointer, preserving all release files.
            if current.is_symlink():
                current.unlink()
        run("nginx","-t")
        run("systemctl","reload","nginx")
        raise


if __name__=="__main__":
    main()
