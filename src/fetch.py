import requests 
from urllib.parse import urlsplit, urlunsplit
import re
import datetime
import uuid
from datetime import timedelta, datetime
from functools import partial

import src.dbadmin as dbadmin
from src.config import Configuration


class RequestContext(object):
    """ Class describing the set of headers and any other
    content to be associated with a URL request 
    normally, these would include authentication and any
    other contextual information that would normally be
    scoped by the domain being accessed"""
    def __init__(self, name, base, headers, refresh, timeout=None):
        self.name = name
        self.base = base
        self.headers = headers
        self.refresh = refresh
        self.timeout = timeout
    
    @staticmethod
    def from_context_string(config : Configuration, context: str):
        return config.get_context(context)



class URLRequest(object):
    """Class used for wrapping a url http request
    (normally a get) both for preparing the call but
    also for capturing the resulting response."""

    def __init__(self, config, url, context):
        self.id = uuid.uuid4().hex
        self.url = url
        self.context = config.get_context(context)
        self.complete=False
        self.requested = False
        self.fetchts = None
        self.status = None

    @staticmethod
    def from_url(config, url):
        """Given a Configuration object reflecting the
        active configuration and a url, return a URLRequest
        object having resolved the context."""
        baseurl = URLRequest.baseurl(url)
        context = config.resolve_context_from_url(url)
        return URLRequest(config, url, context)


    def get(self):
        result = URLRequestResult(self)
        self.complete=True
        return result

    def to_dataclass(self):
        return dbadmin.URLRequestQueue(
            requestid = self.id,
            url = self.url,
            baseurl = URLRequest.baseurl(self.url),
            context = self.context.name,
            submittedts = datetime.now(),
            complete = self.complete
        )
    
    @staticmethod
    def baseurl(url):
        split_url = urlsplit(url)
        base_url = urlunsplit(list([split_url.scheme, split_url.netloc])+(['' for n in range(0,3)]))
        return base_url


class URLRequestResult(object):
    def __init__(self, url_request: URLRequest):
        self.request = url_request
        self._result = requests.get(url_request.url, headers=url_request.context.headers)
        self.fetchts = datetime.now()
        self.status = self._result.status_code
        self.content_length=None
        self.content_type=None
        self.content=self._result.content
        for k,v in self._result.headers.items():
            if k.lower()=='content-type':
                self.content_type = self._result.headers[k]
            elif k.lower()=='content-length':
                self.content_length = self._result.headers[k]

        self.content = self._result.content
        self.encoding = self._result.encoding
                
            

    def to_dataclass(self):
        return dbadmin.URLRequestResult(
            requestid = self.request.id,
            url = self.request.url, 
            baseurl = self.request.baseurl(self.request.url), 
            context = self.request.context.name, 
            fetchts = self.fetchts,
            status = self.status, 
            content_type = self.content_type, 
            content_length = self.content_length, 
            content_bytes = self.content, 
            content_encoding = self.encoding
        )