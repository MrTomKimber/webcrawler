import src.dbadmin as wcdbadmin
import bs4
from urllib.parse import urlsplit, urlunsplit, urljoin


def url_link_connections_from_result(resultdata : wcdbadmin.URLRequestResultData):
    html = unpack_contents(resultdata.content_bytes, "utf-8")
    requestid=resultdata.requestid
    context=resultdata.context
    url=resultdata.url
    baseurl=resultdata.baseurl
    raw_link_set = extract_links_from_html(html, url, baseurl)
    # Create list of link_objects
    link_objects = []
    for fullurl in raw_link_set:
        link_objects.append(URLLinkConnection(url, baseurl, fullurl, requestid, context))
    return link_objects

def extract_links_from_html(html, url):
    link_strainer = bs4.SoupStrainer("a")
    linkset=set()
    for link in bs4.BeautifulSoup(html, features="html.parser", parse_only=link_strainer):
        if 'href' in link.attrs :
            fullurl = urljoin(url, link['href'])
            linkset.add(fullurl)
    return linkset

def classify_contents(resultdata : wcdbadmin.URLRequestResultData):
    """What did the result fetch? 
    Was it html, plain-text, a word-document?
    A broad content classifier to help sift through different content types"""
    ctypes = content_type.split(";")
    pass

def unpack_contents(content_bytes, encoding):
    """Convert raw bytes into an instance of the original object, attempting to preserve original encoding."""
    # Default, always use utf-8
    return content_bytes.decode(encoding=encoding)

class URLLinkConnection(object):
    def __init__(self, from_url, from_urlbase, to_url, requestid, context):
        self.linkid = uuid.uuid4().hex
        self.requestid = requestid
        self.frombase = from_urlbase
        self.fromurl = from_url
        self.tourl = to_url
        self.fetchts = datetime.now()
        self.fetchcontext = context

    def linkclass(self):
        classoptions = { "local", "self-referring", "external" }
        if self.frombase in self.tourl and not self.fromurl in self.tourl:
            # Local link within base
            return "local"
        elif self.frombase in self.tourl and self.fromurl in self.tourl and self.tourl != self.fromurl:
            # Intra-page links that repoint to different anchors within the same page
            return "self-referring"
        elif self.frombase not in self.tourl:
            # Extra-site links that point elsewhere
            return "external"

    def to_dataclass(self):
        return wcdbadmin.URLLinkConnectionData(
            linkid = self.linkid,
            requestid =self.requestid,
            frombase=self.frombase,
            fromurl=self.fromurl ,
            tourl=self.tourl,
            fetchts=self.fetchts,
            fetchcontext=self.fetchcontext
        )

    