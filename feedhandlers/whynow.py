import json, re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1080):
    return 'https://www.whynow.co.uk/_next/image?url={}&w={}&q=75'.format(quote_plus(img_src), width)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    path += '.json'

    next_url = '{}://{}/_next/data/{}{}?slug={}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, paths[-1])
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        m = re.search(r'"buildId":"([^"]+)"', page_html)
        if m and m.group(1) != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = m.group(1)
            utils.update_sites(url, site_json)
            next_url = '{}://{}/_next/data/{}/{}?slug={}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, paths[-1])
            next_data = utils.get_url_json(next_url)
            if not next_data:
                return None
    return next_data


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    post_json = next_data['pageProps']['post']
    seo_json = next_data['pageProps']['seo']
    schema_json = json.loads(seo_json['schema']['raw'])
    if save_debug:
        utils.write_file(schema_json, './debug/schema.json')
    article_json = next((it for it in schema_json['@graph'] if (it['@type'] == 'Article' or it['@type'] == 'NewsArticle' or it['@type'] == 'ReviewNewsArticle' or it['@type'] == 'OpinionNewsArticle' or it['@type'] == 'ReportageNewsArticle')), None)
    content_json = next((it for it in post_json['layout']['rows'] if it.get('content')), None)

    item = {}
    item['id'] = post_json['id']
    item['url'] = seo_json['canonical']
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(article_json['datePublished']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['dateModified']).astimezone((timezone.utc))
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in content_json['wordsBy']:
        authors.append(it['name'])
    # TODO: illustrationBy, interviewBy, photographyBy
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if post_json.get('categories'):
        for it in post_json['categories']:
            item['tags'].append(it['name'])
    if post_json.get('tags'):
        for it in post_json['tags']:
            item['tags'].append(it['name'])

    if post_json.get('summary'):
        item['summary'] = post_json['summary']

    item['content_html'] = ''
    if post_json.get('subtitle'):
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['subtitle'])

    if post_json.get('header_image'):
        item['_image'] = resize_image(post_json['header_image']['sources']['full'])
        item['content_html'] += utils.add_image(item['_image'])

    item['content_html'] += wp_posts.format_content(content_json['content'], item, site_json)
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    n = 0
    feed_items = []
    for post in next_data['pageProps']['posts']:
        post_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, post['permalink'])
        if save_debug:
            logger.debug('getting content for ' + post_url)
        item = get_content(post_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    #feed['title'] = soup.title.get_text()
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
