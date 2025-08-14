
from src.config import Configuration
from src.fetch import URLRequest
from src.extractlinks import URLLinkConnection
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
    request_data.complete=True
    session.add(request_data)
    dataclass_result = result.to_dataclass()
    session.add(dataclass_result)

def process_result_within_session(session, result_data):
    link_objects = [o.to_dataclass() for o in wcextractlinks.url_link_connections_from_result(result_data)]
    session.bulk_save_objects(link_objects)


def TriggerFetchProcess(config, DB, batchsize=50, threadpoolsize=5):
    # Pull incomplete requests in priority order
    with Session(DB.engine) as session:
        #pending_requests_data = session.execute(sqltext("select * from url_request_queue where complete != true order by submittedts"))
        pending_requests_objects = [o[0] for o in session.execute(select(wcdbadmin.URLRequestQueue).where(wcdbadmin.URLRequestQueue.complete!=True).order_by(wcdbadmin.URLRequestQueue.submittedts)).fetchall()]
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


def save_results_stub():
    # Save the results to the database
    with Session(DB.engine) as session:
        # Run the data-fetch from the request - note this is within the session
        result = url_request.get()
        obj = result.to_dataclass()
        session.add(obj)
        session.commit()

def other_content_stub():
    

    # Read Config
    config = Configuration("../config/config.json")

    # Setup Database
    DB = dbadmin.DataStore(config)

    # Create Request
    url_request = URLRequest.from_url(config, "https://www.bbc.co.uk/news/articles/c23p028p200o")

    # Save request to database
    with Session(DB.engine) as session:
        obj = url_request.to_dataclass()
        session.add(obj)
        session.commit()