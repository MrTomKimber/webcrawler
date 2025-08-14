import requests 

import re
import datetime
import uuid
from datetime import timedelta, datetime
from functools import partial
import bs4

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
        self.gotlinks = False

    @staticmethod
    def from_url(config, url):
        """Given a Configuration object reflecting the
        active configuration and a url, return a URLRequest
        object having resolved the context."""
        context = config.resolve_context_from_url(url)
        return URLRequest(config, url, context)


    def get(self):
        _result = requests.get(
                    self.url, 
                    headers=self.context.headers, 
                    timeout=3)
        fetchts=datetime.now()
        content_type=None
        for k,v in _result.headers.items():
            if k.lower()=='content-type':
                content_type = _result.headers[k]

            result = URLRequestResult(
                requestid =self.id,
                url = self.url, 
                baseurl = self.context.baseurl,
                status = _result.status_code,
                content = _result.content,
                content_type = content_type, 
                encoding = _result.encoding, 
                fetchts = fetchts
                )

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
            complete = self.complete, 
            gotlinks = self.gotlinks
        )

    @staticmethod
    def from_dataclass(config, data : dbadmin.URLRequestQueue):
        item = URLRequest(config, data.url, data.context) 
        item.id = data.requestid
        item.complete = data.complete
        item.gotlinks = data.gotlinks
        return item
    
class URLRequestResult(object):
    def __init__(self, 
                requestid : str,
                url : str, 
                baseurl : str,
                status : str,
                content : str,
                content_type : str, 
                encoding :str, 
                fetchts 
                ):
        self.requestid = requestid
        self.url = url
        self.baseurl = baseurl
        self.status = status
        self.content=content
        self.content_type=content_type
        self.content_length=len(content)
        self.encoding = encoding
        self.fetchts = fetchts

    def classify_content(self):
        # Extendable function to identify and classify known
        # content-classes. 
        if self.content_type is not None:
            content_classes = {"html", "other"}
            ctype, *others = self.content_type.split(";")
            if ctype.lower() == "text/html":
                return "html"
            else:
                return "other"
        return "None"

    def collate_encoding_clues(self):
        """Encoding clues can be spread across multiple locations
        this function aims to collate all possible encoding cues
        into a single place"""
        encoding_clues = dict()
        encoding_clues['header']=self.encoding
        if self.content_type is not None:
            ctype, *others = self.content_type.split(";")
            for other in others:
                parm, value = other.lower().split("=")
                if parm.lower()=="charset":
                    encoding_clues['mimetype']=value.lower()
        
        if self.classify_content()=='html':
            meta_charset_strainer = bs4.SoupStrainer("meta", {'charset':True})
            # Sift the first 500 bytes for any meta-tags that might be useful
            nodes = bs4.BeautifulSoup(self.content[0:500].decode("utf-8"), features="html.parser", parse_only=meta_charset_strainer)
            if len(nodes)>0:
                encoding_clues['meta-charset']=list(nodes.children)[0].attrs['charset'].lower()
        return encoding_clues


    def to_dataclass(self):
        return dbadmin.URLRequestResultData(
            requestid = self.requestid,
            url = self.url, 
            baseurl = self.baseurl, 
            fetchts = self.fetchts,
            status = self.status, 
            content_type = self.content_type, 
            content_length = self.content_length, 
            content_bytes = self.content, 
            content_encoding = self.encoding
        )
    @staticmethod
    def from_dataclass(data : dbadmin.URLRequestResultData):
        return URLRequestResult(
            requestid=data.requestid,
            url = data.url, 
            baseurl = data.baseurl,
            status = data.status,
            content = data.content_bytes,
            content_type = data.content_type, 
            encoding = data.content_encoding, 
            fetchts = data.fetchts
            )

