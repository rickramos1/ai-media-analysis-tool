# config.py
from mediacloud.api import SearchApi, DirectoryApi

API_KEY = 'REDACTED_MEDIACLOUD_KEY_2'  # Replace with real key
search_api = SearchApi(API_KEY)
directory_api = DirectoryApi(API_KEY)
