import json, re
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    item = {}
    if 'embed' in paths:
        if 'playlists' in paths:
            page_html = utils.get_url_html(url)
            if page_html:
                soup = BeautifulSoup(page_html, 'lxml')
                el = soup.find('a', class_='c-playlist-item__card')
                if el:
                    m = re.search(r'-([a-f0-9]+)$', urlsplit(el['href']).path)
                    if m:
                        item = get_content('https://sketchfab.com/models/{}/embed'.format(m.group(1)), args, site_json, save_debug)
                        if item:
                            caption = '<a href="{}">View Sketchfab playlist</a>'.format(url)
                            item['content_html'] = utils.add_image(item['_image'], caption, link=url)
        else:
            embed_json = utils.get_url_json('https://sketchfab.com/oembed?url=' + quote_plus(url))
            if embed_json:
                item['id'] = paths[-2]
                item['url'] = url
                item['title'] = embed_json['title']
                item['author'] = {"name": embed_json['author_name']}
                item['_image'] = embed_json['thumbnail_url']
                caption = '<a href="{}">{}</a> by {}'.format(url, item['title'], item['author']['name'])
                item['content_html'] = utils.add_image(item['_image'], caption, link=url)
            else:
                page_html = utils.get_url_html(url)
                if page_html:
                    soup = BeautifulSoup(page_html, 'lxml')
                    el = soup.find(id='js-dom-data-prefetched-data')
                    if el:
                        data_json = json.loads(el.string.replace('&#34;', '"'))
                        if data_json['displayStatus'] == 'deleted':
                            item['content_html'] = '<div style="border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px; font-weight:bold;"><a href="{}">This Sketchfab 3D model has been deleted.</a></div>'.format(url)
                            return item
                item['content_html'] = '<div style="border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px; font-weight:bold;"><a href="{}">Error loading Sketchfab 3D model</a></div>'.format(url)
    else:
        item = wp_posts.get_content(url, args, site_json, save_debug)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
