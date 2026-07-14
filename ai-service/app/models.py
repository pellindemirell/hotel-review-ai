from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from .db import Base

class BaseModel(Base):
    __abstract__ = True
    
    id = Column("Id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column("CreatedAt", DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column("UpdatedAt", DateTime, onupdate=datetime.utcnow, nullable=True)
    is_active = Column("IsActive", Boolean, default=True, nullable=False)

class Department(BaseModel):
    __tablename__ = "Departments"
    
    name = Column("Name", String, nullable=False)
    description = Column("Description", String, nullable=True)
    
    users = relationship("User", back_populates="department")
    categories = relationship("ReviewCategory", back_populates="department")
    action_items = relationship("ActionItem", back_populates="department")

class User(BaseModel):
    __tablename__ = "Users"
    
    fullname = Column("FullName", String, nullable=False)
    email = Column("Email", String, nullable=False)
    password_hash = Column("PasswordHash", String, nullable=False)
    role = Column("Role", String, nullable=False)
    department_id = Column("DepartmentId", UUID(as_uuid=True), ForeignKey("Departments.Id"), nullable=True)
    
    department = relationship("Department", back_populates="users")
    action_items = relationship("ActionItem", back_populates="assigned_user")

class Review(BaseModel):
    __tablename__ = "Reviews"
    
    source = Column("Source", Integer, nullable=False)  # Map to C# Enum ReviewSource
    guest_name = Column("GuestName", String, nullable=False)
    comment = Column("Comment", Text, nullable=False)
    language = Column("Language", String, nullable=False)
    rating = Column("Rating", Integer, nullable=False)
    review_date = Column("ReviewDate", DateTime, nullable=False)
    created_by = Column("CreatedBy", UUID(as_uuid=True), nullable=True)
    
    analysis = relationship("ReviewAnalysis", back_populates="review", uselist=False)
    attachments = relationship("ReviewAttachment", back_populates="review")
    action_items = relationship("ActionItem", back_populates="review")

class ReviewCategory(BaseModel):
    __tablename__ = "ReviewCategories"
    
    name = Column("Name", String, nullable=False)
    keywords = Column("Keywords", JSON, nullable=False)
    department_id = Column("DepartmentId", UUID(as_uuid=True), ForeignKey("Departments.Id"), nullable=False)
    
    department = relationship("Department", back_populates="categories")
    analyses = relationship("ReviewAnalysis", back_populates="category")

class ReviewAnalysis(BaseModel):
    __tablename__ = "ReviewAnalyses"
    
    review_id = Column("ReviewId", UUID(as_uuid=True), ForeignKey("Reviews.Id"), nullable=False)
    sentiment = Column("Sentiment", Integer, nullable=False)  # Map to C# Enum Sentiment
    sentiment_score = Column("SentimentScore", Float, nullable=False)
    category_id = Column("CategoryId", UUID(as_uuid=True), ForeignKey("ReviewCategories.Id"), nullable=True)
    keywords = Column("Keywords", JSON, nullable=False)
    summary = Column("Summary", Text, nullable=True)
    suggestion = Column("Suggestion", Text, nullable=True)
    confidence = Column("Confidence", Float, nullable=False)
    
    review = relationship("Review", back_populates="analysis")
    category = relationship("ReviewCategory", back_populates="analyses")

class ReviewAttachment(BaseModel):
    __tablename__ = "ReviewAttachments"
    
    review_id = Column("ReviewId", UUID(as_uuid=True), ForeignKey("Reviews.Id"), nullable=False)
    file_url = Column("FileUrl", String, nullable=False)
    file_type = Column("FileType", String, nullable=False)
    ocr_text = Column("OcrText", Text, nullable=True)
    
    review = relationship("Review", back_populates="attachments")

class ActionItem(BaseModel):
    __tablename__ = "ActionItems"
    
    review_id = Column("ReviewId", UUID(as_uuid=True), ForeignKey("Reviews.Id"), nullable=False)
    department_id = Column("DepartmentId", UUID(as_uuid=True), ForeignKey("Departments.Id"), nullable=False)
    assigned_to = Column("AssignedTo", UUID(as_uuid=True), ForeignKey("Users.Id"), nullable=True)
    title = Column("Title", String, nullable=False)
    status = Column("Status", Integer, nullable=False, default=0)  # Map to C# Enum ActionItemStatus
    due_date = Column("DueDate", DateTime, nullable=True)
    
    review = relationship("Review", back_populates="action_items")
    department = relationship("Department", back_populates="action_items")
    assigned_user = relationship("User", back_populates="action_items")

class AuditLog(BaseModel):
    __tablename__ = "AuditLogs"
    
    user_id = Column("UserId", UUID(as_uuid=True), nullable=False)
    action = Column("Action", String, nullable=False)
    entity_name = Column("EntityName", String, nullable=False)
    entity_id = Column("EntityId", UUID(as_uuid=True), nullable=False)
