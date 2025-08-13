
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


def unpack_and_get_result(config, input_queue, output_queue, batch_size=0):
    """Reads dataclass data from a queue, converts it to the appropriate
    object (must have a from_dataclass initiation method) and then runs
    the objects get() method to create a result object, which is saved
    to the output_queue. Finally, the original object (with any mutations)
    is returned to the status_queue so those mutations can be written 
    back to the database."""
    i=0
    try:
        while i < batch_size :
            i=i+1
            request_data = input_queue.get()
            working_object = fetch.URLRequest.from_dataclass(config, request_data.URLRequestQueue)
            #try:
            result = working_object.get()
            request_data.URLRequestQueue.complete=True
            output_queue.put(result)
            print("finished", request_data.URLRequestQueue.requestid)
            input_queue.task_done()
    except queue.Empty as e:
        print(e)
        print("Input Queue Processed")
    print("Queue Processed!")

def queued_object_to_session(oqueue, session, batch_size=0):
    """Reads objects(that must have a to_dataclass method) from named queue, 
    converts them to the appropriate dataclass, and then adds that to the 
    session. This should result in the queued item being saved to the database."""
    i=0
    try:
        print("Starting process")
        print(f"Queue-size {oqueue.qsize()}")
        while i < batch_size :
            i=i+1
            queued_object = oqueue.get()
            #print(f"Starting with {str(queued_object)}")
            dataclass_object = queued_object.to_dataclass()
            session.add(dataclass_object)
            oqueue.task_done()
            print(f"Finished {str(queued_object)}")
    except queue.Empty as e:
        print(e)
    
    print("Queue Processed!")


def TriggerFetchProcess(config, DB, maxsize=50):
    url_request_queue=queue.Queue(maxsize=maxsize)
    get_result_queue=queue.Queue(maxsize=maxsize)
    update_status_queue=queue.Queue(maxsize=maxsize)

    # Pull incomplete requests in priority order
    with Session(DB.engine) as session:
        pending_requests_data = session.execute(sqltext("select * from url_request_queue where complete != true order by submittedts"))
        pending_requests_objects = session.execute(select(dbadmin.URLRequestQueue).where(dbadmin.URLRequestQueue.complete!=True).order_by(dbadmin.URLRequestQueue.submittedts)).fetchall()
        batch_len = min(maxsize, len(pending_requests_objects))
        process_requests_thread = threading.Thread(target=unpack_and_get_result, args=(config, url_request_queue, get_result_queue, batch_len))
        save_results_thread = threading.Thread(target=queued_object_to_session, args=(get_result_queue, session, batch_len))
        


        for o in pending_requests_objects[0:batch_len]:
            if not url_request_queue.full():
                url_request_queue.put(o)
                
        process_requests_thread.start()
        save_results_thread.start()
        
        process_requests_thread.join()
        save_results_thread.join()
        
        
        session.commit()
    return url_request_queue, get_result_queue, update_status_queue




# Save the results to the database
with Session(DB.engine) as session:
    # Run the data-fetch from the request - note this is within the session
    result = url_request.get()
    obj = result.to_dataclass()
    session.add(obj)
    session.commit()