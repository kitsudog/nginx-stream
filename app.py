from gevent import monkey
monkey.patch_all()

from flask import Flask, request, Response, make_response
import requests
import os
from requests.adapters import HTTPAdapter
from requests import Session
import traceback
from typing import Dict
import re

s = Session()
adapter = HTTPAdapter(max_retries=1)
s.mount('http://', adapter)
s.mount('https://', adapter)

UPSTREAM_PROTO = "http"
UPSTREAM_HOST = os.environ.get("UPSTREAM_HOST", "127.0.0.1")
UPSTREAM_PORT = int(os.environ.get("UPSTREAM_PORT", 81))
UPSTREAM_TIMEOUT = int(os.environ.get("UPSTREAM_TIMEOUT", 3600))
UPSTREAM_PROXY_HOST = os.environ.get("UPSTREAM_PROXY_HOST", "TRUE") == "TRUE"
UPSTREAM_FILTER = list(
    filter(bool, os.environ.get("UPSTREAM_FILTER", "").split(","))
)

app = Flask(__name__)


def filter_response(raw: bytes, headers: Dict) -> bytes:
    # 减少多余的content解码
    print("filter_response", UPSTREAM_FILTER)
    for each in UPSTREAM_FILTER:
        print(f"run {each}")
        raw = eval(each)(raw, headers)
    return raw


@app.route('/', defaults={'path': ''}, methods=["GET", "POST"])
@app.route('/<path:path>', methods=["GET", "POST"])
def forward_common(path):
    headers = dict(request.headers)
    if UPSTREAM_PROXY_HOST:
        headers["HOST"] = headers["Host"]
    else:
        headers["HOST"] = UPSTREAM_HOST
    proxy_by = "nginx-stream:ex:" + headers["HOST"]
    try:
        if request.method == "GET":
            response = s.get(f'{UPSTREAM_PROTO}://{UPSTREAM_HOST}:{UPSTREAM_PORT}/{path}',
                             headers=headers, params=request.args, timeout=UPSTREAM_TIMEOUT)
        elif request.method == "POST":
            response = s.post(f'{UPSTREAM_PROTO}://{UPSTREAM_HOST}:{UPSTREAM_PORT}/{path}',
                              headers=headers, params=request.args, data=request.get_data(), timeout=UPSTREAM_TIMEOUT)
        else:
            response = make_response(('Server Error 503', 503))
            response.headers["proxy-by"] = proxy_by
            return response
        response_headers = dict()
        for k, v in response.headers.items():
            if k.lower() in {"transfer-encoding", "content-encoding", "content-length"}:
                continue
            response_headers[k] = v
        response_headers["proxy-by"] = proxy_by
        return Response(filter_response(response.content, response_headers), response.status_code, response_headers)
    except Exception:
        traceback.print_exc()
        response = make_response(('Bad Gateway 502', 502))
        response.headers["proxy-by"] = proxy_by
        return response


def replace(raw: bytes, header: Dict) -> bytes:
    content = raw.decode("utf8")
    for each in filter(bool, os.environ.get("REPLACE", "").split(",")):
        lh, _, rh = each.partition("=>")
        content = content.replace(lh, rh)
    for each in filter(bool, os.environ.get("REPLACE_PATTERN", "").split(",")):
        if each[0] != each[-1]:
            continue
        _, lh, rh, _ = each.split(each[0])
        content = re.sub(lh, rh, content)
    return content.encode("utf8")


if __name__ == '__main__':
    from gevent import pywsgi

    server = pywsgi.WSGIServer(('0.0.0.0', 8000), app)
    server.serve_forever()
