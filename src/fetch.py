import requests 

import re
import datetime
import uuid
from datetime import timedelta, datetime
from functools import partial

import src.dbadmin as dbadmin
from src.config import Configuration, baseurl, niceurl

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
            #baseurl = baseurl(self.url),
            baseurl = self.context.baseurl,
            context = self.context.name,
            submittedts = datetime.now(),
            complete = self.complete
        )
    @staticmethod
    def from_dataclass(config, data : dbadmin.URLRequestQueue):
        item = URLRequest(config, data.url, data.context) 
        item.id = data.requestid
        item.complete = data.complete
        return item
    
class URLRequestResult(object):
    def __init__(self, url_request: URLRequest):
        self.request = url_request
        self._result = requests.get(url_request.url, headers=url_request.context.headers, timeout=3)
        self.fetchts = datetime.now()
        self.status = self._result.status_code
        self.content_length=None
        self.content_type=None
        self.content=self._result.content
        for k,v in self._result.headers.items():
            if k.lower()=='content-type':
                self.content_type = self._result.headers[k]
        self.content_length = len(self._result.content)

        self.content = self._result.content
        self.encoding = self._result.encoding
                
            

    def to_dataclass(self):
        return dbadmin.URLRequestResult(
            requestid = self.request.id,
            url = self.request.url, 
            baseurl = self.request.context.baseurl, 
            context = self.request.context.name, 
            fetchts = self.fetchts,
            status = self.status, 
            content_type = self.content_type, 
            content_length = self.content_length, 
            content_bytes = self.content, 
            content_encoding = self.encoding
        )