import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1280):
    if 'media.thepopverse.com' in img_src:
        return 'https://www.thepopverse.com/_next/image?url=' + quote_plus(img_src) + '&w=' + str(width) + '&q=75'
    return img_src


def get_next_data(url, save_debug):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "cache-control": "no-cache",
        "next-router-state-tree": "%5B%22%22%2C%7B%22children%22%3A%5B%5B%22path%22%2C%22%22%2C%22oc%22%5D%2C%7B%22children%22%3A%5B%22__PAGE__%3F%7B%5C%22userLocation%5C%22%3A%5C%22US%5C%22%2C%5C%22device%5C%22%3A%5C%22desktop%5C%22%7D%22%2C%7B%7D%2C%22%2F%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D",
        "next-url": "/",
        "pragma": "no-cache",
        "priority": "i",
        "rsc": "1",
        "sec-ch-ua": "\"Chromium\";v=\"136\", \"Microsoft Edge\";v=\"136\", \"Not.A/Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }
    return utils.get_url_html(url, headers=headers)


def get_next_json(url, save_debug):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/page.html')
    page_soup = BeautifulSoup(page_html, 'lxml')
    next_data = ''
    for el in page_soup.find_all('script', string=re.compile(r'^self\.__next_f\.push')):
        i = el.string.find('[')
        j = el.string.rfind(']') + 1
        next_f = json.loads(el.string[i:j])
        if next_f[0] == 1:
            next_data += next_f[1]
    if save_debug:
        utils.write_file(next_data, './debug/next.txt')

    next_json = {}
    for m in re.findall(r'([0-9a-f]{1,2}):(HL|I|\[|\"|T[0-9a-f]+,|null)(.*?)(?=([0-9a-f]{1,2}):(HL|I|\[|\"|T[0-9a-f]+,|null)|$)', next_data, flags=re.S):
        if m[1] == '"':
            next_json[m[0]] = m[2][:-1]
        if m[1] == '[':
            next_json[m[0]] = json.loads('[' + m[2])
        elif m[1] == 'null':
            next_json[m[0]] = None
        elif m[2].startswith('{') or m[2].startswith('['):
            next_json[m[0]] = json.loads(m[2])
        else:
            next_json[m[0]] = m[2]
    return next_json


def get_content(url, args, site_json, save_debug=False):
    next_json = get_next_json(url, save_debug)
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/next.json')

    ld_json = None
    data_layer = None
    main_content = None
    for it in next_json['b']:
        if it[1] == 'script' and it[2] == 'schema-jsonld':
            key = it[3]['dangerouslySetInnerHTML']['__html'].lstrip('$L')
            ld_json = next_json[key]
        elif it[1] == 'article':
            key = it[3]['children'].lstrip('$L')
            for x in next_json[key]:
                if len(x) == 4 and 'mainContent' in x[3]:
                    main_content = x[3]['mainContent']
                    break
        elif it[3].get('dataLayer'):
            data_layer = json.loads(it[3]['dataLayer'])

    item = {}
    item['id'] = data_layer['Content']['Id']
    item['url'] = ld_json['url']
    item['title'] = ld_json['headline']

    dt = datetime.fromisoformat(ld_json['datePublished'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(ld_json['dateModified'])
    item['date_modified'] = dt.isoformat()

    item['author'] = {
        "name": ld_json['author']['name']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['tags'] = ld_json['keywords'].copy()
    item['image'] = ld_json['image'][0]
    item['summary'] = ld_json['description']

    item['content_html'] = ''
    for child in main_content[3]['children'][3]['children']:
        if isinstance(child, list):
            for it in child:
                if isinstance(it, list):
                    if it[1] == 'section':
                        if 'className' in it[3]:
                            if it[3]['className'].startswith('article_strapline'):
                                item['content_html'] += '<p><em>' + it[3]['children'][3]['children'] + '</em></p>'
                            elif it[3]['className'].startswith('article_headlineImage'):
                                item['content_html'] += utils.add_image(resize_image(it[3]['children'][3]['src']), it[3]['children'][3]['caption'])
                            elif it[3]['className'].startswith('article_content'):
                                for c in it[3]['children']:
                                    for x in c:
                                        if isinstance(x, list) and len(x) == 4:
                                            if 'html' in x[3]:
                                                if x[3]['html'].startswith('$'):
                                                    key = x[3]['html'].lstrip('$L')
                                                    item['content_html'] += next_json[key]
                                                else:
                                                    item['content_html'] += x[3]['html']
                                            elif 'src' in x[3]:
                                                item['content_html'] += utils.add_image(resize_image(x[3]['src']), x[3].get('caption'))
                                            elif 'adID' in x[3]:
                                                continue
                                            else:
                                                logger.warning('unhandled content child ' + str(x))
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
