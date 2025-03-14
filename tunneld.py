import os
import re
from collections import ChainMap

# SSHD_1=root@192.168.100.195:22|127.0.0.1:80<-127.0.0.1:38080
# SSHD_2=192.168.100.195|80<-38081
# SSHD_3=192.168.100.195|38080->8080
expr = re.compile(
    r'((?P<SSH_USER>[^@:]+)@)?(?P<SSH_PORT>\d+)'
    r'(->((?P<SSH_LOCAL_HOST>[^:]+):)?(?P<SSH_LOCAL_PORT>\d+))?'
)
os.makedirs("keys", exist_ok=True)
for each in {"rsa", "ecdsa", "ed25519"}:
    key_file = f"keys/ssh_host_{each}_key"
    if not os.path.exists(key_file):
        os.system(f"ssh-keygen -t {each} -N '' -f {key_file}")

for key, value in os.environ.items():
    if not re.fullmatch(r'SSHD_\d+', key):
        continue
    if match := expr.fullmatch(value):
        group = dict(ChainMap({k: v for k, v in match.groupdict().items() if v is not None}, {
            "SSH_USER": "root",
            "SSH_PORT": 22,
            "SSH_LOCAL_HOST": "127.0.0.1",
            "SSH_LOCAL_PORT": 80,
        }))
        print(f"check "
              f"{key}={group['SSH_USER']}@{group['SSH_PORT']}->{group['SSH_LOCAL_HOST']}:{group['SSH_LOCAL_PORT']}"
              )
        SSHD_KEY = os.environ.get(f"{key}_KEY") or os.environ.get(f"SSHD_KEY") or "/authorized_keys"
        with open(f"config/sshd_config.{key}", mode="w") as fout:
            fout.write(f"""\
Port {group["SSH_PORT"]}
HostKey keys/ssh_host_rsa_key
HostKey keys/ssh_host_ecdsa_key
HostKey keys/ssh_host_ed25519_key
PermitRootLogin yes
PasswordAuthentication no
AuthorizedKeysFile {SSHD_KEY}

Match User {group["SSH_USER"]}
    X11Forwarding no
    # AllowTcpForwarding yes
    PermitTTY no
    ForceCommand sh -c "netstat -antp|grep LISTEN|grep sshd -v|grep {group["SSH_LOCAL_HOST"]}:{group["SSH_LOCAL_PORT"]} && tail -f || echo Error: No valid listening configuration found"

""")
        cmd = (
            "/usr/sbin/sshd "
            "-e "
            f"-f config/sshd_config.{key} "
        )
        print(f"exec {cmd}")
        os.system(cmd)
