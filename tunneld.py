import os
import re
from collections import ChainMap


def init_env():
    if os.path.exists(".env"):
        with open(".env") as fin:
            for each in fin.read().splitlines(keepends=False):
                k, _, v = each.strip().partition("=")
                os.environ[k] = v


init_env()
# SSHD_1=root@:10022|:1022->api.openai.com
expr = re.compile(
    r'((?P<SSH_USER>[^@:|]+)@)?(:(?P<SSH_PORT>\d+))'
    '\|'
    '(:(?P<SSH_LOCAL_PORT>\d+))'
    '->(?P<SSH_REMOTE_HOST>[^:@|]+)(:(?P<SSH_REMOTE_PORT>\d+))?'
)
KEYS_PATH = os.environ.get("KEYS_PATH", "/keys")
os.makedirs(KEYS_PATH, exist_ok=True)
for each in {"rsa", "ecdsa", "ed25519"}:
    key_file = f"{KEYS_PATH}/ssh_host_{each}_key"
    if not os.path.exists(key_file):
        os.system(f"ssh-keygen -t {each} -N '' -f {key_file}")

bind_config = os.environ.get("BIND", "").split(";")
bind_config.remove("")
for key, value in os.environ.items():
    if not re.fullmatch(r'SSHD_\d+', key):
        continue
    if match := expr.fullmatch(value):
        group = dict(ChainMap({k: v for k, v in match.groupdict().items() if v is not None}, {
            "SSH_USER": "root",
            "SSH_PORT": 22,
            "SSH_LOCAL_HOST": "127.0.0.1",
            "SSH_LOCAL_PORT": 80,
            "SSH_REMOTE_HOST": "127.0.0.1",
            "SSH_REMOTE_PORT": 80,
        }))
        print(
            f"check "
            f"{key}={group['SSH_USER']}@{group['SSH_PORT']}"
        )
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
GatewayPorts no
PasswordAuthentication no
AuthorizedKeysFile {SSHD_KEY}
AllowTcpForwarding local
AllowStreamLocalForwarding no
PermitOpen 127.0.0.1:{group['SSH_LOCAL_PORT']}
# PermitListen 127.0.0.1:80
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
            f" -E '/var/log/nginx/{key}.log'"
        )
        print(f"exec {cmd}")
        if os.system(f"{cmd}"):
            exit(1)
        bind_config.append(f"{group['SSH_LOCAL_PORT']}:{group['SSH_REMOTE_HOST']}:{group['SSH_REMOTE_PORT']}")
    else:
        print(f"error config [{key}={value}]")
        exit(1)
if bind_config:
    with open("tunnel.env", mode="w") as fout:
        fout.write(f"BIND={';'.join(bind_config)}")
