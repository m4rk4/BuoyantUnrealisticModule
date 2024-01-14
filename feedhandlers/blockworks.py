import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import wp_posts

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
        params = ''
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
        params = '?slug=' + paths[-1]
    path += '.json'
    next_url = '{}://{}/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, params)
    print(next_url)
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
    if next_data['pageProps'].get('article'):
        return get_article(next_data['pageProps']['article'], args, site_json, save_debug)
    elif next_data['pageProps'].get('episode'):
        return get_episode(next_data['pageProps']['episode'], next_data['pageProps']['podcast'], args, site_json, save_debug)


def get_article(article_json, args, site_json, save_debug):
    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['meta']['canonical']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['meta']['article_published_time'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json['meta'].get('article_modified_time'):
        dt = datetime.fromisoformat(article_json['meta']['article_modified_time'])
        item['date_modified'] = dt.isoformat()

    authors = []
    for it in article_json['authors']:
        authors.append(it['title'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if article_json.get('categories'):
        item['tags'] += article_json['categories'].copy()
    if article_json.get('tags'):
        item['tags'] += article_json['tags'].copy()
    if not item.get('tags'):
        del item['tags']

    item['summary'] = article_json['meta']['description']

    item['content_html'] = ''
    if article_json.get('thumbnail'):
        item['_image'] = article_json['thumbnail']['url']
        if article_json['thumbnail'].get('caption'):
            caption = re.sub(r'^<p>(.*?)</p>$', r'\1', article_json['thumbnail']['caption'])
        else:
            caption = ''
        item['content_html'] += utils.add_image(item['_image'], caption)

    elif article_json.get('imageUrl'):
        item['_image'] = article_json['imageUrl']
        item['content_html'] += utils.add_image(item['_image'])

    item['content_html'] += wp_posts.format_content(article_json['content'], item, site_json)
    return item


def get_episode(episode_json, podcast_json, args, site_json, save_debug):
    item = {}
    item['id'] = episode_json['id']
    item['url'] = 'https://blockworks.co/podcast/{}/{}'.format(podcast_json['slug'], episode_json['id'])
    item['title'] = episode_json['title']

    dt = datetime.fromisoformat(episode_json['pubdate']).replace(tzinfo=pytz.timezone(episode_json['pubdateTimezone']))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if episode_json.get('updatedAt'):
        dt = datetime.fromisoformat(episode_json['updatedAt']).replace(tzinfo=pytz.timezone(episode_json['pubdateTimezone']))
        item['date_modified'] = dt.isoformat()

    item['author'] = {"name": podcast_json['title']}

    if episode_json.get('podcastItunesCategories'):
        item['tags'] = episode_json['podcastItunesCategories'].copy()

    if episode_json.get('summary'):
        item['summary'] = episode_json['summary']

    if episode_json.get('imageFile'):
        item['_image'] = episode_json['imageFile']
        poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
    elif podcast_json.get('imageFile'):
        item['_image'] = podcast_json['imageFile']
        poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
    else:
        poster = '{}/image?height=128&width=128&overlay=audio'.format(config.server)

    item['_audio'] = episode_json['audioFile']
    attachment = {}
    attachment['url'] = item['_audio']
    attachment['mime_type'] = 'audio/mpeg'
    item['attachments'] = []
    item['attachments'].append(attachment)

    duration = utils.calc_duration(float(episode_json['duration']))

    item['content_html'] = '<table><tr><td style="width:128px;"><a href="{}"><img src="{}"></a></td>'.format(item['_audio'], poster)
    item['content_html'] += '<td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold; padding-bottom:8px;"><a href="{}">{}</a></div>'.format(item['url'], item['title'])
    item['content_html'] += '<div style="padding-bottom:8px;">By <a href="https://blockworks.co/podcast/{}">{}</a></div>'.format(podcast_json['slug'], podcast_json['title'])
    item['content_html'] += '<div style="font-size:0.9em;">{} &bull; {}</div></td></tr></table>'.format(item['_display_date'], duration)

    if not 'embed' in args and item.get('summary'):
        item['content_html'] += '<p>{}</p>'.format(item['summary'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    articles = []
    episodes = []
    podcasts = []
    podcast = {}
    if next_data['pageProps'].get('articles'):
        articles = next_data['pageProps']['articles']
    elif next_data['pageProps'].get('readMoreArticles'):
        articles = next_data['pageProps']['readMoreArticles']
    elif next_data['pageProps'].get('episodes'):
        episodes = next_data['pageProps']['episodes']
        podcast = next_data['pageProps']['podcast']
    elif next_data['pageProps'].get('podcasts'):
        podcasts = next_data['pageProps']['podcasts']
    else:
        logger.warning('unknown articles in feed ' + url)
        return None

    n = 0
    feed_items = []
    for article in articles:
        if save_debug:
            logger.debug('getting content for ' + article['meta']['canonical'])
        item = get_article(article, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    for episode in episodes:
        if save_debug:
            ep_url = 'https://blockworks.co/podcast/{}/{}'.format(podcast['slug'], episode['id'])
            logger.debug('getting content for ' + ep_url)
        item = get_episode(episode, podcast, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    for podcast in podcasts:
        podcast_url = 'https://blockworks.co/podcast/{}'.format(podcast['slug'])
        if save_debug:
            logger.debug('getting content for ' + podcast_url)
        podcast_feed = get_feed(podcast_url, args, site_json, save_debug)
        if podcast_feed:
            feed_items += podcast_feed['items'].copy()

    feed = utils.init_jsonfeed(args)
    # feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
