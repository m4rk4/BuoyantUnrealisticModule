import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src):
    if not img_src.startswith('https://mediacloud.theweek.com/image/upload/'):
        return img_src
    split_url = urlsplit(img_src)
    paths = list(filter(None, split_url.path.split('/')))
    if re.search(r'v\d+', paths[2]):
        paths.insert(2, 'f_auto,t_content-image-desktop@1')
    else:
        paths[2] = 'f_auto,t_content-image-desktop@1'
    return 'https://mediacloud.theweek.com/' + '/'.join(paths)


def add_image(image):
    img_src = resize_image(image['src'])
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('credit'):
        captions.append(image['credit'])
    return utils.add_image(img_src, ' | '.join(captions))


def format_block(block):
    content_html = ''
    if block['__typename'] == 'DataBlock':
        if block.get('data'):
            data = json.loads(block['data'])
        if block['type'] == 'TEXT':
            content_html = data
        elif block['type'] == 'HEADER':
            content_html = '<h{0}>{1}</h{0}>'.format(data['size'], data['text'])
        elif block['type'] == 'IMAGE':
            content_html = add_image(data)
        elif block['type'] == 'SOCIAL_EMBED':
            content_html = utils.add_embed(data['__data']['url'])
        else:
            logger.warning('unhandled DataBlock type ' + block['type'])
    elif block['__typename'] == 'WidgetBlock':
        content_html = utils.add_embed(block['url'])
    else:
        logger.warning('unhandled block type ' + block['__typename'])
    return content_html


def get_apollo_state(url):
    page_html = utils.get_url_html(url)
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', string=re.compile(r'__APOLLO_STATE__'))
    if not el:
        logger.warning('unable to find APOLLO_STATE in ' + url)
        return None
    m = re.search(r'window.__APOLLO_STATE__=(.*);$', el.string)
    if not m:
        logger.warning('unable to parse APOLLO_STATE in ' + url)
        return None
    return json.loads(m.group(1))


def get_content(url, args, save_debug=False):
    apollo_state = get_apollo_state(url)
    if save_debug:
        utils.write_file(apollo_state, './debug/debug.json')

    page_json = None
    for key, val in apollo_state['ROOT_QUERY'].items():
        if key.startswith('getRoot:'):
            if re.search(r'^(Article|Gallery)', val['page']['__ref']):
                page_json = apollo_state[val['page']['__ref']]
            break
    if not page_json:
        logger.warning('unable to determine article json in ' + url)
        return None

    item = {}
    item['id'] = page_json['id']
    item['url'] = 'https://theweek.com' + page_json['url']
    item['title'] = page_json['title']

    dt = datetime.fromisoformat(page_json['created']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(page_json['updated']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for key, val in page_json.items():
        if key.startswith('authors'):
            for it in val:
                author = apollo_state[it['__ref']]
                authors.append(author['name'])
            break
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if page_json.get('belowBodyTerms'):
        for it in page_json['belowBodyTerms']:
                item['tags'].append(it['name'])
    if page_json.get('categories'):
        for it in page_json['categories']:
            if it['name'] not in item['tags']:
                item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''

    if page_json.get('subtitle'):
        item['summary'] = page_json['subtitle']
        item['content_html'] = '<p><em>{}</em></p>'.format(page_json['subtitle'])

    if page_json.get('primaryMedia'):
        item['_image'] = page_json['primaryMedia']['src']
        item['content_html'] += add_image(page_json['primaryMedia'])
    elif page_json.get('teaserImage'):
        item['_image'] = page_json['teaserImage']['src']
        item['content_html'] += add_image(page_json['teaserImage'])

    if page_json.get('galleryItems'):
        for i, gallery_item in enumerate(page_json['galleryItems']):
            if gallery_item.get('__ref'):
                gallery = apollo_state[gallery_item['__ref']]
            else:
                gallery = gallery_item
            if gallery.get('title'):
                item['content_html'] += '<h2>{}. {}</h2>'.format(i+1, gallery['title'])
            if gallery.get('subtitle'):
                item['content_html'] = '<p><em>{}</em></p>'.format(gallery['subtitle'])
            if gallery.get('description'):
                for it in gallery['description']:
                    block = apollo_state[it['__ref']]
                    item['content_html'] += format_block(block)
            if gallery.get('sources'):
                sources = ''
                for it in gallery['sources']:
                    sources += '<a href="{}">{}</a>, '.format(it['url'], it['title'])
                item['content_html'] += '<p><small>{}</small></p>'.format(sources[:-2])
            if gallery.get('media'):
                for it in gallery['media']:
                    if it['__typename'] == 'Image':
                        item['content_html'] += add_image(it) + '<br/>'
                    else:
                        logger.warning('unhandled gallery media type {} in {}'.format(it['__typename'], item['url']))

    if page_json.get('body'):
        for it in page_json['body']:
            block = apollo_state[it['__ref']]
            item['content_html'] += format_block(block)
    return item


def get_feed(args, save_debug=False):
    apollo_state = get_apollo_state(args['url'])
    if save_debug:
        utils.write_file(apollo_state, './debug/feed.json')

    page_json = None
    for key, val in apollo_state['ROOT_QUERY'].items():
        if key.startswith('getRoot:'):
            if re.search(r'^(Article|AuthorIndex|Page|TaxonomyIndex):', val['page']['__ref']):
                page_json = apollo_state[val['page']['__ref']]
            break
    if not page_json:
        logger.warning('unable to determine page json in ' + args['url'])
        return None

    articles = []
    if page_json['__typename'] == 'AuthorIndex' or page_json['__typename'] == 'TaxonomyIndex':
        for it in page_json['teasers']:
            teaser = apollo_state[it['__ref']]
            article = {}
            article['url'] = 'https://theweek.com' + teaser['url']
            dt = datetime.fromisoformat(teaser['updated']).astimezone(timezone.utc)
            article['_timestamp'] = dt.timestamp()
            articles.append(article)
    elif page_json['__typename'] == 'Page' or page_json['__typename'] == 'Article':
        if '/speedreads' in args['url']:
            article_type = 'Speed Reads'
            article = {}
            split_url = urlsplit(page_json['url'])
            article['url'] = 'https://theweek.com' + split_url.path
            dt = datetime.fromisoformat(page_json['updated']).astimezone(timezone.utc)
            article['_timestamp'] = dt.timestamp()
            articles.append(article)
        else:
            article_type = ''
        for key, val in page_json.items():
            if key.startswith('associatedContent'):
                for content in val:
                    for teaser in content['teasers']:
                        if article_type and teaser['articleType'] != article_type:
                            continue
                        article = {}
                        # Remove the url fragment, e.g. #1
                        split_url = urlsplit(teaser['url'])
                        article['url'] = 'https://theweek.com' + split_url.path
                        dt = datetime.fromisoformat(teaser['updated']).astimezone(timezone.utc)
                        article['_timestamp'] = dt.timestamp()
                        articles.append(article)
                break

    # Remove duplicates: https://www.geeksforgeeks.org/python-removing-duplicate-dicts-in-list/
    articles = {frozenset(item.items()): item for item in articles}.values()

    n = 0
    feed = utils.init_jsonfeed(args)
    feed['title'] = 'The Week'
    if '/speedreads' in args['url']:
        feed['title'] += ' | Speed Reads'
    elif page_json.get('title'):
        feed['title'] += ' | ' + page_json['title']
    feed_items = []
    for article in sorted(articles, key=lambda i: i['_timestamp'], reverse=True):
        if save_debug:
            logger.debug('getting content for ' + article['url'])
        item = get_content(article['url'], args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed['items'] = feed_items.copy()
    return feed
