
from src.config import Configuration
from src.fetch import URLRequest
import src.dbadmin as dbadmin
from sqlalchemy.orm import Session

# Read Config
config = Configuration("../config/config.json")

# Setup Database
DB = dbadmin.DataStore(config)

# Create Request
url_request = URLRequest.from_url(config, "https://www.bbc.co.uk/news")

# Save request to database
with Session(DB.engine) as session:
    obj = url_request.to_dataclass()
    session.add(obj)
    session.commit()



# Save the results to the database
with Session(DB.engine) as session:
    # Run the data-fetch from the request - note this is within the session
    result = url_request.get()
    obj = result.to_dataclass()
    session.add(obj)
    session.commit()