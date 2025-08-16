import requests 

import re
import datetime
import uuid
from datetime import timedelta, datetime
from functools import partial
from bs4 import BeautifulSoup, SoupStrainer
from urllib.parse import urlsplit, urlunsplit, urljoin

from src.config import Configuration, FrequencyString, baseurl, niceurl
import src.dbadmin as wcdbadmin



class URLRequest(object):
    """Class used for wrapping a url http request
    (normally a get) both for preparing the call but
    also for capturing the resulting response."""

    def __init__(self, config, url, context, depth=None):
        self.id = uuid.uuid4().hex
        self.url = url
        self.context = config.get_context(context)
        self.gotdata=False
        self.requested = False
        self.fetchts = None
        self.expirets = None
        self.status = None
        self.gotlinks = False
        self.closed = False
        self.parent_requestid=None
        if depth is None:
            depth=0
        self.linkdepth = depth
        self.fetchts=datetime.now()
        if self.context is not None:
            self.expirets=self.fetchts + FrequencyString.evaluate(self.context.refresh)

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
        
        content_type=None
        for k,v in _result.headers.items():
            if k.lower()=='content-type':
                content_type = _result.headers[k]

            result = URLRequestResult(
                requestid =self.id,
                url = self.url, 
                baseurl = self.context.baseurl,
                status = str(_result.status_code),
                content = _result.content,
                content_type = content_type, 
                encoding = _result.encoding, 
                fetchts = datetime.now()
                )

        self.gotdata=True
        return result

    def to_dataclass(self):
        return wcdbadmin.URLRequestQueueData(
            requestid = self.id,
            url = self.url,
            #baseurl = baseurl(self.url),
            baseurl = self.context.baseurl,
            context = self.context.name,
            submittedts = self.fetchts,
            expirets = self.expirets,
            gotdata = self.gotdata, 
            gotlinks = self.gotlinks, 
            closed = self.closed,
            linkdepth = self.linkdepth, 
            parent_requestid = self.parent_requestid
        )

    @staticmethod
    def from_dataclass(config, data : wcdbadmin.URLRequestQueueData):
        item = URLRequest(config, data.url, data.context, data.linkdepth) 
        item.id = data.requestid
        item.gotdata = data.gotdata
        item.gotlinks = data.gotlinks
        item.closed = data.closed
        item.fetchts = data.submittedts
        item.expirets = data.expirets
        item.parent_requestid = data.parent_requestid
        return item
    
class URLRequestResult(object):
    def __init__(self, 
                requestid : str,
                url : str, 
                baseurl : str,
                status : str,
                content : bytes,
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
        into a single place. The clues that are closest to the 
        document in question are presented first, as these *should*
        be more reliable indicators of the appropriate encoding to
        use."""
        
        encoding_clues = list()
        encoding_clues.append("{source}={value}".format(source="header", value=self.encoding))
        if self.content_type is not None:
            ctype, *others = self.content_type.split(";")
            for other in others:
                parm, value = other.lower().split("=")
                if parm.lower()=="charset":
#                    encoding_clues['mimetype']=value.lower()
                    encoding_clues.append("{source}={value}".format(source="mimetype", value=value.lower()))
        
        if self.classify_content()=='html':
            meta_charset_strainer = SoupStrainer("meta", {'charset':True})
            # Sift the first 500 bytes for any meta-tags that might be useful
            nodes = BeautifulSoup(self.content[0:500].decode("utf-8"), features="html.parser", parse_only=meta_charset_strainer)
            if len(nodes)>0:
                value=list(nodes.children)[0].attrs['charset'].lower()
                encoding_clues.append("{source}={value}".format(source="meta-charset", value=value))
        return ";".join(encoding_clues[::-1])


    def unpack_content(self):
        """Convert raw bytes into an instance of the original object, attempting to preserve original encoding."""
        # Try and use the first of any encoding_clues
        encoding = self.collate_encoding_clues().split(";")[0].lower().split("=")[1]
        return self.content.decode(encoding=encoding)
    

    def url_link_connections_from_result(self):
        html = self.unpack_content()
        requestid=self.requestid
        url=self.url
        # Generate a set of raw links
        raw_link_set = URLRequestResult.extract_links_from_html(html, url)
        # Create list of link_objects
        link_objects = []
        for fullurl in raw_link_set:
            link_objects.append(URLLinkConnection(url, fullurl, requestid))
        return link_objects

    @staticmethod
    def extract_links_from_html(html, url, remove_anchors=True):
        link_strainer = SoupStrainer("a")
        linkset=set()
        for link in BeautifulSoup(html, features="html.parser", parse_only=link_strainer):
            if 'href' in link.attrs :
                fullurl = urljoin(url, link['href'])
                # Sometimes urls will contain anchors, which aren't always useful 
                # so we optionally remove any anchor-links at this point
                if remove_anchors:
                    fullurl = urlunsplit(urlsplit(fullurl)._replace(fragment=""))
                linkset.add(fullurl)
        return linkset


    def to_dataclass(self):
        return wcdbadmin.URLRequestResultData(
            requestid = self.requestid,
            url = self.url, 
            baseurl = self.baseurl, 
            fetchts = self.fetchts,
            status = self.status, 
            content_type = self.content_type, 
            content_length = self.content_length, 
            content_bytes = self.content, 
            content_encoding = self.encoding, 
            meta_class=self.classify_content(),
            meta_encoding=self.collate_encoding_clues()
        )
    @staticmethod
    def from_dataclass(data : wcdbadmin.URLRequestResultData):
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





class URLLinkConnection(object):
    def __init__(self, from_url, to_url, requestid):
        self.linkid = uuid.uuid4().hex
        self.requestid = requestid
        self.fromurl = from_url
        self.tourl = to_url

    def linkclass(self):
        classoptions = { "local", "self-referring-anchor", "self-referring", "external" }
        from_comps = urlsplit(self.fromurl)
        to_comps = urlsplit(self.tourl)
        if (from_comps.netloc == to_comps.netloc) and ((from_comps.path != to_comps.path) or (from_comps.query != to_comps.query)):
            return "local"
        elif (from_comps.netloc == to_comps.netloc) and (from_comps.path == to_comps.path) and (from_comps.query == to_comps.query) and (self.fromurl != self.tourl):
            # Intra-page links that repoint to different anchors within the same page
            return "self-referring-anchor"
        elif (self.fromurl == self.tourl):
            # Links that point to themselves entirely
            return "self-referring"
        elif (from_comps.netloc != to_comps.netloc):
            # Extra-site links that point elsewhere
            return "external"

    def to_dataclass(self):
        return wcdbadmin.URLLinkConnectionData(
            linkid = self.linkid,
            requestid = self.requestid,
            fromurl = self.fromurl ,
            tourl = self.tourl
        )

    