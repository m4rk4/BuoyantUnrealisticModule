import json, markdown2, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)


def resize_image(image, next_config, width=1200):
    return '{}/f_auto,c_limit,w_{},q_auto/{}/{}'.format(next_config['PUBLIC_GLOBAL_CLOUDINARY_DOMAINS'], width, image['raw_transformation'], image['public_id'])


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
    m = re.search(r'^([0-9a-f]{1,2}):(.*)', next_data)
    while m:
        key = m.group(1)
        x += len(key) + 1
        val = m.group(2)
        if val.startswith('I'):
            val = val[1:]
            x += 1
        elif val.startswith('T'):
            t = re.search(r'T([0-9a-f]+),(.*)', val)
            if t:
                n = int(t.group(1), 16)
                x += len(t.group(1)) + 2
                val = next_data[x:x + n]
        if val:
            if (val.startswith('{') and val.endswith('}')) or (val.startswith('[') and val.endswith(']')):
                next_json[key] = json.loads(val)
            else:
                next_json[key] = val
            x += len(val)
            if next_data[x:].startswith('\n'):
                x += 1
            m = re.search(r'^([0-9a-f]{1,2}):(.*)', next_data[x:])
        else:
            break
    return next_json


def get_content(url, args, site_json, save_debug=False):
    next_json = get_next_json(url, save_debug)
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/next.json')

    ld_json = None
    article_json = None
    for val in next_json.values():
        if isinstance(val, list) and len(val) == 4 and isinstance(val[0], str) and val[0] == '$':
            if val[1] == 'script' and val[3]['type'] == 'application/ld+json':
                if val[3]['dangerouslySetInnerHTML']['__html'].startswith('$'):
                    key = val[3]['dangerouslySetInnerHTML']['__html'][1:]
                    ld = next_json[key]
                elif val[3]['dangerouslySetInnerHTML']['__html'].startswith('{'):
                    ld = json.loads(val[3]['dangerouslySetInnerHTML']['__html'])
                else:
                    ld = None
                if ld and ld['@type'] == 'NewsArticle':
                    ld_json = ld
            elif 'children' in val[3] and 'article' in val[3]['children']:
                article_json = val[3]['children']

    if not ld_json:
        logger.warning('unable to find ld+json in ' + url)
        return None
    if save_debug:
        utils.write_file(ld_json, './debug/ld.json')

    item = {}
    item['id'] = ld_json['mainEntityOfPage']['@id']
    item['url'] = ld_json['mainEntityOfPage']['@id']
    item['title'] = ld_json['headline']

    dt = datetime.fromisoformat(ld_json['datePublished'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if ld_json.get('dateModified'):
        dt = datetime.fromisoformat(ld_json['dateModified'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {
        "name": ld_json['author']['name']
    }

    if ld_json.get('articleSection'):
        item['tags'] = [ld_json['articleSection']]

    if ld_json.get('image'):
        item['_image'] = ld_json['image']['url']
    elif ld_json.get('thumbnailUrl'):
        item['_image'] = ld_json['thumbnailUrl']

    if ld_json.get('description'):
        item['summary'] = ld_json['description']

    item['content_html'] = ''
    def format_content(content):
        content_html = ''
        if content is None:
            return content_html
        elif isinstance(content, str):
            if content.isascii():
                content_html = content
            else:
                try:
                    content_html = content.encode('iso-8859-1').decode('utf-8')
                except:
                    content_html = content
        elif isinstance(content, list) and len(content) == 4 and content[0] == '$':
            if content[1].startswith('$L'):
                content_name = block_name(content)
                if content_name == 'ImageGallery':
                    if content[3].get('images'):
                        for image in content[3]['images']:
                            content_html += utils.add_image(image['url'], image.get('caption'))
                elif content_name == 'InlineSvg':
                    if 'callout.svg' in content[3]['src']:
                        content_html += '💬 '
                    else:
                        logger.warning('unhandled InlineSvg ' + content[3]['src'])
                else:
                    logger.warning('unhandled content type ' + content_name)
            else:
                if 'children' in content[3]:
                    content_html = format_content(content[3]['children'])
                if content[1] == 'blockquote':
                    # content_html = utils.add_blockquote(content_html)
                    content_html = utils.add_pullquote(content_html)
                elif content[1] == 'div' and 'className' in content[3] and 'Callout_container' in content[3]['className']:
                    content_html = utils.add_blockquote(content_html)
                elif content[1] == 'div' and 'className' in content[3] and 'Callout_title' in content[3]['className']:
                    content_html = re.sub(r'(</?)div', r'\1span', content_html)
                    content_html = '<div style="font-size:1.05em; font-weight:bold;">' + content_html + '</div>'
                # elif content[1] == 'div' and 'className' in content[3] and '-bold_' in content[3]['className']:
                #     content_html = '<div style="font-weight:bold;">' + content_html + '</div>'
                else:
                    if content[1] == 'a':
                        start_tag = '<a href="{}">'.format(content[3]['href'])
                    else:
                        start_tag = '<{}>'.format(content[1])
                    end_tag = '</{}>'.format(content[1])
                    content_html = start_tag + content_html + end_tag
        elif isinstance(content, list):
            for c in content:
                content_html += format_content(c)
        else:
            logger.warning('unhandled content ' + str(content))
        return content_html

    def format_block(block):
        block_html = ''
        for content in block['content']:
            block_html += format_content(content)
        return block_html

    def block_name(block):
        nonlocal next_json
        if isinstance(block, list) and len(block) == 4 and isinstance(block[0], str) and block[0] == '$' and block[1].startswith('$L'):
            key = block[1][2:]
            if key in next_json:
                val = next_json[key]
                if isinstance(val, dict) and 'name' in val:
                    return val['name']
                else:
                    logger.warning('unhandled block type ' + type(val))
        return ''

    if article_json:
        for child in article_json[3]['children']:
            if isinstance(child, list) and isinstance(child[0], str):
                if child[0] == '$':
                    if block_name(child) == 'TextBlockClient':
                        item['content_html'] += format_block(child[3])
                elif child[0].startswith('$L'):
                    for c in child:
                        key = c[2:]
                        if key in next_json:
                            if block_name(next_json[key]) == 'TextBlockClient':
                                item['content_html'] += format_block(next_json[key][3])
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_json = get_next_json(url, save_debug)
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/next.json')

    ld_json = None
    for val in next_json.values():
        if isinstance(val, dict) and '@type' in val and val['@type'] == 'WebPage' and 'mainEntity' in val and val['mainEntity']['@type'] == 'CollectionPage':
            ld_json = val
            break

    n = 0
    feed_items = []
    for article in ld_json['mainEntity']['mainEntity']:
        if save_debug:
            logger.debug('getting content for ' + article['url'])
        item = get_content(article['url'], args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['title'] = ld_json['mainEntity']['name'] + ' | ' + ld_json['publisher']['name']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
