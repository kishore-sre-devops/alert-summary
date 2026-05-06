from sqlalchemy import Table, Column, Integer, String, DateTime, MetaData
import datetime


metadata = MetaData()


users_table = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String, unique=True),
    Column("password", String),
    Column("full_name", String),
    Column("phone", String),
    Column("role", String),
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow),
)
