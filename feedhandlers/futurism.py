import re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


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

    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        logger.debug('updating futurism.com buildId')
        page_html = utils.get_url_html(url)
        m = re.search(r'"buildId":"([^"]+)"', page_html)
        if m and m.group(1) != site_json['buildId']:
            site_json['buildId'] = m.group(1)
            utils.update_sites(url, site_json)
            next_url = '{}://{}/_next/data/{}/{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
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
    if next_data['pageProps'].get('post'):
        post = next_data['pageProps']['post']
        apollo_state = None
    elif '/videos/' in url:
        for key, val in next_data['pageProps']['initialApolloState']['ROOT_QUERY'].items():
            if key.startswith('video('):
                post = val
                apollo_state = next_data['pageProps']['initialApolloState']
                break
    else:
        logger.warning('unknown post data in ' + url)
        return None
    return get_item(post, apollo_state, url, args, site_json, save_debug)


def get_item(post_json, apollo_state, url, args, site_json, save_debug=False):
    item = {}
    item['id'] = post_json['databaseId']
    item['url'] = url

    if post_json.get('title'):
        item['title'] = post_json['title']
    elif post_json.get('title({"format":"RENDERED"})'):
        item['title'] = post_json['title({"format":"RENDERED"})']
    elif post_json.get('seo'):
        item['title'] = post_json['seo']['title']

    dt = datetime.fromisoformat(post_json['date'] + '+00:00')
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['modifiedGmt'] + '+00:00')
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": post_json['author']['node']['name']}

    item['tags'] = []
    if post_json.get('category'):
        item['tags'].append(post_json['category']['name'])
    if post_json.get('tags') and post_json['tags'].get('nodes'):
        if apollo_state:
            for tag in post_json['tags']['nodes']:
                it = apollo_state.get(tag['__ref'])
                if it:
                    item['tags'].append(it['name'])
        else:
            for tag in post_json['tags']['nodes']:
                item['tags'].append(tag['name'])

    item['content_html'] = ''
    if post_json.get('subtitle'):
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['subtitle'])

    if post_json.get('__typename') == 'Video':
        item['content_html'] += utils.add_embed(post_json['videoUrl'])

    if post_json.get('featuredImage') and post_json['featuredImage'].get('node'):
        item['_image'] = post_json['featuredImage']['node']['sourceUrl']
        if post_json['__typename'] != 'Video':
            item['content_html'] += utils.add_image(item['_image'], post_json.get('featuredImageAttribution'))

    if post_json.get('seo'):
        item['summary'] = post_json['seo']['description']

    soup = BeautifulSoup(post_json['content'], 'html.parser')
    for el in soup.find_all('figure'):
        img_src = ''
        it = el.find('img')
        if it:
            img_src = it['src']
        else:
            it = el.find('source')
            if it:
                img_src = utils.image_from_srcset(it['srcset'], 1000)
        if img_src:
            it = el.find('figcaption')
            if it:
                caption = it.decode_contents()
            else:
                caption = ''
            it = el.find('a')
            if it:
                link = it['href']
            else:
                link = ''
            new_html = utils.add_image(img_src, caption, link=link)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled figure in ' + item['url'])

    for el in soup.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        if el.parent and el.parent.name == 'p':
            el.parent.insert_after(new_el)
            el.parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all(attrs={"role": "complementary"}):
        el.decompose()

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(args['url'], site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    posts = None
    feed_title = ''
    if '/categories/' in args['url']:
        posts = next_data['pageProps']['initialData']['category']['posts']
        feed_title = 'Futurism | ' + next_data['pageProps']['initialData']['category']['name']
    elif '/tags/' in args['url']:
        posts = next_data['pageProps']['initialData']['tag']['posts']
        feed_title = 'Futurism | ' + next_data['pageProps']['initialData']['tag']['name']
    elif '/videos' in args['url']:
        for key, val in next_data['pageProps']['initialApolloState']['ROOT_QUERY'].items():
            if key.startswith('videos('):
                posts = val
                break
    else:
        for key, val in next_data['pageProps']['initialApolloState']['ROOT_QUERY'].items():
            if key.startswith('posts('):
                posts = val
                break
    if not posts:
        logger.warning('unknown feed posts for ' + args['url'])
        return None

    n = 0
    feed_items = []
    for post in posts['nodes']:
        url = 'https://futurism.com/'
        if post.get('vertical') and post['vertical'] != 'FUTURISM':
            url += post['vertical'].lower().replace('_', '-') + '/'
        elif post['__typename'] == 'Video':
            url += 'videos/'
        url += post['slug']
        if save_debug:
            logger.debug('getting content for ' + url)
        if post.get('content'):
            item = get_item(post, next_data['pageProps']['initialApolloState'], url, args, site_json, save_debug)
        else:
            item = get_content(url, args, site_json, save_debug)
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