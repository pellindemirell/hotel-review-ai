def analyze_sentiment(comment: str, rating: int) -> tuple[int, float]:
    """
    Analyzes review comment sentiment and rating, returning a tuple of (sentiment_enum, score).
    Sentiment enum values:
    0 = Positive
    1 = Negative
    2 = Neutral
    """
    if not comment:
        return 2, 0.0

    # Base score on rating (1 to 5)
    # 5 -> 0.8, 4 -> 0.4, 3 -> 0.0, 2 -> -0.4, 1 -> -0.8
    base_score = (rating - 3) * 0.4
    
    # Sentiment keyword weights
    pos_keywords = [
        "güzel", "iyi", "harika", "temiz", "lezzetli", "memnun", "hızlı", 
        "tavsiye", "güler yüz", "mükemmel", "harikaydı", "sevdim", "beğendim",
        "clean", "good", "great", "friendly", "delicious", "perfect", "nice", "excellent"
    ]
    neg_keywords = [
        "kötü", "kirli", "yavaş", "rezalet", "berbat", "pahalı", "gürültü", 
        "eski", "bozuk", "şikayet", "memnun kalmadım", "beğenmedim", "soğuk",
        "dirty", "bad", "slow", "expensive", "noise", "broken", "worst", "terrible", "poor"
    ]
    
    comment_lower = comment.lower()
    pos_count = sum(1 for kw in pos_keywords if kw in comment_lower)
    neg_count = sum(1 for kw in neg_keywords if kw in comment_lower)
    
    # Adjust score based on keyword counts
    score_adjustment = (pos_count - neg_count) * 0.1
    final_score = base_score + score_adjustment
    
    # Bound the score between -1.0 and 1.0
    final_score = max(-1.0, min(1.0, final_score))
    
    # Categorize based on final score
    if final_score > 0.15:
        sentiment = 0  # Positive
    elif final_score < -0.15:
        sentiment = 1  # Negative
    else:
        sentiment = 2  # Neutral
        
    return sentiment, round(final_score, 2)
