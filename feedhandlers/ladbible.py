import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import config, utils
from feedhandlers import jwplayer, rss

import logging

logger = logging.getLogger(__name__)


def get_next_json(url, save_debug):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
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
        logger.warning('unable to get next data from ' + url)
        return None
    if save_debug:
        utils.write_file(next_data, './debug/next.txt')

    next_json = {}
    x = 0
    m = re.search(r'^\s*([0-9a-f]{1,2}):(.*)', next_data)
    while m:
        key = m.group(1)
        # print(key)
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
                # if not val.isascii():
                #     i = n
                #     n = 0
                #     for c in val:
                #         n += 1
                #         i -= len(c.encode('utf-8'))
                #         if i == 0:
                #             break
                #     val = next_data[x:x + n]
        if val:
            # print(key, val)
            if (val.startswith('{') and val.endswith('}')) or (val.startswith('[') and val.endswith(']')):
                next_json[key] = json.loads(val)
            else:
                next_json[key] = val
            x += len(val)
            if next_data[x:].startswith('\n'):
                x += 1
            m = re.search(r'^\s*([0-9a-f]{1,2}):(.*)', next_data[x:])
        else:
            break
    return next_json


def resize_image(img_src, width=1080):
    return 'https://images.ladbible.com/resize?type=webp&quality=70&width={}&fit=contain&gravity=auto&url=https://images.ladbiblegroup.com{}'.format(width, urlsplit(img_src).path)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if '/jw-iframe' in split_url.path:
        params = parse_qs(split_url.query)
        if 'videoId' in params:
            return jwplayer.get_content('https://cdn.jwplayer.com/v2/media/{}?page_domain={}'.format(params['videoId'][0], split_url.netloc), args, {}, False)
        else:
            logger.warning('unknown videoId for ' + url)
            return None

    next_json = get_next_json(url, save_debug)
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/next.json')

    def find_child(children, key, val):
        for child in children:
            if isinstance(child, list) and child[0] == '$' and isinstance(child[3], dict):
                if key in child[3]:
                    if isinstance(child[3][key], str):
                        if val in child[3][key]:
                            return child
                    else:
                        return child
                if 'children' in child[3]:
                    c = find_child(child[3]['children'], key, val)
                    if c:
                        return c
        return None

    content_container = None
    for key, val in next_json.items():
        if isinstance(val, list) and isinstance(val[0], str) and val[0] == '$':
            if val[3].get('className') and val[3]['className'].startswith('content_container__'):
                content_container = find_child(val[3]['children'], 'channel', site_json['channel'])
    if not content_container:
        logger.warning('unable to find content container in ' + url)
        return None
    article_json = content_container[3]['content']

    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article_json['staticLink'])
    item['title'] = article_json['title'].encode('iso-8859-1').decode('utf-8')

    dt = datetime.fromisoformat(article_json['publishedAtUTC'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('updatedAtUTC'):
        dt = datetime.fromisoformat(article_json['updatedAtUTC'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {
        "name": article_json['author']['name']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['tags'] = []
    if article_json.get('categories'):
        item['tags'] += [x['name'] for x in article_json['categories']]
    if article_json.get('tags'):
        item['tags'] += [x['name'] for x in article_json['tags']]

    if article_json.get('metaDescription'):
        item['summary'] = article_json['metaDescription'].encode('iso-8859-1').decode('utf-8')
    elif article_json.get('summary'):
        item['summary'] = article_json['summary'].encode('iso-8859-1').decode('utf-8')

    item['content_html'] = ''
    if article_json.get('summary'):
        item['content_html'] += '<p><em>' + article_json['summary'] + '</em></p>'

    if article_json.get('featuredVideo'):
        item['image'] = article_json['featuredImage']
        #item['content_html'] += utils.add_video(article_json['featuredVideo'], 'video/mp4', article_json['featuredImage'], article_json['featuredVideoInfo'].get('title'))
        item['content_html'] += utils.add_embed('https://cdn.jwplayer.com/v2/media/' + article_json['featuredVideoInfo']['id'])
    elif article_json.get('featuredImage'):
        item['image'] = article_json['featuredImage']
        item['content_html'] += utils.add_image(resize_image(item['image']), article_json['featuredImageInfo']['credit'].get('text'), link=item['image'])

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if article_json.get('body') and article_json['body'].startswith('$'):
        key = article_json['body'][1:]
        soup = BeautifulSoup(next_json[key].encode('iso-8859-1').decode('utf-8'), 'html.parser')
        if save_debug:
            utils.write_file(str(soup), './debug/debug.html')
        for el in soup.select('p:has(img)', recursive=False):
            new_html = utils.add_image(resize_image(el.img['src']), el.img.get('alt'))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

        for el in soup.find_all('iframe'):
            new_html = utils.add_embed(el['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el.parent and el.parent.name == 'p':
                el.parent.replace_with(new_el)
            else:
                el.replace_with(new_el)

        for el in soup.find_all(class_='social-embed'):
            new_html = ''
            if el.blockquote:
                if 'twitter-tweet' in el.blockquote['class']:
                    links = el.blockquote.find_all('a')
                    new_html = utils.add_embed(links[-1]['href'])
                elif 'instagram-media' in el.blockquote['class']:
                    new_html = utils.add_embed(el.blockquote['data-instgrm-permalink'])
                elif 'tiktok-embed' in el.blockquote['class']:
                    new_html = utils.add_embed(el.blockquote['cite'])
                elif 'reddit-embed-bq' in el.blockquote['class']:
                    links = el.blockquote.find_all('a')
                    new_html = utils.add_embed(links[0]['href'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled social-embed in ' + item['url'])

        item['content_html'] += str(soup)

    return item


def get_feed(url, args, site_json, save_debug=False):
    if url.endswith('.rss'):
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    logger.warning('unhandled feed url ' + url)

    next_json = get_next_json(url, save_debug)
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/next.json')
    return None
