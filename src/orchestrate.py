
from src.config import Configuration
from src.fetch import URLRequest, URLRequestResult, URLLinkConnection

import src.dbadmin as wcdbadmin
import src.extractlinks as wcextractlinks
from sqlalchemy.orm import Session
from sqlalchemy import select, text

import threading
import queue

import logging

class WebCrawler(object):
    def __init__(self, config : str):
        self.config=Configuration(config)

        logging.basicConfig(format='%(levelname)s:%(message)s')
        self.logger = logging.getLogger('sqlalchemy')
        self.logger.setLevel(logging.ERROR)
        self.logger.propagate = False
        # Ensure logfile is truncated for demonstration
        logfile = 'actions.log'
        handler = logging.FileHandler(logfile, mode='w')
        self.logger.setLevel(logging.INFO)

        self.logger.handlers = []

        handler.setLevel(logging.INFO)
        self.logger.addHandler(handler)

        # Suppress output from child loggers
        logging.getLogger('sqlalchemy.engine').handlers = []
        logging.getLogger('sqlalchemy.pool').handlers = []
        logging.getLogger('sqlalchemy.orm').handlers = []

        self.database=wcdbadmin.DataStore(self.config)
        
    def _submit_url_to_queue(self, url):
        url_request = URLRequest.from_url(self.config, url)
        if url_request.context is None:
            self.logger.info(f"No matching context found for {url} review your config file.")
        else:
            with Session(self.database.engine) as session:
                obj = url_request.to_dataclass()
                session.add(obj)
                session.commit()
            self.logger.info(f"Added {url} to queue - requestid: {url_request.id}")

    def _work_on_request_queue(self):
        """Look for outstanding items on the request queue and process them"""
        remaining = -1
        while remaining != 0:
            remaining = FetchProcessWorker(self.config, self.database,batchsize=1000, threadpoolsize=5)
        return remaining

    def _work_on_result_list(self):
        """From the completed requests, extract links"""
        remaining = -1
        while remaining != 0:
            remaining = LinkProcessWorker(self.config, self.database, batchsize=1000, threadpoolsize=5)
        return remaining 
    
    def _work_on_pending_links(self):
        """From the pool of unfetched links, identify new requests and add to the request queue"""
        remaining = -1
        while remaining != 0:
            remaining = QueueProcessWorker(self.config, self.database, batchsize=50, threadpoolsize=5)
        return remaining

    


def submit_url_to_queue(config, datastore, url):
    url_request = URLRequest.from_url(config, url)
    if url_request.context is not None:
        with Session(datastore.engine) as session:
            obj = url_request.to_dataclass()
            session.add(obj)
            session.commit()
    else:
        print(f"No matching Context found for {url}")

def process_request_within_session(config, session, request_data):
    """Reads dataclass data from a queue, converts it to the appropriate
    object (must have a from_dataclass initiation method) and then runs
    the objects get() method to create a result object, which is saved
    to the output_queue. Finally, the original object (with any mutations)
    is returned to the status_queue so those mutations can be written 
    back to the database."""

    working_object = URLRequest.from_dataclass(config, request_data)
    result = working_object.get()
    request_data.gotdata=True
    session.add(request_data)
    dataclass_result = result.to_dataclass()
    session.add(dataclass_result)


def FetchProcessWorker(config, DB, batchsize=50, threadpoolsize=5):
    # Pull incomplete requests in priority order
    with Session(DB.engine) as session:
        #pending_requests_data = session.execute(sqltext("select * from url_request_queue where gotdata != true order by submittedts"))
        pending_requests_objects = [o[0] for o in session.execute(select(wcdbadmin.URLRequestQueueData).where(wcdbadmin.URLRequestQueueData.gotdata!=True).order_by(wcdbadmin.URLRequestQueueData.submittedts)).fetchall()]
        batch_len = min(batchsize, len(pending_requests_objects))
        i=-1
        print(batch_len)
        while i < (batch_len-1):
            threadpool=list()    
            print(i, batch_len, threadpoolsize)
            for t in range(0, min(threadpoolsize, (batch_len-i)-1)):
                i=i+1
                print(i)
                threadpool.append(threading.Thread(target=process_request_within_session, args=(config, session, pending_requests_objects[i])))
                
            for t in threadpool:
                t.start()
            for t in threadpool:
                t.join()
            del threadpool

        session.commit()
    print (f"Processed {i+1} records.")
    return len(pending_requests_objects)-(i+1)


def process_links_from_result_within_session(session, result_data):
    working_object = URLRequestResult.from_dataclass(result_data)
    if working_object.classify_content() == "html":
        link_objects = [l.to_dataclass() for l in working_object.url_link_connections_from_result()]
        for linkdata in link_objects:
            session.add(linkdata)

def LinkProcessWorker(config, DB, batchsize=50, threadpoolsize=5):
    
    with Session(DB.engine) as session:
        
        pending_requests_identifiers = DB.sql_query("""
                                                        select request.requestid from 
                                                        url_request_queue request
                                                        where 
                                                        gotdata = True and 
                                                        gotlinks = False and
                                                        closed = False
                                                        """)[0]
        
#        [o[0] for o in session.execute(select(wcdbadmin.URLRequestQueueData).where(wcdbadmin.URLRequestQueueData.gotdata!=True).order_by(wcdbadmin.URLRequestQueueData.submittedts)).fetchall()]
        batch_len = min(batchsize, len(pending_requests_identifiers))
        print(f"batchlen{batch_len}")
        i=-1
        while i < (batch_len-1):
            threadpool=list()    
            for t in range(0, min(threadpoolsize, (batch_len-i)-1)):
                i=i+1
                requestid = pending_requests_identifiers[i][0]
                print(requestid)
                working_result_dataclass = session.get(wcdbadmin.URLRequestResultData, requestid)
                working_queue_dataclass = session.get(wcdbadmin.URLRequestQueueData, requestid)
                threadpool.append(threading.Thread(target=process_links_from_result_within_session, args=(session, working_result_dataclass)))
                working_queue_dataclass.gotlinks=True
            for t in threadpool:
                t.start()
            for t in threadpool:
                t.join()
            del threadpool

        session.commit()
        print(f"Processed {i+1} records.")
    return len(pending_requests_identifiers)-(i+1)

def close_parental_request(session, request : URLRequest):
    parent_request_dataclass = request.to_dataclass()
    session.add(parent_request_dataclass)
    parent_request_dataclass.closed=True


def process_child_request_to_queue(session, config : Configuration, request : URLRequest, link : str):
    new_request = URLRequest.from_url(config, link)
    if new_request.context is not None:
        new_request.linkdepth = request.linkdepth + 1
        if new_request.linkdepth <= new_request.context.crawldepth:
            new_request.parent_requestid = request.id
            session.add(new_request.to_dataclass())
            

def setlist(values):
    return list(set(values))

def first(values):
    return list(values)[0]

def QueueProcessWorker(config, DB, batchsize=50, threadpoolsize=5):
    
    with Session(DB.engine) as session:
        
        # Start with a collection of requests that have been fetched - this is the collection of requests that want closing off as complete
        # But to do so requires deciding whether to trigger any new requests off the back of the links found in these ones
        # For each request, there may be a number of underlying links to follow. 
        # Deciding which of these to request depends on whether they've been fetched before - and whether or not there's any in the current
        # request pool.

        url_exclusion_set = set([v[0] for v in DB.sql_query("""SELECT res.url
                    FROM url_request_result res
                    JOIN url_request_queue que on res.requestid = que.requestid
                    WHERE 
                    que.gotdata = true
                    and res.fetchts < que.expirets
                    UNION ALL
                    SELECT que.url
                    FROM url_request_queue que
                    WHERE
                    que.gotdata = false
                    """)[0]])
        
        request_candidates_df = DB.sql_to_dataframe("""SELECT link.tourl, que.requestid, que.submittedts
                                                        FROM url_link_connection link
                                                        JOIN url_request_queue que on link.requestid=que.requestid
                                                        WHERE
                                                        que.closed=false AND
                                                        que.gotdata=true AND
                                                        que.gotlinks=true AND
                                                        que.linkdepth < que.maxdepth
                                                        """)
        

        expired_candidates_df = DB.sql_to_dataframe("""SELECT que.requestid, que.submittedts
                                                        FROM url_link_connection link
                                                        JOIN url_request_queue que on link.requestid=que.requestid
                                                        WHERE
                                                        que.closed=false AND
                                                        que.gotdata=true AND
                                                        que.gotlinks=true AND
                                                        que.linkdepth = que.maxdepth
                                                        """)





        expired_candidates_set = set(expired_candidates_df['requestid'].values)

        # Build an index on the list of candidate urls that excludes any that do not have a matching context defined in config
        context_index = request_candidates_df['tourl'].apply(lambda x : config.resolve_context_from_url(x) is not None and x not in url_exclusion_set)

        # Construct dict resolbing requestids to their submission timestamps:
        reqts_d = dict(request_candidates_df[['requestid','submittedts']].groupby('requestid')['submittedts'].agg(first))
    
        # Consolidate the list of remaining urls, and list any open requestids that act as parents
        url_requestid_series = request_candidates_df[context_index].groupby("tourl")['requestid'].agg(setlist)
        request_list = []
        total_set = set(request_candidates_df['requestid'].values).union(expired_candidates_set)
        close_set = set()
        request_set = set()
        for url, requests in url_requestid_series.items():
            f,*r = sorted(requests, key=lambda x : reqts_d.get(x))
            # urls for which multiple requests are attributed
            # take request sumbission timestamp (earliest) to decide
            # which request to pin the url to.
            request_list.append((url, f))
            request_set.add(f)
            
        close_set = total_set - request_set

        close_list = list(close_set)

        batch_len = min(batchsize, len(request_list))
        i=-1
        while i < (batch_len-1):
            threadpool=list()    
            for t in range(0, min(threadpoolsize, (batch_len-i)-1)):
                i=i+1
                link, requestid = request_list[i]
                requestdata=session.get(wcdbadmin.URLRequestQueueData, requestid)
                request = URLRequest.from_dataclass(config, requestdata)
                threadpool.append(threading.Thread(target=process_child_request_to_queue, args=(session, config, request, link)))
            for t in threadpool:
                t.start()
            for t in threadpool:
                t.join()
            del threadpool
            print(i)

        for requestid in close_list:
            request = session.get(wcdbadmin.URLRequestQueueData, requestid)
            request.closed=True
        session.commit()
        print(f"Processed {i+1} records.")
    return len(request_list)-(i+1)



def ProcessURLRequestQueue(config, DB, batchsize=100, threadpoolsize=30):
    def get_pending_q_length(DB):
        return DB.sql_query("select count(*) as pending from url_request_queue where gotdata=false and closed=false")[0][0][0]
    queue_length = get_pending_q_length(DB)
    while queue_length > 0:
        FetchProcessWorker(config, DB, batchsize=batchsize, threadpoolsize=threadpoolsize)
        queue_length = get_pending_q_length(DB)

def ProcessPendingExtractLinks(config, DB, batchsize=100, threadpoolsize=30):
    def get_pending_count(DB):
        return DB.sql_query("""select count(*) as pending from 
                            url_request_queue request
                            where gotdata = True and gotlinks = False and closed = False""")[0][0][0]
    queue_length = get_pending_count(DB)
    while queue_length > 0:
        LinkProcessWorker(config, DB, batchsize=batchsize, threadpoolsize=threadpoolsize)
        queue_length = get_pending_count(DB)
    