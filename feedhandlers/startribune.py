import json, re
from curl_cffi import requests as curl_cffi_requests
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, save_debug):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "next-router-state-tree": "%5B%22%22%2C%7B%22children%22%3A%5B%5B%22section%22%2C%22vikings-trade-cam-robinson-left-tackle-jacksonville-christian-darrisaw-replacement%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%5B%22slug%22%2C%22601171547%22%2C%22c%22%5D%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%5D%7D%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D",
        "next-url": "/vikings-trade-cam-robinson-left-tackle-jacksonville-christian-darrisaw-replacement/601171547",
        "priority": "u=1, i",
        "rsc": "1",
        "sec-ch-ua": "\"Chromium\";v=\"130\", \"Microsoft Edge\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
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

    page_data = None
    for it in next_json['2']:
        if isinstance(it, list) and it[0] == '$' and isinstance(it[3], dict) and 'pageData' in it[3]:
            page_data = it[3]['pageData']
    if not page_data:
        logger.warning('unable to find pageData for ' + url)
        return None

    content_json = page_data['getContent'][0]
    if save_debug:
        utils.write_file(content_json, './debug/debug.json')

    item = {}
    item['id'] = content_json['id']
    item['url'] = url
    item['title'] = content_json['headline']

    dt = datetime.fromisoformat(content_json['displayDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if content_json.get('lastCmsUpdateDate'):
        dt = datetime.fromisoformat(content_json['lastCmsUpdateDate'])
        item['date_modified'] = dt.isoformat()

    item['authors'] = []
    for it in content_json['authors']:
        if it.get('byline'):
            item['authors'].append({"name": it['byline']})
        elif it.get('name'):
            if it.get('organization'):
                item['authors'].append({"name": '{} ({})'.format(it['name'], it['organization'])})
            else:
                item['authors'].append({"name": it['name']})
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'].replace(',', '&#44;') for x in item['authors']]))
        }
        item['author']['name'] = item['author']['name'].replace('&#44;', ',')

    item['tags'] = []
    if content_json.get('sections'):
        if isinstance(content_json['sections'], list):
            item['tags'] = [x['name'] for x in content_json['sections']]
        else:
            for it in next_json[content_json['sections'][1:]]:
                block = next_json[it[1:]]
                item['tags'].append(block['name'])
    if content_json.get('tags'):
        item['tags'] += [x['name'] for x in content_json['tags']]
    if len(item['tags']) == 0:
        del item['tags']

    item['content_html'] = ''

    if content_json['__typename'] == 'Video':
        video_url = next((it for it in next_json[content_json['streams'][1:]] if '/master.m3u8' in it), None)
        if not video_url:
            video_url = next((it for it in next_json[content_json['streams'][1:]] if '/sd.m3u8' in it), None)
            if not video_url:
                video_url = next((it for it in next_json[content_json['streams'][1:]] if '/mobile.m3u8' in it), None)
                if not video_url:
                    video_url = next((it for it in next_json[content_json['streams'][1:]] if '.m3u8' in it), None)
                    if not video_url:
                        video_url = next_json[content_json['streams'][1:]][0]
        if '.m3u8' in video_url:
            item['content_html'] += utils.add_video(video_url, 'application/x-mpegURL', content_json['thumbnail']['url'], content_json['headline'])
        else:
            item['content_html'] += utils.add_video(video_url, 'video/mp4', content_json['thumbnail']['url'], content_json['headline'])
        return item
    
    if content_json.get('dek'):
        item['summary'] = content_json['dek']
        item['content_html'] += '<p><em>' + content_json['dek'] + '</em></p>'

    if content_json.get('leadArt'):
        item['image'] = 'https://arc.stimg.co' + urlsplit(content_json['leadArt']['image']['url']).path + '?w=640'
        captions = []
        if content_json['leadArt']['image'].get('caption'):
            captions.append(content_json['leadArt']['image']['caption'])
        if content_json['leadArt']['image'].get('photographers'):
            captions.append(re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in content_json['leadArt']['image']['photographers']])))
        item['content_html'] += utils.add_image(item['image'], ' | '.join(captions), link=content_json['leadArt']['image']['url'])

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    for it in content_json['body']:
        if it.startswith('$'):
            block = next_json[it[1:]]
            if block['__typename'] == 'BodyParagraph':
                if block['content'].startswith('$') and block['content'][1:] in next_json:
                    item['content_html'] += '<p>' + next_json[block['content'][1:]] + '</p>'
                else:    
                    item['content_html'] += '<p>' + block['content'] + '</p>'
            elif block['__typename'] == 'BodyHeading':
                item['content_html'] += '<h{0}>{1}</h{0}>'.format(block['level'], block['content'])
            elif block['__typename'] == 'BodyImage':
                image = next_json[block['image'][1:]]
                img_src = 'https://arc.stimg.co' + urlsplit(image['url']).path + '?w=640'
                captions = []
                if image.get('caption'):
                    captions.append(image['caption'])
                if image.get('photographers'):
                    photographers = []
                    for x in next_json[image['photographers'][1:]]:
                        photographers.append(next_json[x[1:]]['name'])
                    captions.append(re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(photographers)))
                item['content_html'] += utils.add_image(img_src, ' | '.join(captions), link=image['url'])
            elif block['__typename'] == 'BodyList':
                if block['listType'] == 'UNORDERED':
                    tag = 'ul'
                else:
                    tag = 'ol'
                item['content_html'] += '<{}>'.format(tag)
                for it in next_json[block['listItems'][1:]]:
                    item['content_html'] += '<li>' + it + '</li>'
                item['content_html'] += '</{}>'.format(tag)
            elif block['__typename'] == 'BodyEmbed':
                item['content_html'] += utils.add_embed(block['url'])
            elif block['__typename'] == 'BodyCodeBlock' and '<iframe' in block['content']:
                m = re.search(r'src="([^"]+)"', block['content'])
                item['content_html'] += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled block type {} in {}'.format(block['__typename'], item['url']))

    return item


def get_feed(url, args, site_json, save_debug=False):
    if url.endswith('.rss2'):
        # https://www2.startribune.com/rss-index/112994779/
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 2 and paths[-1].isnumeric():
        # Author
        api_url = 'https://www.startribune.com/api/author-articles?path=' + paths[-1] + '&limit=12'
        key = 'getAuthor'
    else:
        api_url = 'https://www.startribune.com/api/section?path=' + split_url.path + '&limit=12'
        key = 'getSection'
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    n = 0
    feed_items = []
    for article in api_json[key]['content']:
        article_url = 'https://www.startribune.com/{}/{}'.format(article['urlSlug'], article['id'])
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_content(article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
