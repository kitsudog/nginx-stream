#!/usr/bin/env python3
import sys
import os

def upstream_config_gen(i:int,config:str,host:str,port:int,listen_port=80,listen_host="_",server_dns="",listen_path="/",header="FROM",header_value="nginx-stream",proxy_host="$proxy_host",https=False,url:str=""):
    return f"""\
  upstream LISTEN_{i} {{
    # for {config}
    server {host}:{port};
  }}
"""

def listen_location_config_gen(i:int,config:str,host:str,port:int,listen_port=80,listen_host="_",server_dns="",listen_path="/",header="FROM",header_value="nginx-stream",proxy_host="$proxy_host",https=False,url:str=""):
    return f"""\
    location {listen_path} {{
      add_header {header} {header_value};
      proxy_set_header Host {proxy_host};
      proxy_set_header X-FROM {listen_host};
      proxy_pass {"https" if https else "http"}://{host}:{port}{url};
      proxy_redirect default;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection $proxy_connection;
    }}
"""

def listen_config_gen0(i:int,config:str,host:str,port:int,listen_port=80,listen_host="_",server_dns="",listen_path="/",header="FROM",header_value="nginx-stream",proxy_host="$proxy_host",https=False,url:str=""):
    kwargs=locals()
    return f"""\
  server {{
    listen {listen_port};
    server_name {listen_host};
    ssl_verify_client off;
    {("resolver %s;" % server_dns) if server_dns else ""}
"""

def listen_config_gen1(i:int,config:str,host:str,port:int,listen_port=80,listen_host="_",server_dns="",listen_path="/",header="FROM",header_value="nginx-stream",proxy_host="$proxy_host",https=False,url:str=""):
    kwargs=locals()
    return f"""\
  }}
"""

def listen_config_gen(i:int,config:str,host:str,port:int,listen_port=80,listen_host="_",server_dns="",listen_path="/",header="FROM",header_value="nginx-stream",proxy_host="$proxy_host",https=False,url:str=""):
    kwargs=locals()
    return listen_config_gen0(**kwargs)+listen_location_config_gen(**kwargs)+listen_config_gen1(**kwargs)

def stream_config_gen(host:str,port:str,listen_port:int, connect_timeout=3,timeout=10,udp=False):
    return f"""\
  server {{
    listen {listen_port}{" udp" if udp else ""};
    proxy_connect_timeout {connect_timeout}s;
    proxy_timeout {timeout}s;
    proxy_pass {host}:{port};
  }}
"""

def gen_nginx_config(listen_config_list,stream_config_list,listen_port=80,dns="8.8.8.8",config_file="/etc/nginx/nginx.conf"):
    upsteam_config = map(lambda x:upstream_config_gen(**x), listen_config_list)
    tmp={}
    for each in listen_config_list:
        listen_host = each['listen_host']
        if listen_host not in tmp:
            tmp[listen_host] = []
        tmp[listen_host].append(each)
    listen_config = []
    for k, each in tmp.items():
        if len(each)==1:
            listen_config.append(listen_config_gen(**each[0]))
        else:
            config=listen_config_gen0(**each[0])
            for x in each:
              config+=listen_location_config_gen(**x)
            config+=listen_config_gen1(**each[0])
            listen_config.append(config)
    stream_config = map(lambda x:stream_config_gen(**x), stream_config_list)
    content=f"""\
user  nginx;
worker_processes  auto;

error_log   /var/log/nginx/error.log notice;
pid         /var/run/nginx.pid;

events {{
    worker_connections  10240;
}}
http {{
  resolver {dns} valid=5 ipv6=off;
  include       /etc/nginx/mime.types;
  default_type  application/octet-stream;
  log_format  main  '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"' [Proxy-pass=$upstream_addr];

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

  server {{
    server_name _;
    server_tokens off;
    listen 80;
    return 503;
  }}

%s

%s
}}

stream {{
  log_format proxy '$remote_addr [$time_local] '
                 '$protocol $status $bytes_sent $bytes_received '
                 '$session_time -> $upstream_addr '
                 '$upstream_bytes_sent $upstream_bytes_received $upstream_connect_time';
  access_log /var/log/nginx/access.log proxy buffer=32k;
  open_log_file_cache off;

%s
}}
""" % ("\n".join(upsteam_config), "\n".join(listen_config), "\n".join(stream_config))
    with open(config_file, mode="w") as fout:
        fout.write(content)

def env_params(func):
    import inspect
    
    ret = {}
    for name,param in inspect.signature(func).parameters.items():
        if value := os.environ.get(name):
            ret[name] = value
        elif value := os.environ.get(name.upper()):
            ret[name] = value
    return ret

def main():
    import re
    listen_config=[]
    bind_config=[]
    forward_config=[]
    for each in os.environ.get("BIND","").split(";")+ list(filter(lambda kv:kv[0].startswith("BIND_"), os.environ.items())):
        if not each:
            continue
        regex=re.compile('((?P<udp>udp)@)?((?P<listen_port>\d+):)?(?P<host>[^:]+)(:(?P<port>\d+))?')
        config=next(regex.finditer(each)).groupdict()
        config['port'] = int(config['port'] or 80)
        config['listen_port'] = int(config['listen_port'] or config['port'])
        print(f"BIND[{each}]=>[{config}]")
        bind_config.append(config)
    regex_listen=re.compile('(?P<listen_host>[^:/]+)(?P<listen_path>/[^:]+)?:(?P<host>[^:/]+)(:(?P<port>\d+))?(?P<url>/[^@]+)?(@(?P<proxy_host>.+))?')
    i = 0
    def get_listen_config(line,forward=False):
        config=next(regex_listen.finditer(line)).groupdict()
        config['i']=int(k.split("_")[-1]) if k.startswith("LISTEN_") else 100+i
        config['port'] = int(config['port'] or 80)
        config['listen_path'] = config['listen_path'] or '/'
        config['url'] = config['url'] or config['listen_path']
        config['proxy_host'] = config['proxy_host'] or ('$http_host' if forward else '$proxy_host')
        print(f"LISTEN[{line}]=>[{config}]")
        config['config'] = f"{k}={line}"
        return config
    for k,each in list(filter(lambda kv:kv[0].startswith("LISTEN_"), os.environ.items())) + list(map(lambda x:("LISTEN",x),os.environ.get("LISTEN","").split(";"))):
        if not each:
            continue
        print(each)
        i+=1
        listen_config.append(get_listen_config(each))
    for k,each in list(filter(lambda kv:kv[0].startswith("FORWARD_"), os.environ.items())) + list(map(lambda x:("FORWARD",x),os.environ.get("FORWARD","").split(";"))):
        if not each:
            continue
        print(each)
        i+=1
        forward_config.append(get_listen_config(each,forward=True))
    gen_nginx_config(
        listen_config_list=listen_config+forward_config,
        stream_config_list=bind_config,
        **env_params(gen_nginx_config)
    )
        


if __name__=='__main__':
    print("""
Usage: 
  LISTEN=www.abc.com:www.baidu.com:80 FORWARD=www.baidu.com BIND=80:192.168.1.1:80 ./start.py

""")
    main()
    print("config ok")
    
