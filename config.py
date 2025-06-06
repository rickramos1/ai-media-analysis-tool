# config.py
from mediacloud.api import SearchApi, DirectoryApi

API_KEY = 'your_api_key_here'  # Replace with real key
search_api = SearchApi(API_KEY)
directory_api = DirectoryApi(API_KEY)
