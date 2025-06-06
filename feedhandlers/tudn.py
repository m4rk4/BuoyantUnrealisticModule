import curl_cffi, json, pytz, re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


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
    next_data = get_next_data(url, save_debug)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/next.txt')

    next_json = {}
    x = 0
    m = re.search(r'^\s*([0-9a-f]{1,2}):(.*)', next_data)
    while m:
        key = m.group(1)
        x += len(key) + 1
        val = m.group(2)
        if val.startswith('I'):
            val = val[1:]
            x += 1
        elif val.startswith('HL'):
            val = val[2:]
            x += 2
        elif val.startswith('T'):
            t = re.search(r'T([0-9a-f]+),(.*)', val)
            if t:
                n = int(t.group(1), 16)
                x += len(t.group(1)) + 2
                val = next_data[x:x + n]
                # print(n, val)
                # if not val.isascii():
                #     i = n
                #     n = 0
                #     for c in val:
                #         n += 1
                #         i -= len(c.encode('utf-8'))
                #         if i == 0:
                #             break
                #     val = next_data[x:x + n]
                #     print(n, val)
        if val:
            # print(key, val)
            if (val.startswith('{') and val.endswith('}')) or (val.startswith('[') and val.endswith(']')):
                next_json[key] = json.loads(val)
            elif val.startswith('"') and val.endswith('"'):
                next_json[key] = val[1:-1]
            else:
                next_json[key] = val
            x += len(val)
            if next_data[x:].startswith('\n'):
                x += 1
            m = re.search(r'^\s*([0-9a-f]{1,2}):(.*)', next_data[x:])
        else:
            break
    return next_json


def get_content(url, args, site_json, save_debug=False):
    next_json = get_next_json(url + '?_rsc=' + site_json['rsc'], save_debug)
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/next.json')

    article = None
    for it in next_json['5'][1]:
        if isinstance(it, list) and it[0] == '$' and it[1] == 'article':
            article = it
            break

    if not article:
        logger.warning('unable to find article in ' + url)
    
    ld_json = None
    if next_json.get('18') and next_json['18'].get('@type'):
        ld_json = next_json['18']
    elif article:
        for child in article[3]['children']:
            if isinstance(child[0], str) and child[0] == '$' and child[1] == 'script' and child[3].get('type') and child[3]['type'] == 'application/ld+json':
                key = child[3]['dangerouslySetInnerHTML']['__html'][1:]
                ld_json = next_json[key]
                break

    item = {}
    item['id'] = urlsplit(ld_json['url']).path
    item['url'] = ld_json['url']
    item['title'] = ld_json['headline'].encode('latin-1', errors='ignore').decode('utf-8', errors='ignore')

    dt = datetime.fromisoformat(ld_json['datePublished']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if ld_json.get('dateModified'):
        dt = datetime.fromisoformat(ld_json['dateModified']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['authors'] = []

    item['tags'] = []
    if ld_json.get('articleSection'):
        item['tags'].append(ld_json['articleSection'])
    if ld_json.get('keywords'):
        item['tags'] += ld_json['keywords'].encode('latin-1', errors='ignore').decode('utf-8', errors='ignore').split(',')

    if ld_json.get('image'):
        item['image'] = ld_json['image'][0]

    item['content_html'] = ''
    if ld_json.get('abstract'):
        item['summary'] = ld_json['abstract'].encode('latin-1', errors='ignore').decode('utf-8', errors='ignore')
        item['content_html'] += '<p><em>' + item['summary'] + '</em></p>'

    def process_child(child):
        nonlocal item
        # print(child)
        if child[1] == 'script':
            return
        if child[2]:
            if child[2].startswith('body-content') and child[3].get('dangerouslySetInnerHTML'):
                item['content_html'] += child[3]['dangerouslySetInnerHTML']['__html']
            elif child[2].startswith('liveblog-author') and child[3].get('children'):
                item['authors'] = [{"name": x.encode('latin-1', errors='ignore').decode('utf-8', errors='ignore')} for x in child[3]['children'] if x != '.']
                return
        if child[3].get('type'):
            if child[3]['type'] == 'video':
                split_url = urlsplit(child[3]['playlist'][0]['contentUrl'])
                video_src = 'https://' + child[3]['playlist'][0]['tvssDomain'] + '/api/v3/video-auth/url-signature-token-by-id?' + split_url.query
                # Get the redirect url
                r = curl_cffi.get(video_src, impersonate="chrome", proxies=config.proxies)
                item['content_html'] += utils.add_video(config.server + '/proxy/' + r.url, 'application/x-mpegURL', child[3]['playlist'][0]['image'], child[3]['playlist'][0]['title'])
            else:
                logger.warning('unhandled child type ' + child[3]['type'])
        if child[3].get('children') and isinstance(child[3]['children'], list):
            process_children(child[3]['children'])

    def process_children(children):
        if isinstance(children, list) and len(children) > 0:
            if isinstance(children[0], list):
                for child in children:
                    if isinstance(child, list) and len(child) > 0:
                        if isinstance(child[0], str) and child[0] == '$':
                            process_child(child)
                        elif isinstance(child[0], list):
                            process_children(child)
                    else:
                        logger.warning('unhandled child ' + str(child))
            elif isinstance(children[0], str) and children[0] == '$':
                process_child(children)

    if article:
        process_children(article[3]['children'])

    item['content_html'] = item['content_html'].encode('latin-1', errors='ignore').decode('utf-8', errors='ignore')

    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    else:
        item['author'] = {
            "name": "TUDN"
        }
        item['authors'].append(item['author'])

    return item


def get_feed(url, args, site_json, save_debug=False):
    next_json = get_next_json(url + '?_rsc=' + site_json['rsc'], save_debug)
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/feed.json')
    # TODO: parse feed
    return None
