import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit, unquote_plus

import utils
from feedhandlers import rss, twitter

import logging

logger = logging.getLogger(__name__)


def get_next_data(url):
    page_html = utils.get_url_html(url)
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', string=re.compile(r'^__NEXT_DATA__'))
    if not el:
        logger.warning('unable to find NEXT_DATA in ' + url)
        return None
    next_data = re.sub(r';__NEXT_LOADED_PAGES__.*', '', el.string[16:])
    return json.loads(next_data)




def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url)
    if not next_data:
        return None
    return get_article_content(next_data['props']['pageProps']['initialProps']['article'], args, site_json, save_debug)

def get_article_content(article_json, args, site_json, save_debug=False):
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['share_url']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['published_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['updated_at'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    if article_json.get('authors'):
        authors = []
        for it in article_json['authors']:
            authors.append(it['name'])
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif article_json.get('byline'):
        item['author'] = {"name": article_json['byline']}

    if article_json.get('resource_tags'):
        item['tags'] = []
        for it in article_json['resource_tags']:
            item['tags'].append(it['name'])

    item['content_html'] = ''
    if article_json.get('feature_image_url'):
        item['_image'] = article_json['feature_image_url']
        if article_json.get('feature_image_attribution'):
            caption = article_json['feature_image_attribution']
        else:
            caption = ''
        item['content_html'] += utils.add_image(item['_image'], caption)

    if article_json.get('abstract'):
        item['summary'] = article_json['abstract']

    soup = BeautifulSoup(article_json['content'], 'html.parser')
    for el in soup.find_all('figure', class_='article-segment--image'):
        it = el.find('img')
        if it.get('srcset'):
            img_src = utils.image_from_srcset(it['srcset'], 1080)
        elif it.get('src'):
            img_src = it['src']
        captions = []
        it = el.find(class_='article-segment--image-attribution')
        if it:
            captions.append(it.get_text().strip())
            it.decompose()
        it = el.find('figcaption')
        if it:
            captions.insert(0, it.get_text().strip())
        captions = list(filter(None, captions))
        new_html = utils.add_image(img_src, ' | '.join(captions))
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('figure', class_='article-segment--embed'):
        new_html = ''
        it = el.find('iframe')
        if it:
            new_html = utils.add_embed(it['src'])
        elif el.find(class_='twitter-tweet'):
            it = el.find_all('a')
            new_html = utils.add_embed(it[-1]['href'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled article-segment--embed in ' + item['url'])

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug):
    if args['url'].endswith('.rss'):
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    next_data = get_next_data(args['url'])
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    content = None
    feed_title = ''
    if next_data['page'] == '/league_river':
        if next_data['props']['pageProps']['initialState']['pageData'].get('currentLeague'):
            feed_title = 'theScore | ' + next_data['props']['pageProps']['initialState']['pageData']['currentLeague']['full_name']
            content = next_data['props']['pageProps']['initialState']['pageData']['riverData']['relatedContent']
    elif next_data['page'] == '/team':
        feed_title = 'theScore | ' + next_data['props']['pageProps']['initialState']['teamData']['data']['full_name']
        split_url = urlsplit(args['url'])
        api_url = 'https://api.thescore.com' + split_url.path
        api_json = utils.get_url_json(api_url)
        if api_url:
            content_url = 'https://rich-content.thescore.com/content_cards?resource_uris={}&limit=15'.format(api_json['resource_uri'])
            content_cards = utils.get_url_json(content_url)
            if content_cards:
                content = content_cards['content_cards']
                if save_debug:
                    utils.write_file(content_cards, './debug/feed.json')
    if not content:
        logger.warning('unable to find feed content in ' + args['url'])
        return None

    n = 0
    feed_items = []
    for article in content:
        item = None
        if article['type'] == 'theScoreArticleCard':
            if save_debug:
                logger.debug('getting content for ' + article['data']['share_url'])
            item = get_article_content(article['data'], args, site_json, save_debug)
        elif article['type'] == 'TwitterVideoCard':
            if save_debug:
                logger.debug('getting content for ' + article['data']['url'])
            item = twitter.get_content(article['data']['url'], args, {}, save_debug)
            item['title'] = article['caption']
        elif article['type'] == 'SourcedArticleCard':
            if save_debug:
                logger.debug('getting content for ' + article['data']['url'])
            item = utils.get_content(article['data']['url'], args, site_json, save_debug)
        else:
            # TODO: AmpStoryCard https://www.thescore.com/story/23042062
            logger.warning('unhandled article type ' + article['type'])
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    if feed_title:
        feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed