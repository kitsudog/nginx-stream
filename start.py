#!/usr/bin/env python3
import os
import re
from collections import ChainMap
from typing import Dict

from jinja2 import Environment, FileSystemLoader

jinja2_env = Environment(loader=FileSystemLoader('templates'))

if os.path.exists(".env"):
    with open(".env") as fin:
        for each in fin.read().splitlines(keepends=False):
            k, _, v = each.strip().partition("=")
            os.environ[k] = v


# noinspection PyDefaultArgument
def render(template, *, default: Dict = {}, **kwargs):
    data = {}
    for key, value in ChainMap(kwargs, default).items():
        if key.startswith("_"):
            continue
        data[key] = value
    return jinja2_env.get_template(template).render(data)


def format_content(template: str, data: dict):
    lines = template.splitlines()
    for k, v in data.items():
        tmp = []
        key = f"%({k})s"
        for line in lines:
            if line.find(key) >= 0:
                s, _, e = line.partition(key)
                if len(v.splitlines()) <= 1:
                    tmp.append(f"{s}{v}{e}")
                else:
                    white = " " * line.find(key)
                    tmp.append(f"{s}{v.splitlines()[0]}")
                    if len(v.splitlines()) > 2:
                        tmp.extend(list(map(
                            lambda x: f"{white}{x}",
                            v.splitlines()[1:-1]
                        )))
                    tmp.append(f"{white}{v.splitlines()[-1]}{e}")
            else:
                tmp.append(line)
        lines = tmp
    return "\n".join(filter(lambda x: not x.strip().startswith("##"), lines))


def upstream_config_gen(i: int, config: str, host: str, port: int, **kwargs):
    return f"""\
upstream LISTEN_{i} {{
  # for {config}
  server {host}:{port};
}}
"""


def listen_config_gen(host: str, ex: bool = False, **kwargs):
    kwargs2 = kwargs.copy()
    kwargs["host"] = host
    kwargs["ex"] = ex
    tls = kwargs.get("tls", "nginx")
    if ex:
        kwargs["listen_port"] = 81
        kwargs["tls"] = False
    else:
        kwargs["tls"] = tls

    core = render("basic.jinja", default={
        "listen_port": 80,
        "listen_host": "_",
        "server_dns": "",
        "tls_listen_port": 443,
        "tls": "nginx",
        "tls_crt_valid": os.path.exists(f"/etc/nginx/certs/{tls}.crt"),
        "tls_key_valid": os.path.exists(f"/etc/nginx/certs/{tls}.key"),
        "location_config_list": [ChainMap(kwargs, {
            "listen_host": "_",
            "listen_path": "/",
            "header": "FROM",
            "header_value": "nginx-stream",
            "proxy_host": "$proxy_host",
            "https": False,
            "url": "",
            "cross_domain": "",
        })],
        "ex": ex,
        "proxy_config": listen_config_gen(**ChainMap({
            "listen_port": 80,
            "host": "127.0.0.1",
            "port": 8000,
            "proxy_host": host,
            "https": False,
            "ex": False,
        }, kwargs2)) if ex else "",
    }, **kwargs)
    return re.sub("\n\n+", "\n", core)


def proxy_config_gen(host="", proto="https"):
    return f"""\
location /{host}/ {{
  proxy_set_header Host {host};
  proxy_ignore_client_abort on;
  proxy_ssl_server_name on;
  proxy_pass {proto}://{host}/;
}}
"""


def redirect_config_gen(host: str, url: str, listen_port: int, mode="normal"):
    if url.endswith("/"):
        url2, _, _ = url.rpartition("/")
    else:
        url2 = url
    if mode == "normal":
        return f"""\
server {{
  listen {listen_port};
  server_name {host};
  location / {{
    return 302 "{url2}$request_uri";
  }}
}}
"""
    elif mode == "no_uri":
        return f"""\
server {{
  listen {listen_port};
  server_name {host};
  location / {{
    return 302 "{url}";
  }}
}}
"""
    elif mode == "hash":
        return f"""\
server {{
  listen {listen_port};
  server_name {host};
  location / {{
    add_header Content-Type text/html;
    return 200 '<html><head><body><script type="text/javascript">window.location.href="{url2}" + location.pathname + location.search + location.hash;</script></body></html>';
  }}
}}
"""
    else:
        raise Exception(f"not support mode [{mode}]")


# noinspection HttpUrlsUsage
def gen_nginx_config(listen_config_list, stream_config_list, proxy_config_list, redirect_config_list, listen_port=80,
                     dns="8.8.8.8", config_file="/etc/nginx/nginx.conf", client_size="10m", external_host="$http_host",
                     external_proto="http"):
    kwargs = locals()
    upstream_config = map(lambda x: upstream_config_gen(**x), listen_config_list)
    proxy_config = []
    for each in proxy_config_list:
        proxy_config.append(proxy_config_gen(**each))
    tmp = {}
    for each in listen_config_list:
        listen_host = each['listen_host']
        _, _, listen_host2 = listen_host.partition(".")
        # noinspection PyPep8Naming
        CERT_DIR = "/etc/nginx/certs"
        if os.path.exists(f"{CERT_DIR}/{listen_host}.key") and os.path.exists(f"{CERT_DIR}/{listen_host}.crt"):
            each["tls"] = listen_host
        elif os.path.exists(f"{CERT_DIR}/{listen_host2}.key") and os.path.exists(f"{CERT_DIR}/{listen_host2}.crt"):
            each["tls"] = listen_host2
        if each.get("tls"):
            if each["tls"].upper() == "TRUE":
                each["tls"] = "nginx"
        else:
            each["tls"] = False

        if listen_host not in tmp:
            tmp[listen_host] = []
        tmp[listen_host].append(each)
    listen_config = []
    for k, each in sorted(tmp.items(), key=lambda kv: kv[0]):
        assert len(each) == 1
        listen_config.append(listen_config_gen(**each[0]))
    redirect_config = map(lambda x: redirect_config_gen(**x), redirect_config_list)

    content = render("nginx.jinja", default={
        "upstream": "\n".join(upstream_config),
        "proxy": "\n".join(proxy_config),
        "listen": "\n".join(listen_config),
        "redirect": "\n".join(redirect_config),
        "stream_config": jinja2_env.get_template("stream.jinja").render({
            "stream_config_list": stream_config_list,
        }),
    }, **kwargs)
    if os.environ.get("RECORD_PROXY") == "TRUE":
        content.replace('proxy_pass "${full_url}";', 'proxy_pass "http://localhost:81/${full_url}";')
    with open(config_file, mode="w") as fout:
        fout.write(content)


def env_params(func):
    import inspect

    ret = {}
    for name, param in inspect.signature(func).parameters.items():
        if value := os.environ.get(name):
            ret[name] = value
        elif value := os.environ.get(name.upper()):
            ret[name] = value
    return ret


def main():
    import re
    listen_config = []
    bind_config = []
    forward_config = []
    redirect_config = []
    proxy_config = []
    for k, each in list(filter(lambda kv: re.compile("REDIRECT_\d+").fullmatch(kv[0]), os.environ.items())) + list(
            map(lambda x: ("REDIRECT", x), os.environ.get("REDIRECT", "").split(";"))):
        if not each:
            continue
        regex = re.compile(
            '(?P<host>.+)(:(?P<listen_port>\d+))?=(?P<url>.+)'
        )
        config = next(regex.finditer(each)).groupdict()
        config['listen_port'] = int(config['listen_port'] or '80')
        params = filter(lambda kv: kv[0].startswith(f"{k}_"), os.environ.items())
        params = dict(
            map(lambda kv: (kv[0][len(k) + 1:].lower(), kv[1]), params)
        )
        config.update(params)
        redirect_config.append(config)

    for k, each in list(filter(lambda kv: re.compile("BIND_\d+").match(kv[0]), os.environ.items())) + list(
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
        r'(?P<listen_path>/[^:]+)?'
        r':(?P<host>[^:/]+)(:(?P<port>\d+))?(?P<url>/[^@]+)?'
        r'(@(?P<proxy_host>.+))?'
    )
    i = 0

    def get_listen_config(line, forward=False, **kwargs):
        if kwargs:
            print(f"get_listen_config: {line} {kwargs}")
        else:
            print(f"get_listen_config: {line}")
        config = next(regex_listen.finditer(line)).groupdict()
        config['i'] = int(
            k.split("_")[-1]) if k.startswith("LISTEN_") else 100 + i
        config['port'] = int(config['port'] or 80)
        config['listen_path'] = config['listen_path'] or '/'
        config['https'] = bool(config['https'])
        config['url'] = config['url'] or config['listen_path']
        config['proxy_host'] = config['proxy_host'] or (
            '$http_host' if forward else '$proxy_host')
        config.update(
            dict(map(lambda kv: (kv[0].lower(), kv[1]), kwargs.items())))
        print(f"LISTEN[{line}]=>[{config}]")
        config['config'] = f"{k}={line}"
        return config

    for k, each in list(filter(lambda kv: re.compile("LISTEN_\d+").fullmatch(kv[0]), os.environ.items())) + list(
            map(lambda x: ("LISTEN", x), os.environ.get("LISTEN", "").split(";"))):
        if not each:
            continue
        print("listen", k, each)
        i += 1
        params = filter(lambda kv: kv[0].startswith(f"{k}_"), os.environ.items())
        params = dict(
            map(lambda kv: (kv[0][len(k) + 1:].lower(), kv[1]), params)
        )
        params["ex"] = params.get("ex", "false").lower() == "true"
        listen_config.append(get_listen_config(each, **params))

    for k, each in list(filter(lambda kv: re.compile("FORWARD_\d+").match(kv[0]), os.environ.items())) + list(
            map(lambda x: ("FORWARD", x), os.environ.get("FORWARD", "").split(";"))):
        if not each:
            continue
        print("forward:", each)
        i += 1
        forward_config.append(get_listen_config(each, forward=True))

    # noinspection PyTypeChecker
    for k, each in list(filter(
            lambda kv: re.compile("PROXY_\d+").match(kv[0]),
            os.environ.items()
    )) + list(map(
        lambda x: ("PROXY", x),
        os.environ.get("PROXY", "").split(";")
    )):
        if not each:
            continue
        i += 1
        proxy_config.append({
            "host": each.replace("http://", "").replace("https://", "").partition("/")[0],
            "proto": "https" if each.startswith("https://") else "http",
        })

    gen_nginx_config(
        listen_config_list=listen_config + forward_config,
        redirect_config_list=redirect_config,
        stream_config_list=bind_config,
        proxy_config_list=proxy_config,
        **env_params(gen_nginx_config)
    )


if __name__ == '__main__':
    print("""
Usage: 
  LISTEN=www.abc.com:www.baidu.com:80 FORWARD=www.baidu.com BIND=80:192.168.1.1:80 PROXY=openai.com ./start.py
  
""")
    main()
    print("config ok")
