import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_image(image):
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('assetCustomSource'):
        captions.append(image['assetCustomSource'])
    elif image.get('assetCommonSource'):
        captions.append(image['assetCommonSource'])
    return utils.add_image(image['src'], ' | '.join(captions))


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
    if len(paths) > 0:
        query = '?slugs=' + '&slugs='.join(paths)
    next_url = '{}://{}/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, query)
    # print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if not el:
            logger.warning('unable to find __NEXT_DATA__ in ' + url)
            return None
        next_data = json.loads(el.string)
        if next_data['buildId'] != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = next_data['buildId']
            utils.update_sites(url, site_json)
        return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    article_json = next_data['pageProps']['article']

    i = article_json['seomatic']['metaJsonLdContainer'].find('{')
    j = article_json['seomatic']['metaJsonLdContainer'].rfind('}') + 1
    ld_json = json.loads(article_json['seomatic']['metaJsonLdContainer'][i:j])
    if save_debug:
        utils.write_file(ld_json, './debug/ld_json.json')

    item = {}
    item['id'] = article_json['uid']
    item['url'] = article_json['url']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['postDate']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if ld_json.get('dateModified'):
        dt = datetime.fromisoformat(ld_json['dateModified']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    authors = []
    for it in article_json['articleAuthors']:
        authors.append(it['title'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if article_json.get('articleCategory'):
        for it in article_json['articleCategory']:
            item['tags'].append(it['title'])

    if ld_json.get('description'):
        item['summary'] = ld_json['description']
    elif article_json.get('subTitle'):
        item['summary'] = article_json['subTitle']

    item['content_html'] = ''
    if article_json.get('subTitle'):
        item['content_html'] = '<p><em>' + article_json['subTitle'] + '</em></p>'

    if article_json.get('image'):
        item['_image'] = article_json['image'][0]['src']
        item['content_html'] += add_image(article_json['image'][0])

    for node in article_json['articleRichText']['nodes']:
        if node['type'] == 'paragraph' or node['type'] == 'heading':
            item['content_html'] += node['html']
        elif node['type'] == 'vizyBlock':
            if node['blockTypeHandle'] == 'media':
                item['content_html'] += add_image(node['singleMediaWithAspectRatio'][0]['media'])
            elif node['blockTypeHandle'] == 'gallery':
                for it in node['multipleMediaWithAspectRatio']:
                    item['content_html'] += add_image(it['media'])
            elif node['blockTypeHandle'] == 'youtube' or node['blockTypeHandle'] == 'twitter':
                item['content_html'] += utils.add_embed(node['externalLink'])
            elif node['blockTypeHandle'] == 'iframe':
                m = re.search(r'src="([^"]+)"', node['text'])
                item['content_html'] += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled vizyBlock type {} in {}'.format(node['blockTypeHandle'], item['url']))
        else:
            logger.warning('unhandled content node type {} in {}'.format(node['type'], item['url']))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    if 'rss.xml' in url:
        # https://cowboystatedaily.com/rss.xml
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    articles = []
    if next_data['pageProps'].get('topArticles'):
        for it in next_data['pageProps']['topArticles']:
            articles.append(it['url'])
    if next_data['pageProps'].get('paginatedArticles'):
        for it in next_data['pageProps']['paginatedArticles']:
            articles.append(it['url'])

    n = 0
    feed_items = []
    for article in articles:
        if save_debug:
            logger.debug('getting content for ' + article)
        item = get_content(article, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    if next_data['pageProps'].get('self'):
        feed['title'] = next_data['pageProps']['self']['name'] + ' | Cowboy State Daily'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
