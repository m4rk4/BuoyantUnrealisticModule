import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def render_block(block, item):
    block_html = ''
    split_url = urlsplit(item['url'])
    if block['type'] == 'tag':
        if isinstance(block['element']['value'], str):
            value = re.sub(r'href="/', 'href="{}://{}/'.format(split_url.scheme, split_url.netloc), block['element']['value'])
            block_html += '<{0}>{1}</{0}>'.format(block['element']['tag'], value)
        elif isinstance(block['element']['value'], dict):
            if block['element']['value']['type'] == 'shortcode':
                if block['element']['value']['element']['shortcode-id'] == 'video':
                    caption = 'Watch: <a href="{}://{}{}">{}</a>'.format(split_url.scheme, split_url.netloc, block['element']['value']['element']['url'], block['element']['value']['element']['title'])
                    block_html += utils.add_video(block['element']['value']['element']['video']['hls_streaming_url'], 'application/x-mpegURL', block['element']['value']['element']['video']['poster_image'], caption)
                elif block['element']['value']['element']['shortcode-id'] == 'social-media':
                    block_html += utils.add_embed(block['element']['value']['element']['shortcode-url'])
                elif block['element']['value']['element']['shortcode-id'] == 'speedbump':
                    block_html += '<p><a href="{}://{}{}">{}</a></p>'.format(split_url.scheme, split_url.netloc, block['element']['value']['element']['url'], block['element']['value']['element']['shortcode-title'])
                else:
                    logger.warning('unhandled shortcode element {} in {}'.format(block['element']['value']['element']['shortcode-id'], item['url']))
            else:
                logger.warning('unhandled element tag {} in {}'.format(block['element']['tag'], item['url']))
        elif isinstance(block['element']['value'], list):
            for blk in block['element']['value']:
                block_html += render_block(blk, item)
    else:
        logger.warning('unhandled block type {} in {}'.format(block['type'], item['url']))
    return block_html

def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    next_url = 'https://www.insideedition.com/_next/data/insideedition{}.json'.format(path)
    next_data = utils.get_url_json(next_url)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    article_json = next_data['pageProps']['data']['nodeQuery']

    item = {}
    item['id'] = article_json['id']
    item['url'] = url
    item['title'] = article_json['title']

    dt = None
    tz_loc = pytz.timezone('US/Eastern')
    if article_json.get('created'):
        if article_json['created'].isnumeric():
            dt_loc = datetime.fromtimestamp(int(article_json['created']))
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        else:
            dt = datetime.fromisoformat(article_json['created']).astimezone(pytz.utc)
    elif article_json.get('field_display_date'):
        dt = datetime.fromisoformat(article_json['field_display_date']).astimezone(pytz.utc)
    if dt:
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
    else:
        logger.warning('unknown date for ' + item['url'])

    if article_json.get('revision_timestamp'):
        dt_loc = datetime.fromtimestamp(int(article_json['revision_timestamp']))
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_modified'] = dt.isoformat()

    authors = []
    for it in article_json['field_byline']['authors']:
        if it.get('bio'):
            authors.append(it['bio']['title'])
        elif it.get('name'):
            authors.append(it['name'])
        else:
            authors.append('Inside Edition')
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if article_json.get('field_category'):
        item['tags'].append(article_json['field_category']['name'])
    if article_json.get('field_categories'):
        for it in article_json['field_categories']:
            item['tags'].append(it['name'])
    if article_json.get('field_tags'):
        for it in article_json['field_tags']:
            item['tags'].append(it['name'])

    item['content_html'] = ''
    if article_json.get('field_subhead'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['field_subhead'])

    if article_json['__typename'] == 'video':
        item['_image'] = article_json['field_image']['field_image']['poster']['url']
        item['content_html'] += utils.add_video(article_json['field_video_mpx_id']['hls_streaming_url'], 'application/x-mpegURL', item['_image'], 'Watch: ' + article_json['field_display_headline'])
    elif article_json['__typename'] == 'gallery':
        item['_image'] = article_json['field_image']['image']['poster']['url']
        captions = []
        if article_json['field_image'].get('alt'):
            captions.append(article_json['field_image']['alt'])
        if article_json['field_image'].get('field_credit'):
            captions.append(article_json['field_image']['field_credit'])
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))
    elif article_json.get('field_video'):
        item['_image'] = article_json['field_video']['field_image']['field_image']['poster']['url']
        item['content_html'] += utils.add_video(article_json['field_video']['field_video_mpx_id']['hls_streaming_url'], 'application/x-mpegURL', item['_image'], 'Watch: ' + article_json['field_video']['field_display_headline'])
    elif article_json.get('field_image'):
        item['_image'] = article_json['field_image']['field_image']['poster']['url']
        captions = []
        if article_json.get('field_image_caption'):
            captions.append(article_json['field_image_caption'])
        if article_json['field_image'].get('field_credit'):
            captions.append(article_json['field_image']['field_credit'])
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    body_json = json.loads(article_json['body'])
    if save_debug:
        utils.write_file(body_json, './debug/body.json')

    for block in body_json:
        item['content_html'] += render_block(block, item)

    if article_json.get('field_slides'):
        item['content_html'] += '<hr style="width:80%;" /><div>&nbsp</div>'
        for it in article_json['field_slides']:
            if it.get('field_caption'):
                caption = it['field_caption'].replace('<br/>', '')
            else:
                caption = ''
            item['content_html'] += utils.add_image(it['field_image']['image']['poster']['url'], it['field_image']['image'].get('field_credit'), desc=caption)

    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.insideedition.com/rss
    return rss.get_feed(url, args, site_json, save_debug, get_content)
