import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wp_posts_v2

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    split_url = urlsplit(img_src)
    paths = list(filter(None, split_url.path.split('/')))
    return 'https://images.deadspin.com/tr:w-{}/{}'.format(width, paths[-1])


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
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
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/next.json')
    page_props = next_data['pageProps']
    page_post = page_props['post']

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    wp_post = utils.get_url_json(site_json['wpjson_path'] + site_json['posts_path'] + '?slug=' + paths[-1])
    if wp_post:
        post_json = wp_post[0]
        if save_debug:
            utils.write_file(next_data, './debug/debug.json')

    item = {}
    item['id'] = post_json['id']
    item['url'] = 'https://' + split_url.netloc + split_url.path

    dt = datetime.fromisoformat(post_json['date_gmt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if post_json.get('modified_gmt'):
        dt = datetime.fromisoformat(post_json['modified_gmt']).replace(tzinfo=timezone.utc)
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

    item['title'] = post_json['title']['rendered']

    item['authors'] = []
    caption = ''
    for it in page_post['acfBylines']['bylines']:
        if it['bylineTitle'].startswith('Above'):
            caption = it['bylineName']
        elif it['bylineTitle'].startswith('Written'):
            item['authors'].append({"name": it['bylineName'].strip()})
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

    site_copy = site_json.copy()
    site_copy['clear_attrs'] = [
        {
            "attrs": {
                "class": [
                    "wp-block-heading",
                    "wp-block-list"
                ]
            }
        }
    ]

    item['content_html'] += wp_posts_v2.format_content(page_post['content'], item['url'], args, site_json=site_copy)
    return item