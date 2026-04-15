# config.py
import os
from dotenv import load_dotenv
from mediacloud.api import SearchApi, DirectoryApi

load_dotenv()

API_KEY = os.getenv('MEDIACLOUD_API_KEY')
if not API_KEY:
    raise ValueError("MEDIACLOUD_API_KEY not set in .env file")

search_api = SearchApi(API_KEY)
directory_api = DirectoryApi(API_KEY)
