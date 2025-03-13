import os
import json
import time
import httpx
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode
import re
from bs4 import BeautifulSoup
from datetime import datetime

from backend.utils.cache import get_cache, set_cache
from backend.utils.logging import setup_logger
from backend.config import settings
from backend.models.model_loader import model_loader

logger = setup_logger("web_agent")

class WebSearchAgent:
    """
    Agent for conducting web searches to supplement LLM knowledge with real-time information.
    Features:
    - Multiple search providers (fallback options)
    - Result caching
    - Rate limiting
    - Content filtering
    - Source attribution
    """
    
    def __init__(self):
        self.search_providers = {
            "serpapi": self._search_serpapi,
            "searchapi": self._search_searchapi,
            "duckduckgo": self._search_duckduckgo, 
            "custom": self._custom_search
        }
        self.default_provider = settings.DEFAULT_SEARCH_PROVIDER
        self.cache_ttl = settings.SEARCH_CACHE_TTL
        self.max_search_results = settings.MAX_SEARCH_RESULTS
        
        # Rate limiting
        self.last_search_time = 0
        self.min_search_interval = settings.MIN_SEARCH_INTERVAL
        
        # API keys
        self.serpapi_key = settings.SERPAPI_KEY
        self.searchapi_key = settings.SEARCHAPI_KEY
    
    async def search(
        self, 
        query: str, 
        provider: Optional[str] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Search the web for real-time information
        
        Args:
            query: Search query
            provider: Search provider to use (defaults to configured default)
            use_cache: Whether to use cached results
            
        Returns:
            Dict containing search results and metadata
        """
        provider = provider or self.default_provider
        
        # Check if provider is valid
        if provider not in self.search_providers:
            logger.error(f"Invalid search provider: {provider}")
            provider = self.default_provider
        
        # Apply rate limiting
        current_time = time.time()
        time_since_last_search = current_time - self.last_search_time
        
        if time_since_last_search < self.min_search_interval:
            sleep_time = self.min_search_interval - time_since_last_search
            logger.info(f"Rate limiting: waiting {sleep_time:.2f} seconds before search")
            time.sleep(sleep_time)
        
        # Check cache if enabled
        if use_cache:
            cache_key = f"search:{provider}:{query}"
            cached_results = get_cache(cache_key)
            
            if cached_results:
                logger.info(f"Using cached search results for query: {query}")
                return cached_results
        
        # Update last search time for rate limiting
        self.last_search_time = time.time()
        
        # Conduct search using selected provider
        search_function = self.search_providers[provider]
        
        try:
            logger.info(f"Searching {provider} for: {query}")
            results = await search_function(query)
            
            # Cache results if enabled
            if use_cache:
                cache_key = f"search:{provider}:{query}"
                set_cache(cache_key, results, expiry=self.cache_ttl)
            
            return results
            
        except Exception as e:
            logger.error(f"Search error with {provider}: {str(e)}")
            
            # Try fallback providers if primary fails
            if provider != self.default_provider:
                logger.info(f"Falling back to default provider: {self.default_provider}")
                return await self.search(query, provider=self.default_provider, use_cache=use_cache)
            
            # If all providers fail, return empty results
            return {
                "query": query,
                "results": [],
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def _search_serpapi(self, query: str) -> Dict[str, Any]:
        """
        Search using SerpAPI
        
        Args:
            query: Search query
            
        Returns:
            Dict containing search results
        """
        if not self.serpapi_key:
            raise ValueError("SerpAPI key not configured")
        
        params = {
            "q": query,
            "api_key": self.serpapi_key,
            "engine": "google",
            "num": self.max_search_results
        }
        
        url = f"https://serpapi.com/search?{urlencode(params)}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()
        
        # Format results
        formatted_results = []
        
        # Parse organic results
        for result in data.get("organic_results", [])[:self.max_search_results]:
            formatted_results.append({
                "title": result.get("title", ""),
                "link": result.get("link", ""),
                "snippet": result.get("snippet", ""),
                "source": "serpapi"
            })
        
        return {
            "query": query,
            "results": formatted_results,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def _search_searchapi(self, query: str) -> Dict[str, Any]:
        """
        Search using SearchAPI
        
        Args:
            query: Search query
            
        Returns:
            Dict containing search results
        """
        if not self.searchapi_key:
            raise ValueError("SearchAPI key not configured")
        
        params = {
            "q": query,
            "api_key": self.searchapi_key,
            "engine": "google",
            "num": self.max_search_results
        }
        
        url = f"https://www.searchapi.io/api/v1/search?{urlencode(params)}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()
        
        # Format results
        formatted_results = []
        
        # Parse organic results
        for result in data.get("organic_results", [])[:self.max_search_results]:
            formatted_results.append({
                "title": result.get("title", ""),
                "link": result.get("link", ""),
                "snippet": result.get("snippet", ""),
                "source": "searchapi"
            })
        
        return {
            "query": query,
            "results": formatted_results,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def _search_duckduckgo(self, query: str) -> Dict[str, Any]:
        """
        Search using DuckDuckGo (no API key required)
        
        Args:
            query: Search query
            
        Returns:
            Dict containing search results
        """
        # DuckDuckGo lite for simpler parsing
        url = f"https://lite.duckduckgo.com/lite/?{urlencode({'q': query})}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
        
        # Parse HTML results
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        
        # Extract results from DuckDuckGo Lite HTML
        for result in soup.select(".result-link")[:self.max_search_results]:
            title_elem = result.find_next("a")
            snippet_elem = result.find_next("tr").find_next("tr").find("td")
            
            if title_elem and title_elem.text.strip():
                result_url = title_elem.get("href", "")
                
                # Extract actual URL from DuckDuckGo redirect
                if result_url.startswith("/lite"):
                    params = result_url.split("?")[-1]
                    for param in params.split("&"):
                        if param.startswith("uddg="):
                            result_url = param.split("=")[-1]
                            break
                
                results.append({
                    "title": title_elem.text.strip(),
                    "link": result_url,
                    "snippet": snippet_elem.text.strip() if snippet_elem else "",
                    "source": "duckduckgo"
                })
        
        return {
            "query": query,
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def _custom_search(self, query: str) -> Dict[str, Any]:
        """
        Custom search implementation using direct HTTP requests to search engines
        This is a fallback option if no API keys are available
        
        Args:
            query: Search query
            
        Returns:
            Dict containing search results
        """
        # This is a simplified implementation
        # For production, a more robust approach would be needed
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        url = f"https://www.google.com/search?{urlencode({'q': query})}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
        
        # Parse HTML results
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        
        # Extract results from Google HTML
        for result in soup.select(".g")[:self.max_search_results]:
            title_elem = result.select_one("h3")
            link_elem = result.select_one("a")
            snippet_elem = result.select_one(".VwiC3b")
            
            if title_elem and link_elem:
                results.append({
                    "title": title_elem.text.strip(),
                    "link": link_elem.get("href", ""),
                    "snippet": snippet_elem.text.strip() if snippet_elem else "",
                    "source": "custom"
                })
        
        return {
            "query": query,
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def fetch_content(self, url: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Fetch and extract content from a URL
        
        Args:
            url: URL to fetch
            use_cache: Whether to use cached content
            
        Returns:
            Dict containing extracted content
        """
        # Check cache if enabled
        if use_cache:
            cache_key = f"content:{url}"
            cached_content = get_cache(cache_key)
            
            if cached_content:
                logger.info(f"Using cached content for URL: {url}")
                return cached_content
        
        try:
            logger.info(f"Fetching content from URL: {url}")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=30.0)
                response.raise_for_status()
            
            # Extract content using Beautiful Soup
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.extract()
            
            # Extract title
            title = soup.title.text.strip() if soup.title else ""
            
            # Extract main content (implementation depends on site structure)
            # This is a simple implementation that extracts paragraphs
            paragraphs = [p.text.strip() for p in soup.find_all("p") if p.text.strip()]
            content = "\n\n".join(paragraphs)
            
            # Extract metadata
            meta_description = ""
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                meta_description = meta_desc.get("content", "")
            
            result = {
                "url": url,
                "title": title,
                "meta_description": meta_description,
                "content": content,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Cache result if enabled
            if use_cache:
                cache_key = f"content:{url}"
                set_cache(cache_key, result, expiry=self.cache_ttl)
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching content from {url}: {str(e)}")
            
            return {
                "url": url,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def search_and_summarize(
        self, 
        query: str,
        max_results: int = 3,
        provider: Optional[str] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Search for information and summarize the results
        
        Args:
            query: Search query
            max_results: Maximum number of results to summarize
            provider: Search provider to use
            use_cache: Whether to use cached results
            
        Returns:
            Dict containing search results and summary
        """
        # Perform the search
        search_results = await self.search(query, provider, use_cache)
        
        if not search_results.get("results"):
            return {
                "query": query,
                "summary": "No search results found.",
                "results": [],
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Limit results
        results = search_results["results"][:max_results]
        
        # Fetch content for each result
        content_results = []
        
        for result in results:
            content = await self.fetch_content(result["link"], use_cache)
            if "error" not in content:
                content_results.append({
                    "title": result["title"],
                    "link": result["link"],
                    "snippet": result["snippet"],
                    "content": content["content"][:2000]  # Limit content length
                })
        
        # Generate summary using LLM
        summary = await self._generate_summary(query, content_results)
        
        return {
            "query": query,
            "summary": summary,
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def _generate_summary(self, query: str, content_results: List[Dict[str, Any]]) -> str:
        """
        Generate a summary of search results using the LLM
        
        Args:
            query: Original search query
            content_results: List of content results
            
        Returns:
            Generated summary
        """
        # Format prompt for the LLM
        prompt = [
            {
                "role": "system",
                "content": "You are a helpful assistant that summarizes web search results. "
                          "Provide a concise summary of the information found, including relevant "
                          "facts and details. Cite your sources using [Source 1], [Source 2], etc."
            },
            {
                "role": "user",
                "content": f"I need information about: {query}\n\n"
                          f"Here are the search results:\n\n"
            }
        ]
        
        # Add content from each result
        for i, result in enumerate(content_results, 1):
            source_info = (
                f"[Source {i}] {result['title']}\n"
                f"URL: {result['link']}\n"
                f"Snippet: {result['snippet']}\n\n"
                f"Content:\n{result['content'][:1000]}...\n\n"
            )
            
            prompt[1]["content"] += source_info
        
        prompt[1]["content"] += (
            "Please provide a comprehensive summary of this information, "
            "citing sources as [Source 1], [Source 2], etc. Include all relevant "
            "facts and details from the search results."
        )
        
        # Generate summary
        try:
            summary = model_loader.generate_response(
                prompt,
                max_length=1024,
                temperature=0.3  # Lower temperature for more factual responses
            )
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            
            # Fallback to a simple concatenation of snippets
            snippets = [f"[Source {i+1}] {r['snippet']}" for i, r in enumerate(content_results)]
            return "\n\n".join(snippets)

# Initialize the web search agent
web_search_agent = WebSearchAgent()