"""Scraping modules for the Hi-Engineer Heroku app.

All scraping is done with direct HTTP requests (cURL-style via the `requests`
library) -- no Firecrawl, no Apify actors. Each module is a plain script that
fetches a URL and returns structured Python data.
"""
