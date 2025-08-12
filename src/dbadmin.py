"""Proprietary database management code to support webcrawler queueing functions and data storage"""

import sqlite3
import os, sys
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
import datetime
from sqlalchemy import create_engine

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
        self.engine = create_engine(f"sqlite:///{self.dblocation}", echo=True)
        Base.metadata.create_all(self.engine)

class Base(DeclarativeBase):
    pass

class URLRequestQueue(Base):
    """Class for submitting a URL request."""#
    __tablename__ = "url_request_queue"
    requestid : Mapped[str] = mapped_column(primary_key=True)
    url : Mapped[str]
    baseurl: Mapped[str]
    context : Mapped[str]
    submittedts: Mapped[datetime.datetime]
    complete: Mapped[bool]

class URLRequestResult(Base):
    """Class for capturing the response from a URL request."""
    __tablename__ = "url_request_result"
    requestid : Mapped[str] = mapped_column(primary_key=True)
    url : Mapped[str]
    baseurl: Mapped[str]
    context : Mapped[str]
    fetchts = Mapped[datetime.datetime]
    status = Mapped[str]

class URLLinkConnections(Base):
    """Class for capturing link structure"""
    __tablename__ = "url_link_connection"
    linkid : Mapped[str] = mapped_column(primary_key=True)
    frombase: Mapped[str]
    fromurl: Mapped[str]
    tobase: Mapped[str]
    tourl: Mapped[str]
    fetchts: Mapped[datetime.datetime]
    fetchcontext: Mapped[str]


