from urllib.parse import parse_qs, urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # Redirect to megaphone.fm
    # https://player.spokenlayer.net/shows/wired-security?e=AIRWV1900421380
    split_url = urlsplit(url)
    params = parse_qs(split_url.query)
    if params.get('e'):
        return utils.get_content('https://playlist.megaphone.fm/?sharing=false&e=' + params['e'][0], args, save_debug)
    logger.warning('unhandled url ')
    return None
