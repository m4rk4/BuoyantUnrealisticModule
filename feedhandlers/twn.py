import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

from feedhandlers import dirt,jwplayer
import config, utils

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    page_html = utils.get_url_html(url)
    if page_html:
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if el:
            next_data = json.loads(el.string)
            return next_data['props']
    return None


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/next.json')

    if next_data['pageProps'].get('article'):
        article = next_data['pageProps']['article']
        item = {}
        item['id'] = article['id']
        item['url'] = next_data['pageProps']['shareUrl']
        item['title'] = article['headline']

        dt = datetime.fromisoformat(article['createdAt'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, date_only=True)
        if article.get('updatedAt'):
            dt = datetime.fromisoformat(article['updatedAt'])
            item['date_modified'] = dt.isoformat()

        item['author'] = {
            "name": article['author']['name']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

        item['tags'] = []
        if next_data['pageProps'].get('uiParentCategory'):
            item['tags'].append(next_data['pageProps']['uiParentCategory']['name'])
        if next_data['pageProps'].get('uiSubcategories'):
            item['tags'] = [x['name'] for x in next_data['pageProps']['uiSubcategories']]
        if article.get('keywords'):
            logger.warning('unhandled keywords in ' + item['url'])

        item['image'] = article['thumbnail']['url']

        item['content_html'] = ''
        if article.get('summary'):
            item['summary'] = article['summary']
            item['content_html'] += '<p><em>' + article['summary'] + '</em></p>'

        if 'embed' in args:
            item['content_html'] = utils.format_embed_preview(item)
            return item

        if next_data['pageProps'].get('articleBodyDocument'):
            item['content_html'] += dirt.render_content(next_data['pageProps']['articleBodyDocument'], None)
    elif next_data['pageProps']['adProduct'] == 'VIDEO':
        m = re.search(r'/video/([^/]+)', urlsplit(url).path)
        video = next_data['pageProps']['prefetchedQueryResponses']['video-' + m.group(1)]
        item = jwplayer.get_video_content(video['playlist'][0], args)
        item['url'] = 'https://www.theweathernetwork.com' + next_data['pageProps']['urlPath'].split('?')[0]
        if 'author' in item:
            del item['author']
            del item['authors']
        item['author'] = {
            "name": "The Weather Network"
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    if len(paths) == 0:
        lang = 'en'
    else:
        lang = paths[0]

    feed_items = []

    next_data = None
    if len(paths) == 1:
        # Homepage doesn't have NEXT_DATA, so get all news and videos separately
        next_data = get_next_data('https://www.theweathernetwork.com/{}/news'.format(lang), site_json)            
    elif 'news' in paths:
        next_data = get_next_data(url, site_json)
    if next_data:
        if save_debug:
            utils.write_file(next_data, './debug/feed.json')
        for article_list in next_data['pageProps']['articleLists']:
            for article in article_list['items']:
                article_url = next_data['pageProps']['urlPath']
                if article['subcategory']['parentCategory']['slug'] not in list(filter(None, article_url.split('/'))):
                    article_url += '/' + article['subcategory']['parentCategory']['slug']
                if article['subcategory']['slug'] not in list(filter(None, article_url.split('/'))):
                    article_url += '/' + article['subcategory']['slug']
                article_url += '/' + article['slug']
                article_url = 'https://www.theweathernetwork.com' + article_url
                if save_debug:
                    logger.debug('getting content from ' + article_url)
                item = get_content(article_url, args, site_json, save_debug)
                if item:
                    if utils.filter_item(item, args) == True:
                        feed_items.append(item)

    if len(paths) == 1:
        next_data = get_next_data('https://www.theweathernetwork.com/{}/video'.format(lang), site_json)            
    elif 'video' in paths:
        next_data = get_next_data(url, site_json)
    if next_data:
        if save_debug:
            utils.write_file(next_data, './debug/next.json')
        for playlist in next_data['pageProps']['videoGallery']:
            playlist_feed = jwplayer.get_feed(playlist['url'], args, {}, save_debug)
            if playlist_feed:
                for item in playlist_feed['items']:
                    item['url'] = 'https://www.theweathernetwork.com/{}/video/{}'.format(lang, item['id'])
                    if 'author' in item:
                        del item['author']
                        del item['authors']
                    item['author'] = {
                        "name": "The Weather Network"
                    }
                    item['authors'] = []
                    item['authors'].append(item['author'])
                    feed_items.append(item)

    feed = utils.init_jsonfeed(args)
    feed['title'] = next_data['pageProps']['metadata']['pageTitle'] + ' | The Weather Network'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
