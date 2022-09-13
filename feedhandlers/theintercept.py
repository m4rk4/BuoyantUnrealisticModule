import re
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    return 'https://theintercept.imgix.net/{}?auto=compress%2Cformat&q=90&w={}'.format(split_url.path, width)


def render_content(content):
    content_html = ''
    if content['type'] == 'paragraph':
        text = content['content']['text']
        if content['content'].get('items'):
            for i, it in enumerate(content['content']['items']):
                if it.get('data'):
                    start_tag = '<' + it['type']
                    for key, val in it['data'].items():
                        start_tag += ' {}="{}"'.format(key, val)
                    start_tag += '>'
                else:
                    start_tag = '<{}>'.format(it['type'])
                end_tag = '</{}>'.format(it['type'])
                text = text[:it['start']] + start_tag + text[it['start']:it['end']] + end_tag + text[it['end']:]
                if len(content['content']['items']) > i+1:
                    for next_it in content['content']['items'][i+1:]:
                        if next_it['start'] >= it['start']:
                            n = len(start_tag)
                            if next_it['start'] >= it['end']:
                                n += len(end_tag)
                            next_it['start'] += n
                        if next_it['end'] >= it['start']:
                            n = len(start_tag)
                            if next_it['end'] >= it['end']:
                                n += len(end_tag)
                            next_it['end'] += n
        content_html += '<p>{}</p>'.format(text)

    elif content['type'] == 'heading':
        content_html += '<h2>{}</h2>'.format(content['content']['text'])

    elif content['type'] == 'image':
        captions = []
        if content.get('caption'):
            captions.append(content['caption']['text'])
        if content.get('caption-source'):
            captions.append(content['caption-source']['text'])
        content_html += utils.add_image(resize_image(content['src']), ' | '.join(captions))

    elif content['type'] == 'block-embed':
        if content['shortcode'] == 'pullquote':
            quote = ''
            for it in content['content']:
                quote += render_content(it)
            content_html += utils.add_pullquote(quote)

        elif content['shortcode'] == 'intrograph':
            for it in content['content']:
                content_html += render_content(it)

        elif content['shortcode'] == 'chapter':
            content_html += '<h2>{}. {}</h2>'.format(content['props']['number'], content['props']['title'])

        elif content['shortcode'] == 'youtube':
            content_html += utils.add_embed('https://www.youtube.com/embed/' + content['props']['sourceId'])

        elif content['shortcode'] == 'acast':
            content_html += utils.add_embed('https://shows.acast.com/{}/episodes/{}'.format(content['props']['podcast'], content['props']['id']))

        elif content['shortcode'] == 'oembed':
            if content['props']['type'] == 'twitter':
                content_html += utils.add_embed(content['props']['url'])
            else:
                logger.warning('unhandled block-embed oembed type ' + content['props']['type'])

        elif content['shortcode'] == 'iframe':
            content_html += utils.add_embed(content['props']['src'])

        elif re.search(r'cta|newsletter|promote', content['shortcode']):
            pass
        else:
            logger.warning('unhandled block-embed type ' + content['shortcode'])

    else:
        logger.warning('unhandled content type ' + content['type'])
    return content_html

def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    api_url = 'https://theintercept.com/api/requestPostBySlug/?realm=theintercept&slug={}'.format(paths[-1])
    article_json = utils.get_url_json(api_url)
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['ID']
    item['url'] = article_json['link']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['publishedTime'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    authors = []
    for it in article_json['authors']:
        authors.append(it['display_name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    for it in article_json['categories']:
        item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''
    if article_json.get('excerpt'):
        item['summary'] = article_json['excerpt']
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    if article_json.get('promo_image'):
        item['_image'] = resize_image('https://theintercept.com/' + article_json['promo_image']['sizes']['original']['path'])
        if article_json.get('content-parsed') and article_json['content-parsed'][0]['type'] != 'image':
            captions = []
            if article_json['promo_image'].get('excerpt'):
                captions.append(article_json['promo_image']['excerpt'])
            if article_json['promo_image'].get('credit'):
                captions.append(article_json['promo_image']['credit'])
            item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    for content in article_json['content-parsed']:
        item['content_html'] += render_content(content)

    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
