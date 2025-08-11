import requests 
import urllib
import datetime
from functools import partial
import json

class URLRequest(object):
    """Class used for wrapping a url http request
    (normally a get) both for preparing the call but
    also for capturing the resulting response."""

    def __init__(self, url, context):
        self.url = url
        self.context = context
        self.requested = False
        self.fetchts = None
        self.status = None

    def get(self):
        self._result = requests.get(self.url, headers=self.context.headers)
        self.requested = True
        self.fetchts = datetime.datetime.now()
        self.status = self._result.status_code
        return self._result
    
    @staticmethod
    def baseurl(url):
        split_url = urllib.parse.urlsplit(url)
        base_url = urllib.parse.urlunsplit(list([split_url.scheme, split_url.netloc])+(['' for n in range(0,3)]))
        return base_url


class ContextConfiguration(object):
    def __init__(self, json_filename):
        with open(json_filename, "r") as jfile:
            self.config=json.load(jfile)

    def get_context(self, context_name):
        if context_name in self.config.keys():
            c_dict = {**{"name" : context_name}, **self.config[context_name]}
            return RequestContext(**c_dict)
        else:
            raise KeyError (f"No {context_name} found in config {json_filename}.")


class RequestContext(object):
    """ Class describing the set of headers and any other
    content to be associated with a URL request 
    normally, these would include authentication and any
    other contextual information that would normally be
    scoped by the domain being accessed"""
    def __init__(self, name, base, headers):
        self.name = name
        self.base = base
        self.headers = headers

    