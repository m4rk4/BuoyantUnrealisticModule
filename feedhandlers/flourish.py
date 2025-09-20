from bs4 import BeautifulSoup
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
        if 'embed' in paths:
            paths.remove('embed')
        item = {}
        item['id'] = '/'.join(paths)
        item['url'] = 'https://public.flourish.studio/' + item['id']
        item['image'] = item['url'] + '/thumbnail'
        page_html = utils.get_url_html(item['url'])
        if page_html:
            soup = BeautifulSoup(page_html, 'lxml')
            el = soup.find('meta', attrs={"property": "og:title"})
            if el:
                item['title'] = el['content']
            else:
                item['title'] = soup.title.get_text()
            caption = item['title']
            # el = soup.find('meta', attrs={"property": "og:image"})
            # if el:
            #     item['image'] = el['content']
            el = soup.find('meta', attrs={"property": "og:description"})
            if el:
                item['summary'] = el['content']
                caption += ' | ' + item['summary']
            item['content_html'] = utils.add_image(item['image'], caption, link=item['url'] + '/embed')
        else:
            # if 'visualisation' in paths:
            #     item['image'] = '{}/screenshot?url={}&locator=%23fl-layout-wrapper-outer&networkidle=true'.format(config.server, quote_plus(item['url'] + '/embed'))
            # else:
            #     item['image'] = '{}/screenshot?url={}&locator=body%23story&networkidle=true'.format(config.server, quote_plus(item['url'] + '/embed'))
            caption = '<a href="{}" target="_blank">View on Flourish</a>'.format(item['url'])
            item['content_html'] = utils.add_image(item['image'], caption, link=item['url'])
    else:
        logger.warning('unhandled url ' + url)
        item = None
    return item
