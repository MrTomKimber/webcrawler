
from src.config import Configuration
from src.fetch import URLRequest, URLRequestResult, URLLinkConnection

import src.dbadmin as wcdbadmin
import src.extractlinks as wcextractlinks
from sqlalchemy.orm import Session
from sqlalchemy import select, text

import threading
import queue


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
    return f"Processed {i+1} records."


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
        
        [o[0] for o in session.execute(select(wcdbadmin.URLRequestQueueData).where(wcdbadmin.URLRequestQueueData.gotdata!=True).order_by(wcdbadmin.URLRequestQueueData.submittedts)).fetchall()]
        batch_len = min(batchsize, len(pending_requests_identifiers))
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
    return f"Processed {i+1} records."

def close_parental_request(session, request : URLRequest):
    parent_request_dataclass = request.to_dataclass()
    parent_request_dataclass.closed=True


def process_child_request_to_queue(session, config : Configuration, request : URLRequest, link : URLLinkConnection):
    parent_request_dataclass = request.to_dataclass()
    new_request = URLRequest.from_url(config, link.tourl)
    new_request.linkdepth = request.linkdepth + 1
    new_request.parent_requestid = request.id
    if new_request.context is not None:
        session.add(new_request.to_dataclass())
    

def setlist(values):
    return list(set(values))

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
                    where 
                    que.gotdata = true
                    and res.fetchts < que.expirets
                    """)[0]])
        
        request_candidates_df = DB.sql_to_dataframe("""SELECT link.tourl, que.requestid
                                                        FROM url_link_connection link
                                                        JOIN url_request_queue que on link.requestid=que.requestid
                                                        WHERE
                                                        que.closed=false AND
                                                        que.gotdata=true AND
                                                        que.gotlinks=true 
                                                        """)
        # Build an index on the list of candidate urls that excludes any that do not have a matching context defined in config
        context_index = request_candidates_df['tourl'].apply(lambda x : config.resolve_context_from_url(x) is not None and x not in url_exclusion_set)
        # Consolidate the list of remaining urls, and list any open requestids that act as parents
        url_requestid_series = request_candidates_df[context_index].groupby("tourl")['requestid'].agg(setlist)
        request_list = []
        total_set = set(request_candidates_df['requestid'].values)
        close_set = set()
        request_set = set()
        for url, requests in url_requestid_series.items():
            f,*r = requests
            request_list.append((url, f))
            request_set.add(f)
            
        close_set = total_set - request_set

        
        [o[0] for o in session.execute(select(wcdbadmin.URLRequestQueueData).where(wcdbadmin.URLRequestQueueData.gotdata!=True).order_by(wcdbadmin.URLRequestQueueData.submittedts)).fetchall()]
        batch_len = min(batchsize, len(pending_requests_identifiers))
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
    return f"Processed {i+1} records."


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
    