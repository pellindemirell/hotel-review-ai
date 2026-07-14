import re
from collections import Counter

# Turkish & English common stop words
STOPWORDS = {
    # Turkish
    "ve", "veya", "ama", "fakat", "lakin", "ile", "bir", "bu", "o", "şu", "ki", "de", "da", 
    "ise", "için", "gibi", "en", "çok", "daha", "her", "hepsi", "hiç", "mi", "mı", "mu", "mü", 
    "şey", "herkes", "yine", "böyle", "şöyle", "şimdi", "kendi", "olarak", "olan", "tarafından",
    "biri", "ben", "sen", "biz", "siz", "onlar", "bunu", "onu", "buna", "ona", "orada", "burada",
    # English
    "the", "and", "or", "but", "a", "an", "of", "to", "in", "is", "it", "you", "that", "he", 
    "was", "for", "on", "are", "as", "with", "his", "they", "i", "at", "be", "this", "have", 
    "from", "at", "by", "an", "my", "we", "your", "our", "their", "will", "would", "can", "could"
}

def extract_keywords(comment: str, max_keywords: int = 5) -> list[str]:
    """
    Extracts key/frequent words from the comment text, excluding common stopwords.
    """
    if not comment:
        return []
        
    # Clean the text: remove punctuation and split by whitespace
    words = re.findall(r'\b\w+\b', comment.lower())
    
    # Filter stopwords and short tokens
    filtered_words = [
        word for word in words 
        if word not in STOPWORDS and len(word) > 2 and not word.isdigit()
    ]
    
    # Get the most common words
    word_counts = Counter(filtered_words)
    top_words = [word for word, count in word_counts.most_common(max_keywords)]
    
    return top_words
