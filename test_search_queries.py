#!/usr/bin/env python3
"""
Test different YouTube search approaches to find Tamil movies.
"""

from ddgs import DDGS

def test_ddgs_search(query: str):
    """Test DuckDuckGo search for a query."""
    print(f"\nSearching: {query}")
    print("=" * 60)
    
    ddgs = DDGS(timeout=20)
    try:
        results = ddgs.text(
            query,
            region="in-en",
            safesearch="moderate",
            max_results=3,
        )
        
        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result.get('title', 'N/A')}")
            print(f"   URL: {result.get('href', 'N/A')}")
            print(f"   Body: {result.get('body', 'N/A')[:100]}...")
            
    except Exception as e:
        print(f"Error: {e}")

# Test different search queries
queries = [
    "tamil movie youtube",
    "tamil full movie subtitle",
    "tamil cinema movie dialogue youtube",
    "site:youtube.com tamil movie",
    "youtube tamil cinema full movie",
    "tamil comedy movie youtube",
]

for query in queries:
    test_ddgs_search(query)
