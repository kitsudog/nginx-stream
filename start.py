#!/usr/bin/env python3
import os


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


def listen_location_config_gen(host: str, port: int, listen_host="_",
                               listen_path="/", header="FROM", header_value="nginx-stream",
                               proxy_host="$proxy_host", https=False, url: str = "",
                               cross_domain: str = "", **kwargs):
    return f"""\
location {listen_path} {{
  add_header {header} {header_value};
  proxy_set_header X-FROM {listen_host};
  proxy_set_header Host {proxy_host};
  proxy_pass {"https" if https else "http"}://{host}:{port}{url};
  proxy_redirect default;
  proxy_ssl_server_name on;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection $proxy_connection;
""" + (f"""
  # active cross_domain start
  add_header 'Access-Control-Allow-Origin'      '{cross_domain}';
  add_header 'Access-Control-Allow-Methods'     'GET, POST, OPTIONS';
  add_header 'Access-Control-Allow-Headers'     'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
  add_header 'Access-Control-Expose-Headers'    'Content-Length,Content-Range';
  # active cross_domain over
""" if cross_domain else "") + """
}
"""


def listen_config_gen0(listen_port=80, listen_host="_", server_dns="", **kwargs):
    return f"""\
server {{
  listen {listen_port};
  server_name {listen_host};
  ssl_verify_client off;
  {("resolver %s valid=60s;" % server_dns) if server_dns else ""}
"""


def listen_config_gen1(i: int, config: str, host: str, port: int, listen_port=80, listen_host="_", server_dns="",
                       listen_path="/", header="FROM", header_value="nginx-stream", proxy_host="$proxy_host",
                       https=False, url: str = "", ex: bool = False, **kwargs):
    kwargs = locals()
    return f"""\
}}
"""


def listen_config_gen(host: str, ex: bool = False, **kwargs):
    kwargs["host"] = host
    kwargs["ex"] = ex
    if ex:
        kwargs["listen_port"] = 81
    core = format_content("""\
%(s)s
  %(c)s
%(e)s
""", {
        "s": listen_config_gen0(**kwargs),
        "c": listen_location_config_gen(**kwargs),
        "e": listen_config_gen1(**kwargs),
    })
    if not ex:
        return core
    else:
        kwargs["listen_port"] = 80
        kwargs["host"] = "127.0.0.1"
        kwargs["port"] = 8000
        kwargs["proxy_host"] = host
        kwargs["https"] = False
        kwargs["ex"] = False
        return f"""\
{listen_config_gen(**kwargs)}\
# For Ex
{core}\
"""


def proxy_config_gen(host="", proto="https"):
    return f"""\
location /{host}/ {{
  proxy_set_header Host {host};
  proxy_ignore_client_abort on;
  proxy_ssl_server_name on;
  proxy_pass {proto}://{host}/;
}}
"""


def redirect_config_gen(host: str, url: str, listen_port: int):
    return f"""\
server {{
  listen {listen_port};
  server_name {host};
  location / {{
    return 302 "{url}";
  }}
}}
"""


def stream_config_gen(host: str, port: str, listen_port: int, connect_timeout=3, timeout=10, udp=False):
    return f"""\
server {{
  listen {listen_port}{" udp" if udp else ""};
  proxy_connect_timeout {connect_timeout}s;
  proxy_timeout {timeout}s;
  proxy_pass {host}:{port};
}}
"""


# noinspection HttpUrlsUsage
def gen_nginx_config(listen_config_list, stream_config_list, proxy_config_list, redirect_config_list, listen_port=80,
                     dns="8.8.8.8", config_file="/etc/nginx/nginx.conf", client_size="10m", external_host="$http_host",
                     external_proto="http"):
    upsteam_config = map(lambda x: upstream_config_gen(**x), listen_config_list)
    proxy_config = []
    for each in proxy_config_list:
        proxy_config.append(proxy_config_gen(**each))
    tmp = {}
    for each in listen_config_list:
        listen_host = each['listen_host']
        if listen_host not in tmp:
            tmp[listen_host] = []
        tmp[listen_host].append(each)
    listen_config = []
    for k, each in tmp.items():
        if len(each) == 1:
            listen_config.append(listen_config_gen(**each[0]))
        else:
            config = listen_config_gen0(**each[0])
            for x in each:
                config += listen_location_config_gen(**x)
            config += listen_config_gen1(**each[0])
            listen_config.append(config)
    stream_config = map(lambda x: stream_config_gen(**x), stream_config_list)
    redirect_config = map(lambda x: redirect_config_gen(**x), redirect_config_list)

    content = format_content(f"""\
user  nginx;
worker_processes  auto;

error_log  /var/log/nginx/error.log notice;
pid         /var/run/nginx.pid;

events {{
    worker_connections  10240;
}}
http {{
  resolver {dns} valid=60s ipv6=off;
  include       /etc/nginx/mime.types;
  default_type  application/octet-stream;
  log_format  main  '$remote_addr $http_host $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for" ' [Proxy-pass=$upstream_addr @ $dest_host] $full_url;

  access_log  /var/log/nginx/access.log  main;
  sendfile        on;
  #tcp_nopush     on;
  charset 'utf-8';
  keepalive_timeout  65;
  # If we receive X-Forwarded-Proto, pass it through; otherwise, pass along the
  # scheme used to connect to this server
  map $http_x_forwarded_proto $proxy_x_forwarded_proto {{
    default $http_x_forwarded_proto;
    ''      $scheme;
  }}
  # If we receive X-Forwarded-Port, pass it through; otherwise, pass along the
  # server port the client connected to
  map $http_x_forwarded_port $proxy_x_forwarded_port {{
    default $http_x_forwarded_port;
    ''      $server_port;
  }}
  # If we receive Upgrade, set Connection to "upgrade"; otherwise, delete any
  # Connection header that may have been passed to this server
  map $http_upgrade $proxy_connection {{
    default upgrade;
    '' close;
  }}
  # Set appropriate X-Forwarded-Ssl header based on $proxy_x_forwarded_proto
  map $proxy_x_forwarded_proto $proxy_x_forwarded_ssl {{
    default off;
    https on;
  }}
  gzip_types text/plain text/css application/javascript application/json application/x-javascript text/xml application/xml application/xml+rss text/javascript;
  # HTTP 1.1 support
  proxy_http_version 1.1;
  proxy_buffering off;
  proxy_set_header Host $http_host;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection $proxy_connection;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $proxy_x_forwarded_proto;
  proxy_set_header X-Forwarded-Ssl $proxy_x_forwarded_ssl;
  proxy_set_header X-Forwarded-Port $proxy_x_forwarded_port;
  proxy_set_header Proxy "";

  client_max_body_size      {client_size};
  client_header_timeout     1m;
  client_body_timeout       1m;
  proxy_connect_timeout     60s;
  proxy_read_timeout        1m;
  proxy_send_timeout        1m;

  server {{
    server_name _;
    location / {{
      proxy_pass http://127.0.0.1:81;
      proxy_redirect http://internal {external_proto}://{external_host};
    }}
  }}

  server {{
    server_name _;
    server_tokens off;
    listen 81;
    
    set $dest_host $http_host;
    set $dest_proto "https";
    set $full_url "#";
    
    if ($cookie_dest ~ "^(https?)://([^/]*)/$") {{
        set $dest_proto $1;
        set $dest_host $2;
        set $full_url $dest_proto://$dest_host$request_uri;
    }}
    
    if ($cookie_dest ~ "^/([^/]+)/(https?)://([^/]*)/$") {{
        set $dest_ip $1;
        set $dest_proto $2;
        set $dest_host $3;
        set $full_url $dest_proto://$dest_ip$request_uri;
    }}
    
    if ($remote_user ~ "^(https?)-([^/]*)$") {{
        set $dest_proto $1;
        set $dest_host $2;
        set $full_url "${{dest_proto}}://${{dest_host}}${{request_uri}}";
    }}
    
    if ($request_uri ~ "^/([^/]+)/(https?)://([^/]*)/(.*)$") {{
        set $dest_ip $1;
        set $dest_proto $2;
        set $dest_host $3;
        set $url $4;
        set $full_url "${{dest_proto}}://${{dest_ip}}/${{url}}";
    }}
    
    if ($request_uri ~ "^/(https?)://([^/]*)/(.*)$") {{
        set $dest_proto $1;
        set $dest_host $2;
        set $url $3;
        set $dest_proto "https";
        set $full_url "${{dest_proto}}://${{dest_host}}/${{url}}";
    }}
    
    location / {{
    
        if ($request_uri ~ "^/https?://([^/]*)/$") {{
            add_header Set-Cookie "dest_host=$dest_host; path=/;";
            add_header Set-Cookie "dest_ip=$dest_ip; path=/;";
            add_header Set-Cookie "dest=${{dest_proto}}://${{dest_host}}/; path=/;";
            return 302 " /";
        }}
        
        if ($request_uri ~ "^/([^/]+)/https?://([^/]*)/$") {{
            add_header Set-Cookie "dest_host=$dest_host; path=/;";
            add_header Set-Cookie "dest_ip=$dest_ip; path=/;";
            add_header Set-Cookie "dest=/${{dest_ip}}/${{dest_proto}}://${{dest_host}}/; path=/;";
            return 302 " /";
        }}
        
        proxy_ssl_server_name on;
        proxy_pass "${{full_url}}";
        add_header proxy-by nginx-stream;
        add_header proxy-host $dest_host;
        add_header proxy-upstream $upstream_addr;

        add_header 'Access-Control-Allow-Origin' '${{dest_host}}';
        add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
        add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
        if ($request_method = 'OPTIONS') {{
            return 204;
        }}
        
        proxy_set_header Host "$dest_host";
        proxy_redirect $dest_proto://$dest_host http://internal/$dest_proto://$dest_host;
    }}
    
    # PROXY START
    %(proxy)s
    # PROXY END
  }}
  # UPSTREAM START
  %(upstream)s
  # UPSTREAM END
  # LISTEN START
  %(listen)s
  # LISTEN END
  # REDIRECT START
  %(redirect)s
  # REDIRECT END
}}

stream {{
  log_format proxy '$remote_addr [$time_local] '
                 '$protocol $status $bytes_sent $bytes_received '
                 '$session_time -> $upstream_addr '
                 '$upstream_bytes_sent $upstream_bytes_received $upstream_connect_time';
  access_log /dev/stdout proxy buffer=32k;
  open_log_file_cache off;
  # STREAM START
  %(stream)s
  # STREAM END
}}
""", {
        "upstream": "\n".join(upsteam_config),
        "proxy": "\n".join(proxy_config),
        "listen": "\n".join(listen_config),
        "stream": "\n".join(stream_config),
        "redirect": "\n".join(redirect_config),
    })
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
    for k, each in list(filter(lambda kv: re.compile("REDIRECT_\d+").match(kv[0]), os.environ.items())) + list(
            map(lambda x: ("REDIRECT", x), os.environ.get("REDIRECT", "").split(";"))):
        if not each:
            continue
        regex = re.compile(
            '(?P<host>.+)(:(?P<listen_port>\d+))?=(?P<url>.+)'
        )
        config = next(regex.finditer(each)).groupdict()
        config['listen_port'] = int(config['listen_port'] or '80')
        redirect_config.append(config)

    for k, each in list(filter(lambda kv: re.compile("BIND_\d+").match(kv[0]), os.environ.items())) + list(
            map(lambda x: ("BIND", x), os.environ.get("BIND", "").split(";"))):
        if not each:
            continue
        regex = re.compile(
            '((?P<udp>udp)@)?((?P<listen_port>\d+):)?(?P<host>[^:]+)(:(?P<port>\d+))?'
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
        '(?P<https>https@)?'
        '(?P<listen_host>[^:/]+)'
        '(?P<listen_path>/[^:]+)?'
        ':(?P<host>[^:/]+)(:(?P<port>\d+))?(?P<url>/[^@]+)?'
        '(@(?P<proxy_host>.+))?'
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
