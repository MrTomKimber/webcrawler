import requests 
import urllib
import re
import datetime
from datetime import timedelta
from functools import partial
import json
import jsonschema
from jsonschema.exceptions import ValidationError as JSONValidationError 
import importlib

# Ensure that the context_schema.json file is located in the same src directory as this module
JSONCONTEXTSCHEMA=importlib.resources.read_text(__name__, "context_schema.json",encoding='utf-8')




class FrequencyString(object):
    """Encodes a string containing a number and one of the codes {m|h|D|W|M|Y}
    to describe some number of time periods (minutes, hours, Days, Weeks, Months, Years)
    Note that Months are approximated at 30 days, and Years 365 days.
    As a consequence, for example, 12M != 1Y """

    _valid_regex = re.compile(r"^([\d]+?\.?[\d]*)([mhDWMY])$")

    _tcodes = {  "m" : ("minutes", "minutes", 1), 
                "h" : ("hours", "hours", 1), 
                "D" : ("days", "days", 1), 
                "W" : ("weeks", "weeks", 1), 
                "M" : ("months", "days", 30), 
                "Y" : ("years", "days", 365)}


    def __init__(self, freq_string):
        if self.validate(freq_string):
            self.value = FrequencyString.evaluate(freq_string)

        else:
            raise ValueError(f"{freq_string} doesn't conform to specification: `n{{m|h|D|W|M|Y}}` where n is a number, and the second component describes (m)inutes, (h)ours, (D)ays, (W)eeks, (M)onths or (Y)ears. e.g. 24h = 24 (h)ours, 30D = 30 (D)ays. Case sensitive.")

    @staticmethod
    def validate(freq_string):
        return bool(FrequencyString._valid_regex.match(freq_string))
    
    @staticmethod
    def evaluate(freq_string):
        t,u = FrequencyString._valid_regex.match(freq_string).groups()
        return timedelta(**{FrequencyString._tcodes[u][1]:FrequencyString._strtonum(t)*FrequencyString._tcodes[u][2]})
    
    @staticmethod
    def _strtonum(s):
        try:
            return int(s)
        except ValueError:
            return float(s)


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

