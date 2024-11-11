import json, re
from curl_cffi import requests as curl_cffi_requests
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, save_debug):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "next-router-state-tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22(withHeaderFooter)%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2F%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D",
        "next-url": "/",
        "priority": "u=1, i",
        "rsc": "1",
        "sec-ch-ua": "\"Not)A;Brand\";v=\"99\", \"Microsoft Edge\";v=\"127\", \"Chromium\";v=\"127\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }
    r = curl_cffi_requests.get(url, headers=headers, impersonate=config.impersonate, proxies=config.proxies)
    if r.status_code != 200:
        logger.warning('curl cffi requests status code {} getting {}'.format(r.status_code, url))
        return ''
    # next_data = utils.get_url_html(url, headers=headers, use_curl_cffi=True, use_proxy=True)
    # if not next_data:
    #     logger.warning('unable to get next data from ' + url)
    #     return None
    return r.text


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
                if not val.isascii():
                    i = n
                    n = 0
                    for c in val:
                        n += 1
                        i -= len(c.encode('utf-8'))
                        if i == 0:
                            break
                    val = next_data[x:x + n]
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
    for child in next_json['2']:
        if child[1] == 'main' and 'children' in child[3] and child[3]['children'][1] == 'article':
            article = child[3]['children'][3]
    # if not article:
    #     logger.warning('unable to find article data in ' + url)
    # if save_debug:
    #     utils.write_file(article, './debug/debug.json')

    payload = None
    if article:
        for child in article['children']:
            if isinstance(child, list) and 'payload' in child[3]:
                payload = child[3]['payload']
                break
    else:
        for child in next_json['2']:
            if isinstance(child, list) and len(child) == 4 and 'payload' in child[3]:
                payload = child[3]['payload']
                break

    ld_json = None
    gallery_json = None
    for key, val in next_json.items():
        if isinstance(val, dict) and '@type' in val:
            if val['@type'] == 'Article':
                ld_json = val
            elif val['@type'] == 'ImageGallery':
                gallery_json = val

    item = {}
    item['id'] = payload['content_id']
    item['url'] = ld_json['mainEntityOfPage']['url']
    item['title'] = payload['content_title']

    dt = datetime.fromisoformat(payload['content_publication_date'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if payload.get('content_modification_date'):
        dt = datetime.fromisoformat(payload['content_modification_date'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {
        "name": payload['content_writer_primary']
    }

    item['tags'] = [it.strip() for it in payload['content_tags'].split(',')]

    if ld_json.get('image'):
        item['_image'] = ld_json['image']

    item['content_html'] = ''
    if ld_json.get('description'):
        item['summary'] = ld_json['description']
        item['content_html'] += '<p><em>' + ld_json['description'] + '</em></p>'

    if payload['content_type'] == 'gallery' and gallery_json:
        gallery_images = []
        gallery_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
        for i, image in enumerate(gallery_json['image']):
            thumb = image['url'] + '?width=640&q=75&format=webp'
            gallery_images.append({"src": image['url'], "caption": "", "thumb": thumb})
            if i == 0:
                item['content_html'] += utils.add_image(image['url'] + '?width=1000&q=75&format=webp', link=image['url'])
            else:
                gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, link=image['url']) + '</div>'
        gallery_html += '</div>'
        gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
        item['content_html'] += '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + gallery_html
        return item

    article_components = None
    for child in article['children']:
        if isinstance(child, list) and len(child) == 4 and isinstance(child[0], str) and child[0] == '$' and 'FallbackComponent' in child[3] and 'children' in child[3]:
            c = child[3]['children']
            if isinstance(c, list) and len(c) == 4 and isinstance(c[0], str) and c[0] == '$' and 'ChildComponent' in c[3] and 'children' in c[3]:
                article_components = c[3]
                break

    if save_debug:
        utils.write_file(article_components, './debug/debug.json')

    row = 0
    def format_child(child):
        nonlocal next_json
        nonlocal row
        child_html = ''
        if isinstance(child, str):
            if child.isascii():
                return child
            else:
                try:
                    return child.encode('iso-8859-1').decode('utf-8')
                except:
                    return child
        elif isinstance(child, list) and len(child) > 0 and isinstance(child[0], str) and child[0] == '$':
            if 'data-ids' in child[3] and child[3]['data-ids'] == 'Typography':
                child_html += '<{}>'.format(child[1])
                child_html += format_children(child[3]['children'])
                child_html += '</{}>'.format(child[1])
            elif 'data-ids' in child[3] and child[3]['data-ids'] == 'Link':
                link = child[3]['href']
                if link.startswith('/'):
                    link = 'https://www.motortrend.com' + link
                child_html += '<a href="{}">'.format(link) + format_children(child[3]['children']) + '</a>'
            elif 'data-ids' in child[3] and child[3]['data-ids'] == 'Table':
                child_html += format_children(child[3]['children'])
            elif 'data-component' in child[3] and child[3]['data-component'] == 'TableElement':
                row = 0
                child_html += '<div>&nbsp;</div><table style="width:100%; border-collapse:collapse; border:1px solid #ccc;">'
                child_html += format_children(child[3]['children'])
                child_html += '</table><div>&nbsp;</div>'
            elif 'data-ids' in child[3] and child[3]['data-ids'] == 'TableRow':
                if row % 2:
                    style= ' style="background-color:#ccc;"'
                else:
                    style = ''
                row += 1
                child_html += '<tr{}>'.format(style)
                child_html += format_children(child[3]['children'])
                child_html += '</tr>'
            elif 'data-ids' in child[3] and child[3]['data-ids'] == 'TableCell':
                child_html += '<td style="padding-left:8px;">'
                child_html += format_children(child[3]['children'])
                child_html += '</td>'
            elif 'data-component' in child[3] and child[3]['data-component'] == 'ImageElement':
                image_html = format_children(child[3]['children'])
                m = re.search(r'src="([^"]+)"', image_html)
                if m:
                    img_src = m.group(1) + '?width=1000&q=75&format=webp'
                else:
                    img_src = ''
                m = re.search(r'href="([^"]+)"', image_html)
                if m:
                    link = m.group(1)
                else:
                    link = ''
                # TODO: caption
                child_html += utils.add_image(img_src, link=link)
            elif 'data-id' in child[3] and child[3]['data-id'] == 'photo-gallery-preview-card':
                link = child[3]['href']
                if link.startswith('/'):
                    link = 'https://www.motortrend.com' + link
                child_html += '<a href="{}">'.format(link) + format_children(child[3]['children']) + '</a>'
            elif 'imageProps' in child[3]:
                child_html += '<img src="{}"/>'.format(child[3]['src'])
                # skip further children
            elif 'className' in child[3] and 'flex-col' in child[3]['className']:
                child_html += format_children(child[3]['children'])
            elif 'video' in child[3]:
                if isinstance(child[3]['video'], str):
                    key = child[3]['video'][1:]
                    video = next_json[key]
                elif isinstance(child[3]['video'], dict):
                    video = child[3]['video']
                child_html += utils.add_video(video['videoFileUrl'], 'application/x-mpegURL', video['thumbnailUrl'], video['videoName'])
            elif 'embedElement' in child[3]:
                child_html += utils.add_embed(child[3]['embedElement']['embed'])
            elif 'adType' in child[3]:
                pass
            elif isinstance(child[2], str) and 'text-paragraph' in child[2] and 'children' in child[3]:
                child_html += format_children(child[3]['children'])
            elif not child[1].startswith('$') and 'children' in child[3]:
                if child[1] == 'svg':
                    pass
                else:
                    child_html += '<{}>'.format(child[1])
                    child_html += format_children(child[3]['children'])
                    child_html += '</{}>'.format(child[1])
        elif isinstance(child, list) and len(child) > 0:
            for c in child:
                child_html += format_child(c)
        return child_html

    def format_children(children):
        if isinstance(children, str) or (isinstance(children, list) and len(children) > 0 and isinstance(children[0], str) and children[0] == '$'):
            return format_child(children)
        elif isinstance(children, list):
            children_html = ''
            for child in children:
                children_html += format_child(child)
            return children_html

    if article_components:
        item['content_html'] += format_children(article_components['children'])
        item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url + '?_rsc=' + site_json['rsc'], save_debug)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/next.txt')

    if '/staff/' in url:
        matches = re.findall(r'"seo":\{"canonicalUrl":"([^"]+)', next_data)
    else:
        matches = re.findall(r'"href":"([^"]+)","data-ids":"Card"', next_data)

    n = 0
    if 'max' in args:
        n_max = int(args['max'])
    else:
        n_max = 10

    feed_items = []
    for m in matches:
        if m.startswith('/'):
            article_url = 'https://www.motortrend.com' + m
        else:
            article_url = m
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_content(article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if n == n_max:
                    break

    feed = utils.init_jsonfeed(args)
    # if api_json['seo'].get('metaTitle'):
    #     feed['title'] = api_json['seo']['metaTitle']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed

