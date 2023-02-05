import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def add_image(image, images):
    if images:
        for i, img in enumerate(images):
            if img['_id'] == image['_id']:
                del images[i]
                break
    caption = image.get('caption')
    if not caption:
        caption = ''
    return utils.add_image(image['url'], caption)


def add_video(video):
    return utils.add_video(video['href'], video['contentType'], video['thumbnailUrl'], video['title'])


def render_block(block, images, videos):
    block_html = ''
    if block['type'] == 'paragraph':
        if block['text'].startswith('<div'):
            block_html += block['text']
        else:
            block_html += '<p>{}</p>'.format(block['text'])

    elif block['type'] == 'heading' or block['type'] == 'list' or block['type'] == 'table':
        block_html += block['text']

    elif block['type'] == 'image':
        block_html += add_image(block['image'], images)

    elif block['type'] == 'video':
        block_html += add_video(videos[block['ref']])

    elif block['type'] == 'embed':
        block_html += utils.add_embed(block['source'])

    elif block['type'] == 'prosAndCons':
        svg = '<svg width="37" height="37" fill="none" style="vertical-align:middle;" xmlns="http://www.w3.org/2000/svg"><circle cx="18.091" cy="18.419" r="17.5" stroke="#D8D8D8"/><path fill-rule="evenodd" d="M23.168 27.189H14.86a1.852 1.852 0 01-1.846-1.847v-9.23c0-.508.203-.97.535-1.302l6.084-6.083.978.97c.25.248.406.6.406.978l-.028.295-.877 4.218h5.825c1.015 0 1.846.831 1.846 1.847v1.846c0 .24-.046.461-.129.674l-2.788 6.507a1.834 1.834 0 01-1.698 1.127zm-12-11.078H7.476V27.19h3.692V16.11z" fill="#39B54A"/></svg>'
        block_html += '<h3>{}&nbsp;Pros</h3>'.format(svg)
        for it in block['pros']:
            block_html += render_block(it, images, videos)
        svg = '<svg width="37" height="37" fill="none" style="vertical-align:middle;" xmlns="http://www.w3.org/2000/svg"><circle cx="18.767" cy="18.419" r="17.5" stroke="#D8D8D8"/><path fill-rule="evenodd" d="M12.766 10.573h8.308c1.015 0 1.846.83 1.846 1.846v9.23c0 .508-.203.97-.545 1.302l-6.073 6.083-.979-.969a1.39 1.39 0 01-.406-.978l.028-.296.877-4.218H9.997a1.852 1.852 0 01-1.846-1.846V18.88c0-.24.046-.462.13-.674l2.787-6.508a1.834 1.834 0 011.698-1.126zm15.693 0h-3.693V21.65h3.693V10.573z" fill="#ED271C"/></svg>'
        block_html += '<h3>{}&nbsp;Cons</h3>'.format(svg)
        for it in block['cons']:
            block_html += render_block(it, images, videos)

    else:
        logger.warning('unhandled articleBody type ' + block['type'])
    return block_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    api_url = 'https://www.motortrend.com/api/v2/resource/' + quote_plus(split_url.path[1:])
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    article_json = api_json['data']['resource']
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['articleId']
    item['url'] = article_json['seo']['canonicalUrl']
    item['title'] = article_json['title']

    def format_date(matchobj):
        return '.{}+00:00'.format(matchobj.group(1).zfill(3))
    date = re.sub(r'\.(\d+)Z', format_date, article_json['publishedDate'])
    dt = datetime.fromisoformat(date)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    date = re.sub(r'\.(\d+)Z', format_date, article_json['lastModifiedDate'])
    dt = datetime.fromisoformat(date)
    item['date_modified'] = dt.isoformat()

    authors = []
    for author in article_json['contributors']:
        if 'Writer' in author['roles']:
            authors.append(author['displayName'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if article_json['taxonomy'].get('primarySection'):
        item['tags'].append(article_json['taxonomy']['primarySection']['termName']['display'])
    if article_json['taxonomy'].get('primarySubsection'):
        item['tags'].append(article_json['taxonomy']['primarySubsection']['termName']['display'])
    if article_json['taxonomy'].get('sections'):
        for tag in article_json['taxonomy']['sections']:
            tag_name = tag['slug'].replace('-', ' ')
            if tag_name.casefold() in (name.casefold() for name in item['tags']):
                continue
        item['tags'].append(tag_name)
    if article_json['taxonomy'].get('subsections'):
        for tag in article_json['taxonomy']['subsections']:
            tag_name = tag['slug'].replace('-', ' ')
            if tag_name.casefold() in (name.casefold() for name in item['tags']):
                continue
        item['tags'].append(tag_name)
    if article_json['taxonomy'].get('tags'):
        for tag in article_json['taxonomy']['tags']:
            tag_name = tag['slug'].replace('-', ' ')
            if tag_name.casefold() in (name.casefold() for name in item['tags']):
                continue
        item['tags'].append(tag_name)
    if article_json['taxonomy'].get('topics'):
        for tag in article_json['taxonomy']['topics']:
            tag_name = tag['slug'].replace('-', ' ')
            if tag_name.casefold() in (name.casefold() for name in item['tags']):
                continue
        item['tags'].append(tag_name)

    if article_json.get('thumbnail'):
        item['_image'] = article_json['thumbnail']['url']

    item['summary'] = article_json['seo']['metaDescription']

    images = None
    videos = None
    if article_json.get('assets'):
        if article_json['assets'].get('imageSlideshow'):
            images = article_json['assets']['imageSlideshow']
        if article_json['assets'].get('videoPlaylist'):
            videos = article_json['assets']['videoPlaylist']

    item['content_html'] = ''
    if article_json.get('subTitle'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['subTitle'])

    if article_json.get('heroMedia'):
        if article_json['heroMedia']['type'] == 'image':
            item['_image'] = article_json['heroMedia']['image']['url']
            item['content_html'] += add_image(article_json['heroMedia']['image'], images)
        elif article_json['heroMedia']['type'] == 'video':
            item['content_html'] += add_video(videos[article_json['heroMedia']['ref']])
        else:
            logger.warning('unhandled heroMedia type {} in {}'.format(article_json['heroMedia']['type'], url))

    for block in article_json['articleBody']:
        item['content_html'] += render_block(block, images, videos)

    if article_json.get('slides'):
        for slide in article_json['slides']:
            item['content_html'] += utils.add_image(slide['image']['url'])
            item['content_html'] += '<h3>{}</h3>'.format(slide['headline'])
            for block in slide['body']:
                item['content_html'] += render_block(block, images, videos)
            item['content_html'] += '<hr style="width:80%;" /><br/>'

    if images:
        item['content_html'] += '<h3>Gallery: {} images</h3>'.format(len(images))
        for image in images:
            item['content_html'] += add_image(image, None) + '<br/>'

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) == 0:
        api_url = 'https://www.motortrend.com/api/v2/resource/homepage'
    else:
        api_url = 'https://www.motortrend.com/api/v2/resource/' + quote_plus(split_url.path[1:])

    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    items = []
    for package in api_json['data']['resource']['packages']:
        if package['packageType'] == 'videoplaylist' or not package.get('items'):
            continue
        for it in package['items']:
            if it.get('published'):
                item = it.copy()
                dt = datetime.strptime(item['published'], '%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)').replace(tzinfo=timezone.utc)
                item['_timestamp'] = dt.timestamp()
                if 'age' in args:
                    if not utils.check_age(item, args):
                        continue
                if not next((i for i in items if i['_id'] == item['_id']), None):
                    items.append(item)

    items = sorted(items, key=lambda i: i['_timestamp'], reverse=True)

    n = 0
    feed_items = []
    for it in items:
        url = it['source']['seo']['canonicalUrl']
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
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
