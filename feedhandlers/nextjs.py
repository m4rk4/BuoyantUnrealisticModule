import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

from feedhandlers import rss
import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "next-router-state-tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22(pages)%22%2C%7B%22children%22%3A%5B%5B%22locale%22%2C%22en%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22latest%22%2C%7B%22children%22%3A%5B%22article%22%2C%7B%22children%22%3A%5B%5B%22slug%22%2C%22monday-morning-debrief-why-norriss-maiden-win-wasnt-just-thanks-to-a-lucky.7wNMsePLBnbOnq5G7jDn2t%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Fen%2Flatest%2Farticle%2Fmonday-morning-debrief-why-norriss-maiden-win-wasnt-just-thanks-to-a-lucky.7wNMsePLBnbOnq5G7jDn2t%22%2C%22refresh%22%5D%7D%5D%7D%5D%7D%5D%7D%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D",
        "next-url": "/en/latest/article/monday-morning-debrief-why-norriss-maiden-win-wasnt-just-thanks-to-a-lucky.7wNMsePLBnbOnq5G7jDn2t",
        "priority": "u=1, i",
        "rsc": "1",
        "sec-ch-ua": "\"Chromium\";v=\"124\", \"Microsoft Edge\";v=\"124\", \"Not-A.Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }
    next_data = utils.get_url_html(url, headers=headers)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/next.txt')
