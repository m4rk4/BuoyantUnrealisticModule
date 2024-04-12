from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://flo.uri.sh/visualisation/16208627/embed
    # https://flo.uri.sh/story/2183334/embed
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if 'visualisation' in paths or 'story' in paths:
        if 'embed' not in paths:
            paths.append('embed')
        item = {}
        item['url'] = 'https://flo.uri.sh/{}'.format('/'.join(paths))
        if 'visualisation' in paths:
            item['_image'] = '{}/screenshot?url={}&locator=%23fl-layout-wrapper-outer'.format(config.server, quote_plus(item['url']))
        else:
            item['_image'] = '{}/screenshot?url={}&locator=body%23story'.format(config.server, quote_plus(item['url']))
        caption = '<a href="{}">View on Flourish</a>'.format(item['url'])
        item['content_html'] = utils.add_image(item['_image'], caption, link=item['url'])
    else:
        logger.warning('unhandled url ' + url)
        item = None
    return item
