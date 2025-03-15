#!/usr/bin/env python3
import os
from collections import ChainMap, defaultdict
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader

jinja2_env = Environment(loader=FileSystemLoader('templates'))
CONFIG_DIR = os.environ.get("CONFIG_DIR", "/etc/nginx/conf.d")


def init_env():
    for file in os.listdir("."):
        if file.endswith(".env"):
            with open(file) as fin:
                for each in fin.read().splitlines(keepends=False):
                    k, _, v = each.strip().partition("=")
                    os.environ[k] = v


init_env()


# noinspection PyDefaultArgument
def merge_config(
        src: List[Dict], *, group_by_key: List[str], group_key: str, ignore_key: List[str] = [],
) -> List[Dict]:
    tmp = defaultdict(lambda: [])
    for each in src:
        value = ":".join(map(lambda x: f"{x}={each[x]}", group_by_key))
        tmp[value].append(each)
    new = []
    for k, v in list(tmp.items()):
        config = v[0].copy()
        new_value = []
        for each in v:
            for _k, _v in each.items():
                if _k == group_key or _k in ignore_key:
                    continue
                assert each[_k] == config[_k], f"can't merge {_k}"
            if group_key in each:
                new_value.extend(each[group_key])
            else:
                new_value.append(each)
        config[group_key] = new_value
        new.append(config)
    return new


# noinspection PyDefaultArgument
def render(template, *, default: Dict = {}, **kwargs):
    data = {}
    for key, value in ChainMap(kwargs, default).items():
        if key.startswith("_"):
            continue
        data[key] = value
    return jinja2_env.get_template(template).render(data)


# noinspection HttpUrlsUsage
def gen_nginx_config(
        listen_config_list, stream_config_list, proxy_config_list, redirect_config_list,
        tunnel_config_list, listen_port=80,
        dns="8.8.8.8", config_file="/etc/nginx/nginx.conf", client_size="10m", external_host="$http_host",
        external_proto="http", proxy_listen_port=82, disable_proxy="FALSE", default_forward=False, default_jwt_ex=False,
        default_geo_white="", default_geo_black="", default_ban_header="", default_geo_redirect="", default_geo_html="",
        tunnel_all_https=False,
):
    disable_proxy = str(disable_proxy).lower() in {"true", "1"}
    kwargs = locals().copy()
    tmp = {}
    for i, each in enumerate(listen_config_list):
        listen_host = each['listen_host']
        _, _, listen_host2 = listen_host.partition(".")
        # noinspection PyPep8Naming
        CERT_DIR = os.environ.get("CERT_DIR", "/etc/nginx/certs")
        prefix = f"{CERT_DIR}/{listen_host}"
        prefix2 = f"{CERT_DIR}/{listen_host2}"
        if os.path.exists(f"{prefix}.key") and os.path.exists(f"{prefix}.crt"):
            each["tls"] = listen_host
        elif os.path.exists(f"{prefix2}.key") and os.path.exists(f"{prefix2}.crt"):
            each["tls"] = listen_host2
        if os.path.exists(f"{prefix}-client.key") and os.path.exists(f"{prefix}-client.crt"):
            each["client_tls"] = listen_host
        elif os.path.exists(f"{prefix2}-client.key") and os.path.exists(f"{prefix2}-client.crt"):
            each["client_tls"] = listen_host2
        if each.get("tls"):
            if each["tls"].upper() == "TRUE":
                each["tls"] = "nginx"
        else:
            each["tls"] = False
        if each.get("client_tls"):
            if each["client_tls"].upper() == "TRUE":
                each["client_tls"] = "nginx"
        else:
            each["client_tls"] = False
        location_config = f"{CONFIG_DIR}/{each['listen_host']}_location"
        each.update(ChainMap(each, {
            "i": i,
            "listen_port": 81 if each.get("ex") else 80,
            "listen_host": "_",
            "config_location": os.path.exists(location_config) and location_config,
            "server_dns": "",
            "tls_listen_port": 443,
            "tls": "nginx",
            "tls_crt_valid": os.path.exists(f"{CERT_DIR}/{each['tls']}.crt"),
            "tls_key_valid": os.path.exists(f"{CERT_DIR}/{each['tls']}.key"),
            "client_tls_crt_valid": os.path.exists(f"{CERT_DIR}/{each['client_tls']}-client.crt"),
            "client_tls_key_valid": os.path.exists(f"{CERT_DIR}/{each['client_tls']}-client.key"),
            "location_config_list": [
                ChainMap(each, {
                    "listen_host": "_",
                    "listen_path": "/",
                    "proxy_host": "$proxy_host",
                    "https": False,
                    "url": "",
                    "cross_domain": "",
                })
            ],
        }))
        if listen_host not in tmp:
            tmp[listen_host] = []
        tmp[listen_host].append(dict(each))
    new_config_list = merge_config(
        listen_config_list,  #
        group_by_key=["listen_host"],  #
        group_key="location_config_list",  #
        ignore_key=["listen_path", "url", "i", "config", "host", "port"],  #
    )
    listen_config_list.clear()
    listen_config_list.extend(new_config_list)
    new_config_list = merge_config(
        redirect_config_list,  #
        group_by_key=["host", "listen_port"],  #
        group_key="location_list",  #
        ignore_key=["location", "url", "url2", "mode", "keep_prefix"],  #
    )
    redirect_config_list.clear()
    redirect_config_list.extend(new_config_list)
    content = render("nginx.jinja", **kwargs)
    if os.environ.get("RECORD_PROXY") == "TRUE":
        content.replace('proxy_pass "${full_url}";', 'proxy_pass "http://localhost:81/${full_url}";')
    with open(config_file, mode="w") as fout:
        fout.write(content)


def env_params(func):
    import inspect

    ret = {}
    for name, param in inspect.signature(func).parameters.items():
        if value := os.environ.get(name):
            ret[name] = value == "TRUE" or value
        elif value := os.environ.get(name.upper()):
            ret[name] = value == "TRUE" or value
    return ret


def main():
    import re
    listen_config = []
    bind_config = []
    forward_config = []
    redirect_config = []
    tunnel_config = []
    proxy_config = []
    for i, k_each in enumerate(
            list(filter(lambda kv: re.compile(r"TUNNEL_\d+").fullmatch(kv[0]), os.environ.items())) + list(
                map(lambda x: ("TUNNEL", x), os.environ.get("TUNNEL", "").split(";"))),
            start=1
    ):
        k, each = k_each
        if not each:
            continue
        regex = re.compile(
            r'(?P<host>.+)(:(?P<listen_port>\d+))?'
        )
        config = next(regex.finditer(each)).groupdict()
        config["id"] = i
        config['listen_port'] = int(config['listen_port'] or '443')
        params = filter(lambda kv: kv[0].startswith(f"{k}_"), os.environ.items())
        params = dict(
            map(lambda kv: (kv[0][len(k) + 1:].lower(), kv[1]), params)
        )
        config.update(params)
        tunnel_config.append(config)

    for k, each in list(filter(lambda kv: re.compile(r"REDIRECT_\d+").fullmatch(kv[0]), os.environ.items())) + list(
            map(lambda x: ("REDIRECT", x), os.environ.get("REDIRECT", "").split(";"))):
        if not each:
            continue
        regex = re.compile(
            r'(?P<host>[^:/]+)(:(?P<listen_port>\d+))?(?P<location>/[^=]*)?=(?P<url>.+)'
        )
        config = next(regex.finditer(each)).groupdict()
        config['listen_port'] = int(config['listen_port'] or '80')
        if config["url"].endswith("/"):
            config["url2"], _, _ = config["url"].rpartition("/")
        else:
            config["url2"] = config["url"]
        params = filter(lambda kv: kv[0].startswith(f"{k}_"), os.environ.items())
        params = dict(
            map(lambda kv: (kv[0][len(k) + 1:].lower(), kv[1]), params)
        )
        config.update(params)
        config['location'] = config.get('location') or '/'
        config['mode'] = config.get('mode', 'normal')
        config['keep_prefix'] = (config.get('keep_prefix') or 'false').lower() in ["true"]
        redirect_config.append(config)

    for k, each in list(filter(lambda kv: re.compile(r"BIND_\d+").match(kv[0]), os.environ.items())) + list(
            map(lambda x: ("BIND", x), os.environ.get("BIND", "").split(";"))):
        if not each:
            continue
        regex = re.compile(
            r'((?P<udp>udp)@)?((?P<listen_port>\d+):)?(?P<host>[^:]+)(:(?P<port>\d+))?'
        )
        print("check", each)
        config = next(regex.finditer(each)).groupdict()
        config['port'] = int(config['port'] or 80)
        config['listen_port'] = int(config['listen_port'] or config['port'])
        config['connect_timeout'] = os.environ.get("CONNECT_TIMEOUT", 3)
        config['timeout'] = os.environ.get("TIMEOUT", 10)
        print(f"BIND[{each}]=>[{config}]")
        bind_config.append(config)
    regex_listen = re.compile(
        r'(?P<https>https@)?'
        r'(?P<listen_host>[^:/]+)'
        r'(?P<listen_path>/[^:]*)?'
        r':(?P<host>[^:@/]+)(:(?P<port>\d+))?(?P<url>/[^@]*)?'
        r'(@(?P<proxy_host>.+))?'
    )

    def get_listen_config(line, forward=False, **kwargs):
        if kwargs:
            print(f"get_listen_config: {line} {kwargs}")
        else:
            print(f"get_listen_config: {line}")
        # noinspection PyShadowingNames
        config = next(regex_listen.finditer(line)).groupdict()
        config['i'] = int(k.split("_")[-1]) if k.startswith("LISTEN_") else 100 + i
        config['https'] = bool(config['https'])
        config['port'] = int(config['port'] or (443 if config['https'] else 80))
        config['listen_path'] = config['listen_path'] or '/'
        config['url'] = config['url'] or config['listen_path']
        config['proxy_host'] = config['proxy_host'] or ('$http_host' if forward else '$proxy_host')
        config.update(dict(map(lambda kv: (kv[0].lower(), kv[1]), kwargs.items())))
        print(f"LISTEN[{line}]=>[{config}]")
        config['config'] = f"{k}={line}"
        return config

    for i, k_each in enumerate(list(filter(
            lambda kv: re.compile(r"LISTEN_\d+").fullmatch(kv[0]),
            os.environ.items()
    )) + list(map(
        lambda x: ("LISTEN", x),
        os.environ.get("LISTEN", "").split(";")
    ))):
        k, each = k_each
        if not each:
            continue
        print("listen", k, each)
        _params = list(filter(lambda kv: kv[0].startswith(f"{k}_"), os.environ.items()))
        params = dict(
            map(lambda kv: (kv[0][len(k) + 1:].lower(), kv[1]), _params)
        )
        params["ex"] = str(params.get("ex", "false")).lower() == "true"
        listen_config.append(get_listen_config(each, **params))

    for k, each in list(filter(lambda kv: re.compile(r"FORWARD_\d+").fullmatch(kv[0]), os.environ.items())) + list(
            map(lambda x: ("FORWARD", x), os.environ.get("FORWARD", "").split(";"))):
        if not each:
            continue
        print("forward:", each)
        forward_config.append(get_listen_config(each, forward=True))

    # noinspection PyTypeChecker
    for k, each in list(filter(
            lambda kv: re.compile(r"PROXY_\d+").match(kv[0]),
            os.environ.items()
    )) + list(map(
        lambda x: ("PROXY", x),
        os.environ.get("PROXY", "").split(";")
    )):
        if not each:
            continue
        proxy_config.append({
            "host": each.replace("http://", "").replace("https://", "").partition("/")[0],
            "proto": "https" if each.startswith("https://") else "http",
        })

    gen_nginx_config(
        listen_config_list=listen_config + forward_config,
        redirect_config_list=redirect_config,
        stream_config_list=bind_config,
        proxy_config_list=proxy_config,
        tunnel_config_list=tunnel_config,
        **env_params(gen_nginx_config)
    )


if __name__ == '__main__':
    print("""
Usage: 
  LISTEN=www.abc.com:www.baidu.com:80 FORWARD=www.baidu.com BIND=80:192.168.1.1:80 PROXY=openai.com ./start.py
  
""")
    main()
    print("config ok")
