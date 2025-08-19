"""Module containing all configuration validation, setup and processing"""

import re
import json
import jsonschema
from jsonschema.exceptions import ValidationError as JSONValidationError 
try:
    import importlib.resources as impres
except ImportError:
    import importlib_resources as impres
from urllib.parse import urlsplit, urlunsplit
from datetime import timedelta, datetime

# Ensure that the context_schema.json file is located in the same src directory as this module
print(__name__)
try:
    JSONCONTEXTSCHEMA=impres.read_text(__name__, "context_schema.json",encoding='utf-8')
except TypeError:
    JSONCONTEXTSCHEMA=impres.read_text(__name__.split(".")[0], "context_schema.json",encoding='utf-8')




def baseurl(url):
    split_url = urlsplit(url)
    base_url = urlunsplit(list([split_url.scheme, split_url.netloc])+(['' for n in range(0,3)]))
    return base_url

def niceurl(url):
    split_url = urlsplit(url)
    nice_url = urlunsplit(split_url)
    if nice_url[-1]=="/":
        nice_url=nice_url[:-1]
    return nice_url



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
        match = FrequencyString._valid_regex.match(freq_string)
        if not match:
            raise ValueError(f"Invalid frequency string: {freq_string}")
        else:
            t,u = match.groups()
        return timedelta(**{FrequencyString._tcodes[u][1]:FrequencyString._strtonum(t)*FrequencyString._tcodes[u][2]})
    
    @staticmethod
    def _strtonum(s):
        try:
            return int(s)
        except ValueError:
            return float(s)



class Configuration(object):
    
    def __init__(self, json_filename):
        self.source_filename=json_filename
        with open(json_filename, "r") as jfile:
            configjson=json.load(jfile)

        # Validate json config file
        schemajson=json.loads(JSONCONTEXTSCHEMA)
        jsonschema.validate(configjson, schemajson)

        # Process sections of the config file for later reference
        self.unpack_contexts(configjson)
        self.unpack_server_config(configjson)
        
        # Build reverse_context_dictionary for identifying applicable contexts from url-bases
        found_bases=set()
        reverse_dict = dict()
        for name,v in self.contexts.items():
            base = niceurl(v['baseurl'])
            if base in found_bases:
                reverse_dict[base].append(name)
            else:
                reverse_dict[base]=[name]
        self.reverse_context_base_search_d = reverse_dict


    def unpack_contexts(self, config_json):
        contexts_d = dict()
        for obj in config_json['contexts']:
            contexts_d[obj['name']]=obj
        self.contexts=contexts_d

    def unpack_server_config(self, config_json):
        server_d = dict()
        for k,v in config_json['server'].items():
            server_d[k]=v
        self.server=server_d

    def get_context(self, context_name):
        if context_name in self.contexts.keys():
            c_dict = {**{"name" : context_name}, **self.contexts[context_name]}
            return RequestContext(**c_dict)
        else:
            pass
            #options = ",".join(self.contexts.keys())

            #raise KeyError (f"No {context_name} found in config {self.source_filename}. Try one of {{{options}}}")
    
    def search_matching_contexts(self, url):
        matching_contexts=list()
        best_context_keys=set()
        for k in self.reverse_context_base_search_d.keys():
            if k in url:
                best_context_keys.add(k)
        # Extract the longest best_context_key
        if len(best_context_keys)>0:
            context_key = sorted(list(best_context_keys), key=lambda x : len(x), reverse=True)[0]
            return self.reverse_context_base_search_d[context_key]


    def resolve_context_from_url(self, url):
        contexts = self.search_matching_contexts(url)
        if contexts is not None:
            if len(contexts)==1:
                return contexts[0]
            else:
                contexts_str=",".join(contexts)
                raise ValueError(f"Multiple contexts {{{contexts_str}}} returned for url {url} - review config")



class RequestContext(object):
    """ Class describing the set of headers and any other
    content to be associated with a URL request 
    normally, these would include authentication and any
    other contextual information that would normally be
    scoped by the domain being accessed"""
    def __init__(self, name, baseurl, headers, refresh, timeout=None, crawldepth=None, donotfollow=None):
        self.name = name
        self.baseurl = baseurl
        self.headers = headers
        self.refresh = refresh
        self.timeout = timeout
        self.crawldepth = crawldepth
        self.donotfollow = donotfollow
    
    @staticmethod
    def from_context_string(config : Configuration, context: str):
        return config.get_context(context)

