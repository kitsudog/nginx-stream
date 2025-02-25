from gevent import monkey

monkey.patch_all()
"""
负责中专请求实现额外的过滤等高级功能
"""
import json
from collections import UserDict


class Headers(UserDict):
    def __init__(self, *args, **kwargs):
        self.__keys = {}
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, value):
        if isinstance(key, str):
            key_lower = key.lower()
            if origin_key := self.__keys.get(key_lower):
                super().__setitem__(origin_key, value)
            else:
                origin_key = key
                self.__keys[key_lower] = key
                super().__setitem__(origin_key, value)
        else:
            origin_key = key
            self.__keys[key] = origin_key
            super().__setitem__(origin_key, value)

    def __delitem__(self, key):
        if isinstance(key, str):
            key_lower = key.lower()
            if origin_key := self.__keys.get(key_lower):
                super().__delitem__(origin_key)
                del self.__keys[key_lower]
                return
        super().__delitem__(key)
        del self.__keys[key]

    def __getitem__(self, key):
        if isinstance(key, str):
            return super().__getitem__(self.__keys[key.lower()])
        else:
            return super().__getitem__(key)

    def __contains__(self, key):
        if super().__contains__(key):
            return True
        if isinstance(key, str):
            return key.lower() in self.__keys
        else:
            return False

    def items_lower(self):
        for k, v in super().items():
            if isinstance(k, str):
                yield k.lower(), v
            else:
                yield k, v


from flask import Flask, request, Response, make_response
import os
from requests.adapters import HTTPAdapter, DEFAULT_RETRIES
from requests import Session
import traceback
from typing import Tuple
import re

s = Session()
adapter = HTTPAdapter(max_retries=DEFAULT_RETRIES)
# noinspection HttpUrlsUsage
s.mount('http://', adapter)
s.mount('https://', adapter)
s.proxies = {}
if all_proxy := os.environ.get("ALL_PROXY") or os.environ.get("all_proxy"):
    s.proxies["http"] = all_proxy
    s.proxies["https"] = all_proxy
if http_proxy := os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"):
    s.proxies["http"] = http_proxy
if https_proxy := os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"):
    s.proxies["http"] = https_proxy

UPSTREAM_PROTO = "http"
UPSTREAM_HOST = os.environ.get("UPSTREAM_HOST", "127.0.0.1")
UPSTREAM_PORT = int(os.environ.get("UPSTREAM_PORT", 81))
UPSTREAM_TIMEOUT = int(os.environ.get("UPSTREAM_TIMEOUT", 3600))
UPSTREAM_PROXY_HOST = os.environ.get("UPSTREAM_PROXY_HOST", "TRUE") == "TRUE"
UPSTREAM_FILTER = list(
    filter(bool, os.environ.get("UPSTREAM_FILTER", "").split(","))
)

app = Flask(__name__)


def filter_response(raw: bytes, headers: Headers) -> Tuple[bytes, Headers]:
    # 减少多余的content解码
    # print("filter_response", UPSTREAM_FILTER)
    for each in UPSTREAM_FILTER:
        # print(f"run {each}")
        ret = eval(each)(raw, headers)
        if isinstance(ret, tuple) and len(ret) == 2:
            raw, headers = ret[0], ret[1]
        elif isinstance(ret, bytes):
            raw = ret
        else:
            print(type(ret))
            assert False, f"[filter={each}]实现错误"
    return raw, headers


# noinspection PyBroadException
@app.route('/', defaults={'path': ''}, methods=["GET", "POST"])
@app.route('/<path:path>', methods=["GET", "POST"])
def forward_common(path):
    headers = dict(request.headers)
    if UPSTREAM_PROXY_HOST:
        headers["HOST"] = headers["Host"]
    else:
        headers["HOST"] = UPSTREAM_HOST
    if headers.get("Accept-Encoding"):
        # fix: 可能引入莫名其妙的压缩格式
        del headers['Accept-Encoding']
    proxy_by = "nginx-stream:ex:" + headers["HOST"]
    try:
        if request.method == "GET":
            # noinspection PyTypeChecker
            response = s.get(
                f'{UPSTREAM_PROTO}://{UPSTREAM_HOST}:{UPSTREAM_PORT}/{path}',
                headers=headers, params=request.args, timeout=UPSTREAM_TIMEOUT, allow_redirects=False
            )
        elif request.method == "POST":
            # noinspection PyTypeChecker
            response = s.post(
                f'{UPSTREAM_PROTO}://{UPSTREAM_HOST}:{UPSTREAM_PORT}/{path}',
                headers=headers, params=request.args, data=request.get_data(), timeout=UPSTREAM_TIMEOUT,
                allow_redirects=False
            )
        else:
            response = make_response(('Server Error 503', 503))
            response.headers["proxy-by"] = proxy_by
            return response
        if response.status_code in {301, 302}:
            print(f"[redirect] {response.headers['Location']}")
        response_headers = Headers(response.headers)
        for k in {"transfer-encoding", "content-encoding", "content-length"}:
            if k in response_headers:
                del response_headers[k]
        response_headers["proxy-by"] = proxy_by
        content, headers = filter_response(response.content, response_headers)
        return Response(content, response.status_code, dict(headers))
    except Exception:
        traceback.print_exc()
        response = make_response(('Bad Gateway 502', 502))
        response.headers["proxy-by"] = proxy_by
        return response


# noinspection PyBroadException
def replace(raw: bytes, headers: Headers) -> Tuple[bytes, Headers]:
    try:
        # todo: 只针对部分做
        content = raw.decode("utf8")
    except Exception:
        return raw, headers

    def __replace(src):
        for each in filter(bool, os.environ.get("REPLACE", "").split(",")):
            lh, _, rh = each.partition("=>")
            src = src.replace(lh, rh)
        for each in filter(bool, os.environ.get("REPLACE_PATTERN", "").split(",")):
            if each[0] != each[-1]:
                continue
            _, lh, rh, _ = each.split(each[0])
            src = re.sub(lh, rh, src)
        return src

    content = __replace(content)
    # 针对Set-Cookie处理
    if "set-cookie" in headers:
        headers["set-cookie"] = __replace(headers["set-cookie"])
    # 针对Set-Cookie处理
    if "location" in headers:
        headers["location"] = __replace(headers["location"])
    return content.encode("utf8"), headers


@app.route('/echo', methods=["GET", "POST"])
def echo():
    origin = {
        "url": request.url,
        "method": request.method,
        "headers": dict(request.headers),
        "data": request.get_data().decode("utf8", errors="ignore"),
        "form": dict(request.form),
        "cookie": dict(request.cookies),
        "remote": request.remote_addr,
    }
    json_ret = json.dumps(origin, indent=2)
    print(json_ret)
    return json_ret.encode("utf8"), {"Content-Type": "application/json"}


if __name__ == '__main__':
    from gevent import pywsgi

    server = pywsgi.WSGIServer(('0.0.0.0', 8000), app, log=None)
    server.serve_forever()
