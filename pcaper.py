#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2018 Alexander Grechin
#
# Licensed under the BSD 3-Clause license.
# See LICENSE file in the project root for full license information.
#

""" Parse pcap file and asseble HTTP requests
"""

from __future__ import unicode_literals

import json
import os
import re
import time
import traceback
from datetime import datetime
from hashlib import md5
from typing import List, Optional
from urllib.parse import parse_qsl

import pymongo
from elasticsearch import Elasticsearch, helpers
from redis.client import Redis

from HTTPRequest import HTTPRequest
from HTTPResponse import HTTPResponse
from utils import PcapParser


class Filter:
    def __init__(self, params):
        self.params = params
        if regex := params.get("regex"):
            regex = re.compile(regex)
        else:
            regex = None
        self.regex: Optional[re.Pattern] = regex

    def __str__(self):
        if self.params.get("regex"):
            return f"~{self.params['mode']} {self.params['regex']}"
        else:
            return f"~{self.params['mode']}"


# noinspection PyMethodMayBeStatic
class RequestFilter(Filter):
    def match_request(self, req: HTTPRequest):
        return False


# noinspection PyMethodMayBeStatic
class ResponseFilter(Filter):

    def match_response(self, req: HTTPRequest, rsp: HTTPResponse):
        return False


# noinspection PyPep8Naming
class Filter_bq(RequestFilter):
    """
    Request body
    """

    def match_request(self, req: HTTPRequest):
        if req.body:
            if self.regex.search(req.body):
                return True
        return False


# noinspection PyPep8Naming
class Filter_bs(ResponseFilter):
    """
    Response body
    """

    def match_response(self, req: HTTPRequest, rsp: HTTPResponse):
        if content := rsp.content:
            if isinstance(content, str):
                if self.regex.search(content):
                    return True
        return False


# noinspection PyPep8Naming
class Filter_hq(RequestFilter):
    """
    Request header
    """

    def match_request(self, req: HTTPRequest):
        if self.regex.search(req.origin):
            return True
        return False


# noinspection PyPep8Naming
class Filter_hs(ResponseFilter):
    """
    Response header
    """

    def match_response(self, req: HTTPRequest, rsp: HTTPResponse):
        if self.regex.search(rsp.origin_headers):
            return True
        return False


# noinspection PyPep8Naming
class Filter_u(RequestFilter):
    """
    URL
    """

    def match_request(self, req: HTTPRequest):
        if self.regex.search(req.uri):
            return True
        return False


# noinspection PyPep8Naming
class Filter_d(ResponseFilter):
    """
    Domain
    """

    def match_response(self, req: HTTPRequest, rsp: HTTPResponse):
        if self.regex.search(req.headers.get("host")):
            return True
        if self.regex.search(rsp.headers.get("proxy-host")):
            # 针对proxy的
            return True
        return False


# noinspection PyPep8Naming
class Filter_c(ResponseFilter):
    """
    HTTP response code
    """

    def match_response(self, req: HTTPRequest, rsp: HTTPResponse):
        if self.regex.search(str(rsp.status_code)):
            return True
        return False


# noinspection PyPep8Naming
class Filter_m(RequestFilter):
    """
    Method
    """

    def match_request(self, req: HTTPRequest):
        if self.regex.search(req.method):
            return True
        return False


# noinspection PyPep8Naming
class Filter_q(ResponseFilter):
    """
    Match request with no response
    """

    def match_response(self, req: HTTPRequest, rsp: HTTPResponse):
        if len(rsp.body) == 0:
            return True
        return False


# noinspection PyPep8Naming
class Filter_ts(ResponseFilter):
    """
    Response Content-Type header
    """

    def match_response(self, req: HTTPRequest, rsp: HTTPResponse):
        if self.regex.search(rsp.headers.get("content-type")):
            return True
        return False


# noinspection PyPep8Naming
class Filter_tq(RequestFilter):
    """
    Request Content-Type header
    """

    def match_request(self, req: HTTPRequest):
        if self.regex.search(req.headers.get("content-type")):
            return True
        return False


def _es():
    if uri := os.environ.get("ES_URI"):
        service, auth, username, password, host, port_str, port, name, query = re.compile(
            r"(https?)://(([^:]+):([^@]+)?@)?([^:]+)(:(\d+))?/([^?]*)(\?.*)?"
        ).fullmatch(uri).groups()
        db = Elasticsearch(
            hosts=f"{service}://{host}{port_str}/{name}{query or ''}",
            basic_auth=(username, password),
            request_timeout=5000
        )
    else:
        host = os.environ.get("ES_HOST", "127.0.0.1")
        port = os.environ.get("ES_PORT", "9200")
        db = Elasticsearch(hosts=f"http://{host}:{port}", timeout=5000)
    db.ping()
    return db


def _mongo(cate):
    if uri := os.environ.get("MONGO_URI"):
        service, auth, username, password, host, _, port, name, query = re.compile(
            r"mongodb([^:]*)://(([^:]+):([^@]+)?@)?([^:]+)(:(\d+))?/([^?]*)\??(.*)"
        ).fullmatch(uri).groups()
    else:
        host = os.environ.get("MONGO_HOST", "127.0.0.1")
        port = os.environ.get("MONGO_PORT", "27017")
        name = os.environ.get("MONGO_NAME", "model")
        if port and re.compile(r"\d+").fullmatch(port):
            port = int(port)
        elif re.compile(r"tcp://[^:]+:\d+").fullmatch(port):
            port = int(port.split(":")[-1])
        auth = os.environ.get("MONGO_AUTH", "")
        if not host or not port:
            exit(1)
        if len(auth):
            auth = "%s@" % auth
        uri = f'mongodb://{auth}{host}:{port}/{name}'
    db = pymongo.MongoClient(
        uri,
        socketTimeoutMS=20000,
        connectTimeoutMS=10000,
        serverSelectionTimeoutMS=10000,
        connect=True,
    )
    db.server_info()
    collection = db[name][cate]
    if "timestamp_-1" not in collection.index_information():
        collection.create_index([("timestamp", pymongo.DESCENDING)], unique=False, sparse=True, background=True)
    return collection


mongo = None
es_bulk = None
output = os.environ.get("JSON_OUTPUT")
if mongo_collection := os.environ.get("MONGO_COLLECTION"):
    mongo = _mongo(mongo_collection)
if es_index := os.environ.get("ES_INDEX"):
    es = _es()


    def bulk(data: List[dict]):
        helpers.bulk(es, actions=data, index=es_index)


    es_bulk = bulk


# noinspection PyShadowingNames
def db_redis(index=0) -> Redis:
    import redis
    host = os.environ.get("REDIS_HOST", "127.0.0.1")
    port = os.environ.get("REDIS_PORT", "6379")
    if port and re.compile(r"\d+").fullmatch(port):
        port = int(port)
    elif re.compile(r"tcp://[^:]+:\d+").fullmatch(port):
        port = int(port.split(":")[-1])
    password = os.environ.get("REDIS_PASS", os.environ.get("REDIS_AUTH", None))
    if not host or not port:
        exit(1)
    db = redis.StrictRedis(host=host, port=port, decode_responses=True, db=index, password=password)
    db.execute_command("select", "%s" % index)
    return db


def to_header_dict(lines):
    ret = {}
    for each in lines:
        k, _, v = each.partition(":")
        ret[k.lower()] = v.lower()
    return ret


FILTER_EXPR = os.environ.get("FILTER_EXPR")
FROM = os.environ.get("FROM") or os.environ.get("HOSTNAME")
VERBOSE = os.environ.get("VERBOSE") == "TRUE"


# noinspection PyBroadException
def main():
    pcap_dir = os.environ.get("DATA_DIR", "/pcap")
    filter_expr_list = list(map(lambda x: eval(f"Filter_{x.group('mode')}({x.groupdict()})"), re.compile(
        r"~(?P<mode>all|a|bq|bs|b|comment|c|dns|dst|d|e|hq|hs|http|h|marked|marker|meta|m|q|replay|replayq|replays|src|s|tcp|tq|ts|t|udp|u|websocket)"
        r"( *(?P<regex>[^~]+[^~ ]))?"
    ).finditer(FILTER_EXPR)))
    request_filter_expr_list: List[RequestFilter] = list(
        filter(lambda x: issubclass(type(x), RequestFilter), filter_expr_list)
    )
    response_filter_expr_list: List[ResponseFilter] = list(
        filter(lambda x: issubclass(type(x), ResponseFilter), filter_expr_list)
    )
    while True:
        for each in sorted(filter(lambda x: x.endswith(".pcap"), os.listdir(pcap_dir)))[:-1]:
            file = os.path.join(pcap_dir, each)
            print(f"parser [file={file}]")
            if not os.path.getsize(file):
                os.remove(file)
                print(f"remove zero [file={file}]")
                continue
            try:
                buffer = []
                parser = PcapParser()
                for packet in filter(
                        lambda x: isinstance(x, HTTPResponse),
                        parser.read_pcap({"input": file})
                ):  # type: HTTPResponse
                    skip = False
                    for filter_expr in request_filter_expr_list:
                        if not filter_expr.match_request(packet.request):
                            skip = True
                            break
                    for filter_expr in response_filter_expr_list:
                        if not filter_expr.match_response(packet.request, packet):
                            skip = True
                            break
                    if skip:
                        continue
                    record = {
                        "timestamp": int(packet.timestamp * 1000),
                        "url": f"{packet.request.headers.get('host')}{packet.request.uri}",
                        "size": len(packet.origin) + len(packet.body) +
                                len(packet.request.origin) + len(packet.request.body),
                        "response": {
                            "body": packet.body[:1000].decode("utf8", "replace"),
                        },
                    }
                    if VERBOSE:
                        print(json.dumps(record))
                    record.update({
                        "request": {
                            "origin": packet.request.origin,
                            "header": to_header_dict(packet.request.origin.split("\r\n")[1:]),
                            "body": packet.request.body,
                        },
                        "response": {
                            "origin": packet.origin,
                            "header": to_header_dict(packet.origin.split("\r\n")[1:]),
                            "body": packet.body[:1024 * 1024],
                        },
                        "datetime": datetime.utcfromtimestamp(packet.timestamp),
                        "filter-expr": FILTER_EXPR,
                        "from": FROM,
                    })
                    if packet.request.body:
                        body = packet.request.body.strip()
                        if body.startswith(b"{") and body.endswith(b"}"):
                            record["request"]["json"] = json.loads(body.decode("utf8"))
                        elif body.startswith(b"[") and body.endswith(b"]"):
                            record["request"]["json"] = json.loads(body.decode("utf8"))
                        elif "application/x-www-form-urlencoded" == packet.request.headers["content-type"]:
                            record["request"]["form"] = dict(parse_qsl(body.decode("utf8"), keep_blank_values=True))
                    if packet.body:
                        body = packet.body.strip()
                        if body.startswith(b"{") and body.endswith(b"}"):
                            record["response"]["json"] = json.loads(body.decode("utf8"))
                        elif body.startswith(b"[") and body.endswith(b"]"):
                            record["response"]["json"] = json.loads(body.decode("utf8"))
                    buffer.append(record)
                print(f"parser [file={file}] [match={len(buffer)}]")
                if parser.last_stream:
                    print(f"parser [file={file}] not complete [stream_len={len(parser.last_stream)}]")
                if buffer:
                    if output:
                        def dumps(x):
                            if isinstance(x, bytes):
                                try:
                                    return x.decode("utf8")
                                except:
                                    return md5(x).hexdigest()
                            elif isinstance(x, datetime):
                                return x.isoformat()
                            return x

                        with open(f"{output}/{each}.json", mode="w") as fout:
                            fout.write(
                                "\n".join(map(lambda x: json.dumps(x, ensure_ascii=False, default=dumps), buffer))
                            )
                    if es_bulk:
                        es_bulk(list(map(lambda x: {
                            "filter-expr": x["filter-expr"],
                            "timestamp": x["timestamp"],
                            "datetime": x["datetime"],
                            "from": x["from"],
                        }, buffer)))
                        print(f"parser [file={file}] es [submit={len(buffer)}]")
                    if mongo:
                        ret = mongo.insert_many(buffer)
                        print(f"parser [file={file}] mongo [submit={len(ret.inserted_ids)}]")
            except Exception:
                traceback.print_exc()
            finally:
                try:
                    if os.environ.get("NO_REMOVE") == "TRUE":
                        pass
                    else:
                        os.remove(file)
                    if mongo:
                        mongo.delete_many({"timestamp": {"lt": int(datetime.now().timestamp() - 12 * 3600) * 1000}})
                except Exception:
                    traceback.print_exc()
        duration = 10
        print(f"sleep [{duration}s]")
        time.sleep(duration)


if __name__ == "__main__":
    main()
