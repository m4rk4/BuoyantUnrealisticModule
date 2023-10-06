import base64, json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    if url.startswith('https'):
        split_url = urlsplit(url)
        slug = split_url.path
    elif url.startswith('/'):
        slug = url
    content_url = '{}/get_content?site={}&slug={}'.format(site_json['api_url'], site_json['site'], slug)
    content_json = utils.get_url_json(content_url)
    if not content_json:
        return None
    if save_debug:
        utils.write_file(content_json, './debug/debug.json')

    item = {}
    item['id'] = content_json['id']
    item['url'] = content_json['meta']['canonical']
    item['title'] = content_json['title']

    dt = datetime.fromisoformat(content_json['post_date']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": content_json['author']['name']}

    item['tags'] = []
    if content_json.get('category') and content_json['category'].get('name'):
        item['tags'].append(content_json['category']['name'])
    if content_json.get('sub_category') and content_json['sub_category'].get('name'):
        item['tags'].append(content_json['sub_category']['name'])
    if content_json['meta']['open_graph'].get('article:tag'):
        item['tags'] += content_json['meta']['open_graph']['article:tag']
    if not item.get('tags'):
        del item['tags']

    if content_json['meta'].get('description'):
        item['summary'] = content_json['meta']['description']

    item['content_html'] = ''
    if content_json.get('hero_images'):
        item['_image'] = content_json['hero_images']['original']
        item['content_html'] += utils.add_image(item['_image'])

    item['content_html'] += content_json['content']
    def sub_image(matchobj):
        m = re.search(r'src="([^"]+)"', matchobj.group(0))
        if m:
            img_src = m.group(1)
            m = re.search(r'\[\[imagecaption\|\|(.*?)\]\]', matchobj.group(0))
            if m:
                caption = m.group(1).strip()
            else:
                caption = ''
            return utils.add_image(img_src, caption)
        logger.warning('unknown image src ' + matchobj.group(0))
        return matchobj.group(0)
    item['content_html'] = re.sub(r'<p><img\s.*?</p>', sub_image, item['content_html'])

    def sub_widget(matchobj):
        w = matchobj.group(1).split('||')
        if w[0] == 'twitterwidget' or w[0] == 'twittewidget' or w[0] == 'instagramwidget' or w[0] == 'youtubewidget' or w[0] == 'tiktokwidget' or w[0] == 'facebookwidget':
            return utils.add_embed(w[1])
        elif w[0] == 'jwplayerwidget':
            return utils.add_embed('https://cdn.jwplayer.com/v2/media/' + w[2])
        else:
            logger.warning('unhandled widget ' + w[0])
            return matchobj.group(0)
    item['content_html'] = re.sub(r'<p>\[\[(.+?)\]\]?</p>', sub_widget, item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index.json'
        query = ''
    else:
        path = split_url.path
        if path.endswith('/'):
            path = path[:-1]
        path += '.json'
        query = '?category=' + paths[0]
        if len(paths) > 1:
            query += '&page=' + paths[1]
    next_url = '{}://{}/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, query)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if el:
            next_data = json.loads(el.string)
            if next_data['buildId'] != site_json['buildId']:
                site_json['buildId'] = next_data['buildId']
                utils.update_sites(url, site_json)
            next_data = next_data['props']
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    articles = []
    if next_data['pageProps'].get('articleList'):
        articles += next_data['pageProps']['articleList']
    if next_data['pageProps'].get('subCategory'):
        articles += next_data['pageProps']['subCategory']

    n = 0
    feed_items = []
    for article in articles:
        if save_debug:
            logger.debug('getting content for ' + article['slug'])
        item = get_content(article['slug'], args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    #feed['title'] = 'Stories - PGA of America'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
