import math, re
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

import logging
logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://castbox.fm/app/castbox/player/id2574365?v=8.22.11&autoplay=0
    # https://everest.castbox.fm/data/channel/v3?cid=2574365&raw=1&web=1&m=20230221&n=aa54f633983a06dcbbb65881473c73c5&r=1
    # n is some encoding of 'cid=2574365&r=1&raw=1&web=1evst20230221'
    return None
