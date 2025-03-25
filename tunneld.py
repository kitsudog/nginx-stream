import os
import re
from collections import ChainMap
from typing import List


def init_env():
    if os.path.exists(".env"):
        with open(".env") as fin:
            for kv in fin.read().splitlines(keepends=False):
                k, _, v = kv.strip().partition("=")
                os.environ[k] = v


init_env()
# 受限的-D模式
# SSHD_1=root@:22|:443|=>api.openai.com
# SSHD_1=root@:22|127.0.0.1:443|127.0.0.1:443=>api.openai.com
# ssh -L 0.0.0.0:10443:127.0.0.1:443 -p 22 root@local.orb.local
expr1 = re.compile(
    r'((?P<SSH_USER>[^@:|]+)@)?(:(?P<SSH_PORT>\d+))'
    '\|'
    '(:(?P<SSH_LOCAL_PORT>\d+))'
    '\|'
    '(?P<SSH_MODE>=>)'
    '(?P<SSH_REMOTE_HOST>[^:@|]+)(:(?P<SSH_REMOTE_PORT>\d+))?'
)
# 远程HTTP(s)隧道
# SSHD_1=root@:22|:443|<=api.openai.com
# SSHD_1=root@:22|127.0.0.1:443|127.0.0.1:443<=api.openai.com
# ssh -R 127.0.0.1:443:127.0.0.1:443 -p 22 root@local.orb.local
expr2 = re.compile(
    r'((?P<SSH_USER>[^@:|]+)@)?(:(?P<SSH_PORT>\d+))'
    '\|'
    '(:(?P<SSH_LOCAL_PORT>\d+))?'
    '\|'
    '(?P<SSH_MODE><=)'
    '(?P<SSH_REMOTE_HOST>[^:@|]+)(:(?P<SSH_REMOTE_PORT>\d+))?'
)
KEYS_PATH = os.environ.get("KEYS_PATH", "/keys")
os.makedirs(KEYS_PATH, exist_ok=True)
for each in {"rsa", "ecdsa", "ed25519"}:
    key_file = f"{KEYS_PATH}/ssh_host_{each}_key"
    if not os.path.exists(key_file):
        os.system(f"ssh-keygen -t {each} -N '' -f {key_file}")

bind_config: List[str] = os.environ.get("BIND", "").split(";")
bind_config.remove("")
listen_config: List[str] = os.environ.get("LISTEN", "").split(";")
listen_config.remove("")
for key, value in os.environ.items():
    if not re.fullmatch(r'SSHD_\d+', key):
        continue
    if match := expr1.fullmatch(value) or expr2.fullmatch(value):
        group = dict(ChainMap({k: v for k, v in match.groupdict().items() if v is not None}, {
            "SSH_USER": "root",
            "SSH_PORT": 22,
            "SSH_LOCAL_HOST": "127.0.0.1",
            "SSH_LOCAL_PORT": 80,
            "SSH_MODE": "",
            "SSH_REMOTE_HOST": "127.0.0.1",
            "SSH_REMOTE_PORT": 80,
        }))
        print(
            f"check "
            f"{key}={group['SSH_USER']}@{group['SSH_PORT']}"
        )
        if group["SSH_MODE"] == "=>":
            group["SSH_MODE"] = "local"
        else:
            group["SSH_MODE"] = "remote"
        SSHD_KEY = os.environ.get(f"{key}_KEY") or os.environ.get(f"SSHD_KEY") or "/authorized_keys"
        CONFIG_FILE = f"config/sshd_config.{key}"
        with open(CONFIG_FILE, mode="w") as fout:
            fout.write(f"""\
# https://man.openbsd.org/sshd_config
Port {group["SSH_PORT"]}
HostKey {KEYS_PATH}/ssh_host_rsa_key
HostKey {KEYS_PATH}/ssh_host_ecdsa_key
HostKey {KEYS_PATH}/ssh_host_ed25519_key
PermitRootLogin yes
GatewayPorts {"no" if group["SSH_MODE"] == "local" else "yes"}
PasswordAuthentication no
AuthorizedKeysFile {SSHD_KEY}
AllowTcpForwarding {group["SSH_MODE"]}
AllowStreamLocalForwarding no
PermitOpen {group['SSH_LOCAL_HOST']}:{group['SSH_LOCAL_PORT']}
PermitListen 127.0.0.1:{group['SSH_LOCAL_PORT']}
# LogLevel DEBUG3
PrintLastLog yes
PrintMotd yes

Match User {group["SSH_USER"]}
    X11Forwarding no
    # AllowTcpForwarding yes
    PermitTTY no
    # lsof -nPp $(ps -o ppid= -p $$)|grep TCP|grep LISTEN
    # ForceCommand sh -c "netstat -atnp|grep LISTEN" && tail -f || echo Error: No valid listening configuration found"
""")
        cmd = (
            "/usr/sbin/sshd"
            f" -f '{CONFIG_FILE}'"
            f" -E '{os.environ.get('LOG_PATH', 'config')}/{key}.log'"
        )
        print(f"exec {cmd}")
        if os.system(f"{cmd}"):
            exit(1)
        if group["SSH_MODE"] == "local":
            bind_config.append(f"{group['SSH_LOCAL_PORT']}:{group['SSH_REMOTE_HOST']}:{group['SSH_REMOTE_PORT']}")
        else:
            listen_config.append(f"{group['SSH_REMOTE_HOST']}:{group['SSH_LOCAL_HOST']}:{group['SSH_LOCAL_PORT']}")
    else:
        print(f"error config [{key}={value}]")
        exit(1)
with open("tunnel.env", mode="w") as fout:
    if bind_config:
        fout.write(f"BIND={';'.join(bind_config)}\n")
    if listen_config:
        fout.write(f"LISTEN={';'.join(listen_config)}\n")
