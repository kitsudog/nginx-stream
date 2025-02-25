#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2018 Alexander Grechin
#
# Licensed under the BSD 3-Clause license.
# See LICENSE file in the project root for full license information.
#

""" Build HTTP request"""
from typing import Optional

from dpkt import http

from HTTPRequest import HTTPRequest


class HTTPResponse(http.Response):
    """HTTP request class"""

    def __init__(self, response_dict=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.no = 0
        self.__dict = response_dict
        self.__content = None
        self.protocol = ''
        self.request: Optional[HTTPRequest] = None
        self.status_code = 0
        self.status = ''
        self.version = ''
        self.uri = ''
        self.method = ''
        self.headers = {}
        self.origin_headers = {}
        self.body = bytes()
        self.timestamp = ''
        self.src = ''
        self.sport = ''
        self.dst = ''
        self.dport = ''
        self.origin = ''
        if response_dict:
            self.build(response_dict)

    def to_dict(self):
        return self.__dict

    @property
    def content(self):
        if self.__content:
            return self.__content

        # headers, body = self.headers, self.body
        # original_content_type = headers.get("content-type", "").lower()
        # content_type, _, content_type2 = original_content_type.partition(";")[0].partition("/")
        #
        # if content_type in {"text"} or "charset" in original_content_type:
        #     if "utf-8" in original_content_type or "utf8" in original_content_type:
        #         content = body.decode("utf8")
        #     else:
        #         content = body.decode("utf8", "replace")
        # elif content_type in {"image"}:
        #     if "svg" in content_type:
        #         content = body.decode("utf8")
        #     else:
        #         content = body
        # elif content_type in {"audio", "video"}:
        #     if "svg" in content_type:
        #         content = body.decode("utf8")
        #     else:
        #         content = body
        # elif content_type in {"application"}:
        #     if content_type2 in {"octet-stream"}:
        #         content = body
        #     else:
        #         content = body.decode("utf8", "replace")
        # else:
        #     content = body
        self.__content = self.body.decode("utf8", "replace")
        return self.__content

    def build(self, response_dict):
        if 'no' in response_dict:
            self.no = response_dict["no"]
        if 'request' in response_dict:
            self.request = response_dict["request"]
        if 'protocol' in response_dict:
            self.protocol = response_dict["protocol"]
        if 'status' in response_dict:
            self.status = response_dict["status"]
        if 'status_code' in response_dict:
            self.status_code = response_dict["status_code"]
        if 'version' in response_dict:
            self.version = response_dict["version"]
        if 'uri' in response_dict:
            self.uri = response_dict["uri"]
        if 'method' in response_dict:
            self.method = response_dict["method"]
        if 'headers' in response_dict:
            self.headers = response_dict["headers"]
        if 'origin_headers' in response_dict:
            self.origin_headers = response_dict["origin_headers"]
        if 'body' in response_dict:
            self.body = response_dict["body"]
        if 'timestamp' in response_dict:
            self.timestamp = response_dict['timestamp']
        if 'src' in response_dict:
            self.src = response_dict['src']
        if 'sport' in response_dict:
            self.sport = response_dict['sport']
        if 'dst' in response_dict:
            self.dst = response_dict['dst']
        if 'dport' in response_dict:
            self.dport = response_dict['dport']
        if 'origin' in response_dict:
            self.origin = response_dict['origin']
