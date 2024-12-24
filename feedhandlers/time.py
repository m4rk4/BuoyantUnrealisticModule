import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit, quote_plus

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    return '{}://{}{}?quality=85&w={}'.format(split_url.scheme, split_url.netloc, split_url.path, width)


def add_image(image):
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('credit'):
        captions.append(image['credit'])
    return utils.add_image(resize_image(image['image']), ' | '.join(captions))


def get_content(url, args, site_json, save_debug):
    split_url = urlsplit(url)
    api_url = 'https://api.time.com/wp-json/tempo/v1/documents?path={}'.format(quote_plus(split_url.path))
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    post_json = api_json['data']
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['meta']['canonical']
    item['title'] = post_json['seo_headline']

    dt = datetime.fromtimestamp(post_json['published']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromtimestamp(post_json['last_updated']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['authors'] = [{"name": x['title']} for x in post_json['authors']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    else:
        item['author'] = {
            "name": 'Time Magazine'
        }
        item['authors'].append(item['author'])

    if post_json['taxonomy'].get('tags'):
        item['tags'] = post_json['taxonomy']['tags'].copy()
    else:
        item['tags'] = []
    if post_json['taxonomy'].get('category'):
        item['tags'].append(post_json['taxonomy']['category'])
    if post_json['taxonomy'].get('subcategory'):
        item['tags'] = [*item['tags'], *post_json['taxonomy']['subcategory']]
    if item.get('tags'):
        item['tags'] = test_list = list(set(item['tags']))
    else:
        del item['tags']

    item['image'] = post_json['meta']['og:image']

    item['summary'] = post_json['meta']['description']

    item['content_html'] = ''
    if post_json.get('primary_media'):
        if post_json['primary_media']['type'] == 'image':
            item['content_html'] += add_image(post_json['primary_media']['primary_image'])
        elif post_json['primary_media']['type'] == 'hero-card-image':
            item['content_html'] += add_image(post_json['primary_media']['data'])
        elif post_json['primary_media']['type'] == 'video-jw':
            item['content_html'] += utils.add_video(post_json['primary_media']['data']['url'], post_json['primary_media']['data']['video_type'], post_json['primary_media']['data']['poster_url'], post_json['primary_media']['data']['name'])
        else:
            logger.warning('unhandled primary media type {} in {}'.format(post_json['primary_media']['type'], item['url']))
    elif post_json.get('primary_image'):
        item['content_html'] += add_image(post_json['primary_image'])

    for block in post_json['body']:
        if block['type'] == 'paragraph' or block['type'] == 'heading' :
            if block['format'] == 'html':
                if block['content'].startswith('<p><strong>Read More'):
                    continue
                if re.search('dropcap', block['content']):
                    soup = BeautifulSoup(block['content'], 'html.parser')
                    el = soup.find(class_='dropcap')
                    if el:
                        el['style'] = 'float:left; font-size:4em; line-height:0.8em;'
                        item['content_html'] += str(soup) + '<span style="clear:left;"></span>'
                else:
                    item['content_html'] += block['content']
            else:
                logger.warning('unhandled paragraph format {} in {}'.format(block['format'], item['url']))

        elif block['type'] == 'image':
            item['content_html'] += add_image(block)

        elif block['type'] == 'video-jw':
            if block['data'].get('media_id'):
                item['content_html'] += utils.add_embed('https://content.jwplatform.com/players/{}.html'.format(block['data']['media_id']))
            elif block['data'].get('url'):
                item['content_html'] += utils.add_video(block['data']['url'], block['data']['video_type'], block['data']['poster_url'], block['data']['name'], use_videojs=True)
            else:
                logger.warning('unhandled video-jw block in ' + item['url'])

        elif block['type'] == 'embed-twitter' or block['type'] == 'video-youtube':
            item['content_html'] += utils.add_embed(block['original_oembed_url'])

        elif re.search(r'recirc|subscription|tout', block['type']):
            pass

        else:
            logger.warning('unhandled body block type {} in {}'.format(block['type'], item['url']))
    
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
