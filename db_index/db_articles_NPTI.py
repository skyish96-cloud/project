from logger import Logger
from sqlalchemy import Column, String, DateTime
from database import Base
from datetime import datetime

logger = Logger().get_logger(__name__)



class ArticlesNPTI(Base):
    __tablename__ = "articles_NPTI"  # ERD에 명시된 테이블 이름

    news_id = Column(String, primary_key=True, index=True)
    NPTI_code = Column(String, nullable=False)
    length_type = Column(String)
    article_type = Column(String)
    info_type = Column(String)
    view_type = Column(String)
    updated_at = Column(DateTime, default=datetime.now)