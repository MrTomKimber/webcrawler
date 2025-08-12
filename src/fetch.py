import requests 
import urllib
import datetime
from functools import partial
import json
import jsonschema
from jsonschema.exceptions import ValidationError as JSONValidationError 
import importlib

JSONCONTEXTSCHEMA=importlib.resources.read_text(__name__, "context_schema.json",encoding='utf-8')
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
        self.source_filename=json_filename
        with open(json_filename, "r") as jfile:
            configjson=json.load(jfile)

        schemajson=json.loads(JSONCONTEXTSCHEMA)

        jsonschema.validate(configjson, schemajson)
        self.unpack_config(configjson)
        
        found_bases=set()
        reverse_dict = dict()
        for name,v in self.config.items():
            base = v['base']
            if base in found_bases:
                reverse_dict[base].append(name)
            else:
                reverse_dict[base]=[name]
        self.reverse_base_search_d = reverse_dict


    def unpack_config(self, config_json):
        config_d = dict()
        for obj in config_json['contexts']:
            config_d[obj['name']]=obj
        self.config=config_d

    def get_context(self, context_name):
        if context_name in self.config.keys():
            c_dict = {**{"name" : context_name}, **self.config[context_name]}
            return RequestContext(**c_dict)
        else:
            options = ",".join(self.config.keys())
            raise KeyError (f"No {context_name} found in config {self.source_filename}. Try one of {{{options}}}")


class RequestContext(object):
    """ Class describing the set of headers and any other
    content to be associated with a URL request 
    normally, these would include authentication and any
    other contextual information that would normally be
    scoped by the domain being accessed"""
    def __init__(self, name, base, headers, refresh):
        self.name = name
        self.base = base
        self.headers = headers
        self.refresh = refresh

    