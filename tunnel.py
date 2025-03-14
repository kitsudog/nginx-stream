import os
import re
from collections import ChainMap

# SSH_1=root@192.168.100.195:22|127.0.0.1:80<-127.0.0.1:38080
# SSH_2=192.168.100.195|80<-38081
# SSH_3=192.168.100.195|38080->8080
expr = re.compile(
    r'((?P<SSH_USER>[^@:]+)@)?(?P<SSH_HOST>[^:@]+)(:(?P<SSH_PORT>\d+))?'
    r'\|((?P<SSH_REMOTE_HOST>[^:]+):)?(?P<SSH_REMOTE_PORT>\d+)'
    r'(?P<SSH_MODE>(<-|->))'
    r'((?P<SSH_LOCAL_HOST>[^:]+):)?(?P<SSH_LOCAL_PORT>\d+)'
)
for key, value in os.environ.items():
    if not re.fullmatch(r'SSH_\d+', key):
        continue
    if match := expr.fullmatch(value):
        print(f"check {key}={value}")
        group = dict(ChainMap({k: v for k, v in match.groupdict().items() if v is not None}, {
            "SSH_USER": "root",
            "SSH_HOST": None,
            "SSH_PORT": 22,
            "SSH_REMOTE_HOST": "127.0.0.1",
            "SSH_REMOTE_PORT": None,
            "SSH_LOCAL_HOST": "127.0.0.1",
            "SSH_LOCAL_PORT": None,
            "SSH_MODE": None,
        }))
        if group["SSH_MODE"] == "<-":
            group["SSH_MODE"] = "L"
        else:
            group["SSH_MODE"] = "R"
        SSH_KEY = os.environ.get(f"{key}_KEY") or os.environ.get(f"SSH_KEY") or "/id_rsa"
        if not os.path.exists(SSH_KEY):
            print(f"error {key}={value} not found key [{SSH_KEY}]")
            exit(2)
        SSH_MODE = group["SSH_MODE"]
        SSH_USER, SSH_HOST, SSH_PORT = group["SSH_USER"], group["SSH_HOST"], group["SSH_PORT"]
        SSH_REMOTE_HOST, SSH_REMOTE_PORT = group["SSH_REMOTE_HOST"], group["SSH_REMOTE_PORT"]
        SSH_LOCAL_HOST, SSH_LOCAL_PORT = group["SSH_LOCAL_HOST"], group["SSH_LOCAL_PORT"]
        if SSH_MODE == "L":
            SSH_BIND_IP = SSH_LOCAL_HOST
            SSH_TUNNEL_PORT = SSH_LOCAL_PORT
            SSH_TARGET_HOST = SSH_REMOTE_HOST
            SSH_TARGET_PORT = SSH_REMOTE_PORT
        else:
            SSH_BIND_IP = SSH_REMOTE_HOST
            SSH_TUNNEL_PORT = SSH_REMOTE_PORT
            SSH_TARGET_HOST = SSH_LOCAL_HOST
            SSH_TARGET_PORT = SSH_LOCAL_PORT
        cmd = (
            "autossh -M 0 -f -N "
            "-o StrictHostKeyChecking=no "
            "-o CheckHostIP=no "
            "-o ServerAliveInterval=10 "
            "-o ServerAliveCountMax=3 "
            "-o ExitOnForwardFailure=yes "
            f"-t -t {SSH_USER}@{SSH_HOST} -p {SSH_PORT} -i {SSH_KEY} -{SSH_MODE} {SSH_BIND_IP}:{SSH_TUNNEL_PORT}:{SSH_TARGET_HOST}:{SSH_TARGET_PORT}"
        )
        print(cmd)
        os.system(cmd)
        # subprocess.Popen(cmd.split(" "), preexec_fn=os.setsid)
    else:
        print(f"error config {key}={value}")
        exit(1)

expr = re.compile(
    r'((?P<SSH_USER>[^@:]+)@)?(?P<SSH_PORT>\d+)'
    r'->'
    r'((?P<SSH_LOCAL_HOST>[^:]+):)?(?P<SSH_LOCAL_PORT>\d+)'
)
for key, value in os.environ.items():
    if not re.fullmatch(r'SSHD_\d+', key):
        continue
    with open(f"/etc/sshd_config.{key}") as fout:
        pass
