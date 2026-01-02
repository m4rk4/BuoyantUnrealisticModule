import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss, wp_posts_v2

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.strip('/').split('/')))
    if len(paths) == 0:
        path = '/index'
    else:
        path = split_url.path
        if path.endswith('/'):
            path = path[:-1]
    next_url = split_url.scheme + '://' + split_url.netloc + '/_next/data/' + site_json['buildId'] + '/' + path + '.json?postSlug=' + paths[-1]
    print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if el:
            next_data = json.loads(el.string)
            if next_data['buildId'] != site_json['buildId']:
                logger.debug('updating {} buildId'.format(split_url.netloc))
                site_json['buildId'] = next_data['buildId']
                utils.update_sites(url, site_json)
            return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.strip('/').split('/')))
    wp_post = utils.get_url_json(site_json['wpjson_path'] + site_json['posts_path'] + '?slug=' + paths[-1])
    if not wp_post:
        return None
    if save_debug:
        utils.write_file(wp_post[0], './debug/debug.json')

    return get_item(wp_post[0], args, site_json, save_debug)


def get_item(wp_post, args, site_json, save_debug):
    next_data = get_next_data(wp_post['link'], site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/next.json')
    page_props = next_data['pageProps']
    page_post = page_props['post']

    item = {}
    item['id'] = wp_post['id']
    item['url'] = wp_post['link']
    item['title'] = wp_post['title']['rendered']

    dt = datetime.fromisoformat(wp_post['date_gmt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if wp_post.get('modified_gmt'):
        dt = datetime.fromisoformat(wp_post['modified_gmt']).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()
        if page_post.get('revisions') and page_post['revisions'].get('nodes'):
            revision = None
            dt = datetime.fromisoformat(page_post['date'])
            for node in page_post['revisions']['nodes']:
                dt_rev = datetime.fromisoformat(node['date'])
                if dt_rev > dt:
                    dt = dt_rev
                    revision = node
            if revision:
                page_post = revision

    item['authors'] = []
    caption = ''
    for it in page_post['acfBylines']['bylines']:
        if it['bylineTitle'].startswith('Above'):
            caption = it['bylineName']
        elif it['bylineTitle'].startswith('Written'):
            item['authors'].insert(0, {"name": it['bylineName'].strip()})
        elif it['bylineTitle'].startswith('Photos'):
            item['authors'].append({"name": it['bylineName'].strip() + " (photos)"})
        else:
            item['authors'].append({"name": it['bylineTitle'].strip() + ' ' + it['bylineName'].strip()})
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    else:
        item['author'] = {
            "name": page_post['seo']['opengraphSiteName']
        }
        item['authors'].append(item['author'])

    item['tags'] = []
    if page_post.get('categories') and page_post['categories'].get('nodes'):
        item['tags'] += [x['name'] for x in page_post['categories']['nodes']]
    if page_post.get('tags') and page_post['tags'].get('nodes'):
        item['tags'] += [x['name'] for x in page_post['tags']['nodes']]

    item['content_html'] = ''
    if page_post.get('featuredImage') and page_post['featuredImage'].get('node'):
        item['image'] = page_post['featuredImage']['node']['sourceUrl']
        item['content_html'] += utils.add_image(item['image'], caption)

    emergent_site = site_json.copy()
    emergent_site.update({
        "clear_attrs": [
            {
                "attrs": {
                    "class": [
                        "wp-block-heading",
                        "wp-block-list"
                    ]
                }
            }
        ],
        "images": [
            {
                "attrs": {
                    "class": "wp-block-media-text__media"
                },
                "tag": "figure"
            }
        ],
        "rename": [
            {
                "old": {
                    "attrs": {
                        "class": "wp-block-media-text__content"
                    }
                },
                "new": {
                    "attrs": {
                        "style": "flex:1; min-width:256px;"
                    }
                }
            },
            {
                "old": {
                    "attrs": {
                        "class": "wp-block-media-text"
                    }
                },
                "new": {
                    "attrs": {
                        "style": "display:flex; flex-wrap:wrap; gap:1em;"
                    }
                }
            }
        ],
        "wrap": [
            {
                "attrs": {
                    "class": "wp-block-media-text__media"
                },
                "tag": "figure",
                "new": {
                    "attrs": {
                        "style": "flex:1; min-width:256px;"
                    },
                    "tag": "div"
                }
            }
        ]
    })

    item['content_html'] += wp_posts_v2.format_content(page_post['content'], item['url'], args, site_json=emergent_site)
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.strip('/').split('/')))

    wp_posts = None
    if len(paths) == 0:
        wp_posts =  utils.get_url_json(site_json['wpjson_path'] + site_json['posts_path'])
    elif 'category' in paths:
        next_data = get_next_data(url, site_json)
        if next_data:
            wp_posts =  utils.get_url_json(site_json['wpjson_path'] + site_json['posts_path'] + '?categories=' + str(next_data['pageProps']['category']['databaseId']))

    if not wp_posts:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    n = 0
    items = []
    for post in wp_posts:
        if save_debug:
            logger.debug('getting content for ' + post['link'])
        item = get_item(post, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args and n == int(args['max']):
                    break

    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
