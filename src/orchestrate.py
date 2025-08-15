
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


def process_child_request_to_queue_and_close(session, config : Configuration, request : URLRequest, link : URLLinkConnection):
    parent_request_dataclass = request.to_dataclass()
    new_request = URLRequest.from_url(config, link.tourl)
    new_request.linkdepth = request.linkdepth + 1
    if new_request.context is not None:
        session.add(new_request.to_dataclass())
    parent_request_dataclass.closed=True



def QueueProcessWorker(config, DB, batchsize=50, threadpoolsize=5):
    
    with Session(DB.engine) as session:
        
        # Start with a collection of requests that have been fetched - this is the collection of requests that want closing off as complete
        # But to do so requires deciding whether to trigger any new requests off the back of the links found in these ones
        # For each request, there may be a number of underlying links to follow. 
        # Deciding which of these to request depends on whether they've been fetched before - and whether or not there's any in the current
        # request pool.

        pending_requests_identifiers = DB.sql_query("""
                                                        select request.requestid from 
                                                        url_request_queue request
                                                        where 
                                                        gotdata = True and 
                                                        gotlinks = True and
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
    