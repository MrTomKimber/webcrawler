
from src.config import Configuration
from src.fetch import URLRequest, URLRequestResult, URLLinkConnection

import src.dbadmin as wcdbadmin
import src.extractlinks as wcextractlinks
from sqlalchemy.orm import Session
from sqlalchemy import select, text

import threading
import queue
from tqdm import tqdm
from math import ceil

import pandas as pd

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

        self.fetch_pending_requests_process = ThreadedDataProcess(self.config, 
                                                                  self.database, 
                                                                  100, 
                                                                  5, 
                                                                  """SELECT requestid, parent_requestid, linkdepth, maxdepth, url from url_request_queue where closed = false and gotdata = false""",
                                                                  fetch_pending_request_function, 
                                                                  )
        
        self.retrieve_links_from_data = ThreadedDataProcess(self.config, 
                                                                  self.database, 
                                                                  100, 
                                                                  1, 
                                                                  """SELECT que.requestid, 
                                                                  que.parent_requestid, 
                                                                  que.linkdepth, 
                                                                  que.maxdepth, 
                                                                  que.url, 
                                                                  res.meta_class
                                                                  FROM url_request_queue que 
                                                                  JOIN url_request_result res
                                                                  ON que.requestid = res.requestid
                                                                  WHERE 
                                                                    closed = false 
                                                                AND gotdata = true 
                                                                AND gotlinks = false
                                                                """,
                                                                  retrieve_links_function, 
                                                                  )
        
        self.request_request_from_links = ThreadedDataProcess(self.config, 
                                                                  self.database, 
                                                                  100, 
                                                                  1, 
                                                                  """SELECT 
                                                                        que.requestid, 
                                                                        link.linkid,
                                                                        link.tourl, 
                                                                        COALESCE(url_c.url_count,0) as existing, 
                                                                        que.linkdepth <= que.maxdepth as recurse,
                                                                        que.linkdepth,
                                                                        que.maxdepth, 
                                                                        link.followed, 
                                                                        link.donotfollow
                                                                    FROM 
                                                                        url_request_queue que 
                                                                    LEFT JOIN 
                                                                        url_link_connection link ON link.requestid = que.requestid 
                                                                    LEFT JOIN 
                                                                        url_request_result res ON link.requestid = res.requestid 
                                                                    LEFT JOIN
                                                                        (SELECT que.url url, count(*) url_count from url_request_queue que group by que.url) url_c on url_c.url = link.tourl
                                                                        
                                                                    WHERE 
                                                                        que.closed = false 
                                                                    AND que.gotlinks = true 
                                                                    AND link.followed = false
                                                                    AND COALESCE(url_c.url_count,0) = false""", 
                                                                    generate_requests_function,
                                                                    )
        
        self.close_exhausted_requests = ThreadedDataProcess(self.config, 
                                                                  self.database, 
                                                                  100, 
                                                                  1, 
                                                                  """SELECT  
                                                                        que.requestid, 
                                                                        count(link.linkid) as unfollowed_links

                                                                    FROM 
                                                                        url_request_queue que 
                                                                    LEFT JOIN 
                                                                        url_link_connection link ON link.requestid = que.requestid AND link.followed = false
                                                                    WHERE 
                                                                        que.closed = false 
                                                                    AND 
                                                                        que.gotlinks = true
                                                                        
                                                                    GROUP BY
                                                                        que.requestid""", 
                                                                    close_exhausted_requests_function,
                                                                    )
        self.close_duplicate_requests = ThreadedDataProcess(self.config, 
                                                                  self.database, 
                                                                  100, 
                                                                  1, 
                                                                  """SELECT
                                                                        que.requestid, 
                                                                        que.url, 
                                                                        que.submittedts, 
                                                                        que.linkdepth,
                                                                        dups.number, 
                                                                        RANK() OVER (PARTITION BY que.url ORDER BY que.linkdepth, submittedts)=1 as keep
                                                                    FROM
                                                                        (SELECT 
                                                                            que.url, 
                                                                            group_concat(que.requestid) ids, 
                                                                            count(que.requestid) number, 
                                                                            que.closed
                                                                        FROM url_request_queue que 
                                                                        WHERE
                                                                            que.closed = false
                                                                        GROUP BY 
                                                                            que.url, que.closed
                                                                        HAVING COUNT(que.url) > 1) as dups 
                                                                    JOIN 
                                                                        url_request_queue que ON dups.url = que.url
                                                                    WHERE 
                                                                        que.closed = false
                                                                    ORDER BY
                                                                        que.url, que.linkdepth, que.submittedts""", 
                                                                    close_duplicate_requests_function,
                                                                    )


    def perform_cycle(self):
        self.fetch_pending_requests_process.autorun()
        self.retrieve_links_from_data.autorun()
        self.request_request_from_links.autorun()
        self.close_exhausted_requests.autorun()
        self.close_duplicate_requests.autorun()

        
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

    
    
class ThreadedDataProcess(object):
    def __init__(self, config, datastore, batchsize, poolsize, pollsql, datafunction):
        self.config = config
        self.datafunction = datafunction
        self.batchsize = batchsize
        self.poolsize = poolsize
        self.pollsql = pollsql
        self.datastore = datastore

    def poll(self):
        poll_df = self.datastore.sql_to_dataframe(self.pollsql)
        return poll_df

    def execute(self, data):
        tasksize = len(data)

        arguments = self.config, self.datastore
        batchcount = ceil(tasksize/self.batchsize)
        for b in range(batchcount):
            for d in tqdm(range(b*self.batchsize, min((b+1)*self.batchsize, tasksize), self.poolsize)):
                threadpool=[]
                for t in range(d, min(d+self.poolsize, (b+1)*self.batchsize,tasksize)):
                    threadpool.append(threading.Thread(target=self.datafunction, args=(data[t], *arguments)))
                for t in threadpool:
                    t.start()
                for t in threadpool:
                    t.join()
                for t in threadpool:
                    del t
                del threadpool
            # Perform commits at completion of task (batch-intervals only used to break-up thread-operations

    def autorun(self):
        data = [r for i,r in self.poll().iterrows()]
        self.execute(data)



def fetch_pending_request_function(poll_data, config, datastore):
    """Reads dataclass data from a queue, converts it to the appropriate
    object (must have a from_dataclass initiation method) and then runs
    the objects get() method to create a result object, which is saved
    to the output_queue. Finally, the original object (with any mutations)
    is returned to the status_queue so those mutations can be written 
    back to the database."""
    with Session(datastore.engine) as session:
        queue_data = session.get(wcdbadmin.URLRequestQueueData, poll_data.requestid)
        queue_object = URLRequest.from_dataclass(config, queue_data)
        result = queue_object.get()
        dataclass_result = result.to_dataclass()
        queue_data.gotdata=True
        
        session.add(dataclass_result)
        session.commit()



def retrieve_links_function(poll_data, config, datastore):
    with Session(datastore.engine) as session:
        queue_data = session.get(wcdbadmin.URLRequestQueueData, poll_data.requestid)
        queue_object = URLRequest.from_dataclass(config, queue_data)
        result_data = session.get(wcdbadmin.URLRequestResultData, poll_data.requestid)
        result_object = URLRequestResult.from_dataclass(result_data)
        if result_object.classify_content() == "html":
            link_objects = [l.to_dataclass() for l in result_object.url_link_connections_from_result()]
            for linkdata in link_objects:
                linkdata.donotfollow = URLRequest.do_not_follow(config, linkdata.tourl)
                session.add(linkdata)
        
        queue_data.gotlinks=True
        session.commit()

def generate_requests_function(poll_data, config, datastore):
    with Session(datastore.engine) as session:
        url = poll_data.tourl
        new_request = URLRequest.from_url(config, url)
        if new_request.context is not None and url is not None:
            new_request.linkdepth = poll_data.linkdepth + 1
            if poll_data.existing == False and poll_data.recurse == True and poll_data.donotfollow == False:
                new_request.parent_requestid = poll_data.requestid
                session.add(new_request.to_dataclass())

        # Mark flag to show that the link has been evaluated
        if poll_data.linkid is not None:
            #print(poll_data.requestid, poll_data.linkid)
            link_object = session.get(wcdbadmin.URLLinkConnectionData, poll_data.linkid)
            if link_object is not None:
                link_object.followed = True
            else:
                print(f"{poll_data.linkid} not identified as a valid link-object")
        else:
            print(f"{url} not followed for {poll_data.requestid}")
        session.commit()

def close_exhausted_requests_function(poll_data, config, datastore):
    with Session(datastore.engine) as session:
        queue_data = session.get(wcdbadmin.URLRequestQueueData, poll_data.requestid)
        queue_object = URLRequest.from_dataclass(config, queue_data)
        queue_data.closed = True
        session.commit()

def close_duplicate_requests_function(poll_data, config, datastore):
    with Session(datastore.engine) as session:
        if poll_data.keep == False:
            queue_data = session.get(wcdbadmin.URLRequestQueueData, poll_data.requestid)
            queue_data.closed = True
            session.commit()








































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
        #print(batch_len)
        while i < (batch_len-1):
            threadpool=list()    
            #print(i, batch_len, threadpoolsize)
            for t in range(0, min(threadpoolsize, (batch_len-i)-1)):
                i=i+1
                #print(i)
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
        #print(f"batchlen{batch_len}")
        i=-1
        while i < (batch_len-1):
            threadpool=list()    
            for t in range(0, min(threadpoolsize, (batch_len-i)-1)):
                i=i+1
                requestid = pending_requests_identifiers[i][0]
                #print(requestid)
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
            #print(i)

        for requestid in close_list:
            request = session.get(wcdbadmin.URLRequestQueueData, requestid)
            request.closed=True
        session.commit()
        print(f"Processed {i+1} records.")
    return len(request_list)-(i+1)

