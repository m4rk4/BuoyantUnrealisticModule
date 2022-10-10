import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_img_src(image, width=1000):
    if width < image['width']:
        w = width
        h = int(width * image['height']/image['width'])
    else:
        # doesn't upscale
        w = image['width']
        h = image['height']
    img_src = 'https://cms.prod.nypr.digital/images/{}/fill-{}x{}|format-jpeg|jpegquality-80/'.format(image['id'], w, h)
    return utils.get_redirect_url(img_src)

def add_image(image, width=1000, gallery_url=''):
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('credit'):
        captions.append(image['credit'])
    if gallery_url:
        gallery_url = '{}/content?read&url={}'.format(config.server, quote_plus(gallery_url))
        captions.append('<a href=""><b>View gallery</b></a>'.format(gallery_url))
    img_src = get_img_src(image, width)
    return utils.add_image(img_src, ' | '.join(captions), link=gallery_url)


def get_content(url, args, save_debug=False):
    page_html = utils.get_url_html(url)
    m = re.search(r'detailUrl:"([^"]+)"', page_html)
    if not m:
        logger.warning('unable to find detailUrl in ' + url)
        return None
    article_json = utils.get_url_json(m.group(1).encode().decode('unicode-escape'))
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['url']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['meta']['first_published_at']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    authors = []
    for it in article_json['related_authors']:
        authors.append('{} {}'.format(it['first_name'], it['last_name']))
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json.get('tags'):
        item['tags'] = []
        for it in article_json['tags']:
            item['tags'].append(it['name'])

    item['summary'] = article_json['description']

    item['content_html'] = ''
    if article_json.get('lead_asset'):
        for content in article_json['lead_asset']:
            if content['type'] == 'lead_image':
                item['content_html'] += add_image(content['value']['image'])
                if not item.get('_image'):
                    item['_image'] = get_img_src(content['value']['image'])
            elif content['type'] == 'lead_gallery':
                gallery_json = utils.get_url_json('https://cms.prod.nypr.digital/api/v2/pages/{}/'.format(content['value']['gallery']))
                item['content_html'] += add_image(content['value']['default_image'], gallery_url=gallery_json['url'])
                if not item.get('_image'):
                    item['_image'] = get_img_src(content['value']['default_image'])
            else:
                logger.warning('unhandled lead_asset type {} in {}'.format(content['type'], item['url']))

    if article_json.get('body'):
        for content in article_json['body']:
            if content['type'] == 'paragraph':
                item['content_html'] += content['value']
            elif content['type'] == 'pull_quote':
                item['content_html'] += utils.add_pullquote(content['value']['pull_quote'], content['value']['attribution'])
            elif content['type'] == 'image':
                item['content_html'] += add_image(content['value']['image'])
            elif content['type'] == 'code' or content['type'] == 'embed':
                soup = BeautifulSoup(content['value'][content['type']], 'html.parser')
                if soup.find(class_='twitter-tweet'):
                    links = soup.find_all('a')
                    item['content_html'] += utils.add_embed(links[-1]['href'])
                if soup.iframe:
                    item['content_html'] += utils.add_embed(soup.iframe['src'])
                else:
                    logger.warning('unhandled content {} in {}'.format(content['type'], item['url']))
            else:
                logger.warning('unhandled content type {} in {}'.format(content['type'], item['url']))

    if article_json.get('slides'):
        for content in article_json['slides']:
            if content['type'] == 'image_slide':
                item['content_html'] += add_image(content['value']['slide_image']['image'])
            else:
                logger.warning('unhandled slide type {} in {}'.format(content['type'], item['url']))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
