
from src.config import Configuration
from src.fetch import URLRequest
import src.dbadmin as dbadmin
from sqlalchemy.orm import Session
from sqlalchemy import select, text

import threading
import queue


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


def process_request(config, session, request_data):
    """Reads dataclass data from a queue, converts it to the appropriate
    object (must have a from_dataclass initiation method) and then runs
    the objects get() method to create a result object, which is saved
    to the output_queue. Finally, the original object (with any mutations)
    is returned to the status_queue so those mutations can be written 
    back to the database."""

    working_object = fetch.URLRequest.from_dataclass(config, request_data.URLRequestQueue)
    result = working_object.get()
    request_data.URLRequestQueue.complete=True
    session.add(request_data)
    dataclass_result = result.to_dataclass()
    session.add(dataclass_result)



def TriggerFetchProcess(config, DB, batchsize=50, threadpoolsize=5):
    url_request_queue=queue.Queue(maxsize=maxsize)

    # Pull incomplete requests in priority order
    with Session(DB.engine) as session:
        #pending_requests_data = session.execute(sqltext("select * from url_request_queue where complete != true order by submittedts"))
        pending_requests_objects = session.execute(select(dbadmin.URLRequestQueue).where(dbadmin.URLRequestQueue.complete!=True).order_by(dbadmin.URLRequestQueue.submittedts)).fetchall()
        batch_len = min(batchsize, len(pending_requests_objects))
        i=-1
        while i < batch_len:
            threadpool=list()    
            for t in range(min(threadpoolsize, batch_len-i)):
                threadpool.append(threading.Thread(target=process_request, args=(config, session, pending_requests_objects[i])))
                i=i+1
            for t in threadpool:
                t.start()
            for t in threadpool:
                t.join()
            del threadpool

        session.commit()
    return "Processed {i+1} records."




# Save the results to the database
with Session(DB.engine) as session:
    # Run the data-fetch from the request - note this is within the session
    result = url_request.get()
    obj = result.to_dataclass()
    session.add(obj)
    session.commit()