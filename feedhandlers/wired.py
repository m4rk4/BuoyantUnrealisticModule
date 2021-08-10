import re

from feedhandlers import cne, rss, wp_posts

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
  if re.search(r'wired\.com/\d+/\d+/geeks-guide', url):
    return wp_posts.get_content(url, args, save_debug)
  return cne.get_content(url, args, save_debug)

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)