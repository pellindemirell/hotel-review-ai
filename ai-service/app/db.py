from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from .config import DATABASE_URL

# Create the database engine
# pool-pre-ping kullan ufak pingle database uyku moduna geçmiş mi kontrol et
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# scoped session fastapı asekntron çalışır databaseden istekler çekilirken karmaşa önler
db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

# Base class for models
Base = declarative_base()
Base.query = db_session.query_property()

def get_db():
    db = db_session()
    try:
        yield db
    finally:
        db.close()
