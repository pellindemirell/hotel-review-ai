from sqlalchemy.orm import Session
from ..models import ReviewCategory

def classify_category(comment: str, db: Session) -> tuple[str | None, str | None]:
    """
    Classifies the review comment into a category from the database based on keyword matching.
    Returns a tuple of (category_id, category_name) or (None, None).
    """
    if not comment:
        return None, None
        
    comment_lower = comment.lower()
    
    try:
        # Fetch all active review categories from the database
        categories = db.query(ReviewCategory).filter(ReviewCategory.is_active == True).all()
    except Exception:
        # Fallback if database query fails
        categories = []
        
    best_category_id = None
    best_category_name = None
    max_matches = 0
    
    for category in categories:
        # keywords can be a list stored as JSON
        keywords = category.keywords or []
        if isinstance(keywords, str):
            # Safe parsing if it was somehow stored as string
            import json
            try:
                keywords = json.loads(keywords)
            except Exception:
                keywords = []
                
        matches = 0
        for kw in keywords:
            if kw.lower() in comment_lower:
                # Add weight or simple count
                matches += 1
                
        if matches > max_matches:
            max_matches = matches
            best_category_id = str(category.id)
            best_category_name = category.name
            
    return best_category_id, best_category_name
