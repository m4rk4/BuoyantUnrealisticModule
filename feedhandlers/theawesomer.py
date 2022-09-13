import json, re, requests
from bs4 import BeautifulSoup
from urllib.parse import urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    s = requests.session()
    page = s.get(url)
    soup = None
    yoast_json = None
    if page.status_code == 200:
        soup = BeautifulSoup(page.text, 'html.parser')
        el = soup.find('script', class_='yoast-schema-graph')
        if el:
            yoast_json = json.loads(el.string)
            if save_debug:
                utils.write_file(yoast_json, './debug/yoast.json')

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    slug = paths[0]
    post_url = '{}://{}/wp-json/wp/v2/posts?slug={}'.format(split_url.scheme, split_url.netloc, slug)
    r = s.get(post_url)
    if r.status_code != 200:
        return None

    post_json = r.json()
    post = post_json[0]
    if save_debug:
        utils.write_file(post, './debug/debug.json')

    args_copy = args.copy()
    args_copy['nolead'] = ''
    item = wp_posts.get_post_content(post, args_copy, save_debug)
    if not item:
        return None

    if soup:
        el = soup.find(class_='topmetasingle')
        if el:
            el.attrs = {}
            el.name = 'p'
            item['content_html'] += str(el)

    video = next((it for it in yoast_json['@graph'] if it['@type'] == 'VideoObject'), None)
    if video:
        item['content_html'] += utils.add_embed(video['embedUrl'])

    if post['_links'].get('wp:attachment'):
        r = s.get(post['_links']['wp:attachment'][0]['href'])
        if r.status_code == 200:
            media_json = r.json()
            if save_debug:
                utils.write_file(media_json, './debug/content.json')
            slugs = []
            for media in media_json:
                if media['media_type'] == 'image':
                    if re.search(r'youtube-video-(\w+)', media['slug']) or re.search(r'_t$', media['slug']):
                        continue
                    slugs.append(media['slug'])
            slugs.sort(key=lambda slug: list(map(int, re.findall(r'\d+$', slug)))[0])
            for slug in slugs:
                media = next((it for it in media_json if it['slug'] == slug), None)
                item['content_html'] += utils.add_image(media['source_url'], media['caption']['rendered'])

    item['content_html'] = re.sub(r'</(figure|table)><(figure|table)', r'</\1><br/><\2',item['content_html'])
    return item


def get_feed(args, save_debug=False):
    if '/wp-json/' in args['url']:
        return wp_posts.get_feed(args, save_debug)
    else:
        return rss.get_feed(args, save_debug, get_content)
