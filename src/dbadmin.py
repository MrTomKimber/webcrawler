"""Proprietary database management code to support webcrawler queueing functions and data storage"""

import sqlite3
import os, sys
from sqlalchemy.orm import DeclarativeBase
from typing import Optional
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
import datetime
from sqlalchemy import create_engine, Index
import pandas as pd

class DataStore(object):
    def __init__(self, configuration):
        self.dblocation=configuration.server.get('dblocation')
        # Test if the dblocation exists already, and update the path 
        self.dblocation=os.path.abspath(self.dblocation)
        if os.path.isfile(self.dblocation):
            #We're starting with a pre-created database - set flag to skip any creation routines
            new_db_start = True
        else:
            new_db_start = False
        self.engine = create_engine(f"sqlite:///{self.dblocation}", echo=False, pool_size=20)
        Base.metadata.create_all(self.engine)

    def sql_query(self, query):
        with sqlite3.connect(self.dblocation) as connection:
            cursor = connection.cursor()
            results = cursor.execute(query)
            if results.description is not None:
                columns = [c[0] for c in results.description]
                resultlist = results.fetchall()
                return resultlist, columns
            return results
        
    def sql_to_dataframe(self, query):
        with sqlite3.connect(self.dblocation) as connection:
            cursor = connection.cursor()
            results = cursor.execute(query)
            if results.description is not None:
                columns = [c[0] for c in results.description]
                df = pd.DataFrame(results, columns=columns)
                cursor.close()
                return df
            else:
                return None


class Base(DeclarativeBase):
    pass

class URLRequestQueueData(Base):
    """Class for submitting a URL request."""#
    __tablename__ = "url_request_queue"
    __table_args__ = (Index('url_request_queue_url_ix', "url"), )
    requestid : Mapped[str] = mapped_column(primary_key=True)
    url : Mapped[str]
    baseurl: Mapped[str]
    context : Mapped[str]
    submittedts: Mapped[datetime.datetime]
    expirets: Mapped[Optional[datetime.datetime]] = mapped_column(nullable=True)
    gotdata: Mapped[bool]
    gotlinks: Mapped[bool]
    closed: Mapped[bool]
    linkdepth: Mapped[int]
    maxdepth: Mapped[int]
    parent_requestid : Mapped[str] = mapped_column(nullable=True)

class URLRequestResultData(Base):
    """Class for capturing the response from a URL request."""
    __tablename__ = "url_request_result"
    __table_args__ = (Index('url_request_result_url_ix', "url"), )
    requestid : Mapped[str] = mapped_column(primary_key=True)
    url : Mapped[str]
    baseurl: Mapped[str]
    fetchts : Mapped[datetime.datetime]
    status : Mapped[str]
    content_type : Mapped[str]
    content_length : Mapped[int]
    content_bytes : Mapped[bytes]
    content_encoding : Mapped[str] = mapped_column(nullable=True)
    meta_class : Mapped[str] = mapped_column(nullable=True)
    meta_encoding : Mapped[str] = mapped_column(nullable=True)

class URLLinkConnectionData(Base):
    """Class for capturing link structure"""
    __tablename__ = "url_link_connection"
    __table_args__ = (Index('url_link_connection_url_ix', "tourl"), )
    linkid : Mapped[str] = mapped_column(primary_key=True)
    requestid : Mapped[str]
    fromurl: Mapped[str]
    tourl: Mapped[str]
    followed : Mapped[bool]
    donotfollow: Mapped[bool]


