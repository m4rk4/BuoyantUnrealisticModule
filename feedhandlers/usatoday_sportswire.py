import re
from bs4 import BeautifulSoup
from urllib.parse import urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    slug = paths[-1].split('.')[0]
    if split_url.path.startswith('/lists/'):
        post_url = '{}://{}/wp-json/wp/v2/listicle?slug={}'.format(split_url.scheme, split_url.netloc, slug)
    elif split_url.path.startswith('/gallery/'):
        post_url = '{}://{}/wp-json/wp/v2/fishburn_gallery?slug={}'.format(split_url.scheme, split_url.netloc, slug)
    else:
        post_url = '{}://{}/wp-json/wp/v2/posts?slug={}'.format(split_url.scheme, split_url.netloc, slug)

    post = utils.get_url_json(post_url)
    if not post:
        return None
    item = wp_posts.get_post_content(post[0], args, save_debug)
    if not item:
        return None

    if split_url.path.startswith('/lists/'):
        # Need to add the list items. Don't know if they are in the api.
        page_html = utils.get_url_html(url)
        if page_html:
            soup = BeautifulSoup(page_html, 'html.parser')
            for el in soup.find_all(id=re.compile(r'listicle-\d+')):
                it = el.find(class_='listicle-header-text')
                if it:
                    item['content_html'] += '<h3>{}</h3>'.format(it.get_text())
                it = el.find(class_='wp-caption-text')
                if it:
                    caption = it.get_text()
                else:
                    caption = ''
                it = el.find('img')
                if it:
                    if it.get('data-lazy-srcset'):
                        img_src = utils.image_from_srcset(it['data-lazy-srcset'], 1080)
                    else:
                        img_src = it['src']
                    it.parent.decompose()
                    item['content_html'] += utils.add_image(img_src, caption)
                it = el.find(class_='listicle-content')
                if it:
                    item['content_html'] += wp_posts.format_content(it.decode_contents(), item)
    elif split_url.path.startswith('/gallery/'):
        # Need to add the gallery items. Don't know if they are in the api.
        page_html = utils.get_url_html(url)
        if page_html:
            soup = BeautifulSoup(page_html, 'html.parser')
            for el in soup.find_all(class_='vertical-gallery'):
                it = el.find('img')
                if it:
                    if it.get('data-lazy-srcset'):
                        img_src = utils.image_from_srcset(it['data-lazy-srcset'], 1080)
                    else:
                        img_src = it['src']
                    it = el.find(class_='vertical-gallery--author')
                    if it:
                        caption = it.get_text().strip()
                    else:
                        caption = ''
                    item['content_html'] += utils.add_image(img_src, caption)
                it = el.find(class_='vertical-gallery--title')
                if it:
                    item['content_html'] += '<h4>{}</h4>'.format(it.get_text())
                it = el.find(class_='vertical-gallery--caption-hidden')
                if not it:
                    it = el.find(class_='vertical-gallery--caption-text')
                if it:
                    it.attrs = {}
                    it.name = 'p'
                    item['content_html'] += str(it)

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item
