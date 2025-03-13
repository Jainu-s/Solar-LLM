import os
import json
import logging
import traceback
from collections import Counter
from typing import Dict, Tuple, Any, List, Optional
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

from ..config import config

# Configure logging
logger = logging.getLogger(__name__)

# Download NLTK resources (with error handling)
try:
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)
except Exception as e:
    logger.warning(f"Warning: Failed to download NLTK resources: {e}")

def load_meta_index() -> Dict[str, Any]:
    """
    Load the meta index with error handling.
    
    Returns:
        Dict[str, Any]: The loaded meta index or an empty dict if loading fails
    """
    try:
        meta_index_path = config.META_INDEX_PATH
        
        if not os.path.exists(meta_index_path):
            # Try alternative locations
            alt_paths = [
                os.path.join(os.path.dirname(__file__), "../vector_db/meta_index.json"),
                "backend/vector_db/meta_index.json",
                "data/vector_db/meta_index.json"
            ]
            
            for path in alt_paths:
                if os.path.exists(path):
                    meta_index_path = path
                    break
            else:
                logger.warning(f"⚠️ Meta index file not found at {meta_index_path} or alternative locations")
                return {}
        
        with open(meta_index_path, 'r') as f:
            meta_index = json.load(f)
            logger.info(f"✅ Successfully loaded meta index with {len(meta_index)} databases")
            return meta_index
    except Exception as e:
        logger.error(f"❌ Error loading meta index: {e}")
        logger.error(traceback.format_exc())
        return {}  # Return empty dict on error

def get_collection_schema(meta_index: Dict[str, Any], db_name: str, collection_name: str) -> Dict[str, Any]:
    """
    Get the schema for a specific collection.
    
    Args:
        meta_index: The loaded meta index
        db_name: Database name
        collection_name: Collection name
        
    Returns:
        Dict[str, Any]: The collection schema or empty dict if not found
    """
    try:
        return meta_index.get(db_name, {}).get(collection_name, {})
    except Exception as e:
        logger.error(f"❌ Error getting collection schema: {e}")
        return {}

def extract_keywords(query: str) -> List[str]:
    """
    Extract keywords from a query, removing stopwords.
    
    Args:
        query: The user query
        
    Returns:
        List[str]: List of extracted keywords
    """
    try:
        # Get stop words
        stop_words = set(stopwords.words('english'))
        
        # Tokenize and filter out stopwords
        word_tokens = word_tokenize(query.lower())
        keywords = [word for word in word_tokens if word.isalnum() and word not in stop_words]
        
        logger.debug(f"Extracted keywords: {keywords}")
        return keywords
    except Exception as e:
        logger.error(f"❌ Error extracting keywords: {e}")
        # Fallback to simple word splitting
        return [word.lower() for word in query.split() if len(word) > 3]

def match_keywords_to_collections(query: str, meta_index: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Match query keywords to database collections.
    
    Args:
        query: The user query
        meta_index: The loaded meta index
        
    Returns:
        Tuple[Optional[str], Optional[str]]: Matched database and collection names or (None, None)
    """
    try:
        # Extract keywords from query
        keywords = extract_keywords(query)
        
        # Track matching scores for each collection
        collection_scores = Counter()
        
        # Iterate through databases and collections
        for db_name, db_info in meta_index.items():
            for collection_name, collection_info in db_info.items():
                # Get column examples
                column_examples = []
                for col_name, col_info in collection_info.get('columns', {}).items():
                    # Add column name
                    column_examples.append(col_name.lower())
                    
                    # Add column examples if available
                    examples = col_info.get('examples', [])
                    if isinstance(examples, list):
                        column_examples.extend([str(ex).lower() for ex in examples if ex])
                
                # Check if any keyword matches collection data
                for keyword in keywords:
                    if any(keyword.lower() in example.lower() if isinstance(example, str) else False 
                           for example in column_examples):
                        collection_scores[(db_name, collection_name)] += 1
        
        logger.debug(f"Collection scores: {collection_scores}")
        
        # Return the best match if any
        if collection_scores:
            best_match = collection_scores.most_common(1)[0][0]
            return best_match
        
        return None, None
    except Exception as e:
        logger.error(f"❌ Error matching keywords to collections: {e}")
        logger.error(traceback.format_exc())
        return None, None