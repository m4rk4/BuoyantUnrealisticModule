import json, re
from bs4 import BeautifulSoup
from urllib.parse import urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    post = None
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('link', attrs={"type": "application/json", "href": re.compile(r'wp-json')})
    if el:
        post_url = el['href']
        post = utils.get_url_json(post_url)
    if not post:
        logger.warning('failed to get post data from ' + url)
        return None
    item = wp_posts.get_post_content(post, args, site_json, save_debug)
    content = BeautifulSoup(item['content_html'], 'html.parser')
    lede_fig = content.find('figure')

    if post['type'] == 'ftm_video':
        m = re.search(r"media_id: '([^']+)'", page_html)
        if m:
            new_html = utils.add_embed('https://cdn.jwplayer.com/v2/media/' + m.group(1))
            new_el = BeautifulSoup(new_html, 'html.parser')
            lede_fig.insert_before(new_el)
            lede_fig.decompose()
            lede_fig = content.find('figure')

    ld_json = None
    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        ld_json = json.loads(el.string)
        if ld_json['@type'] == 'Article':
            break
        ld_json = None
    if ld_json:
        item['author']['name'] = ld_json['author']['name']

    if item.get('summary'):
        new_html = '<p><em>{}</em></p>'.format(item['summary'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        lede_fig.insert_before(new_el)

    el = soup.find('div', string=re.compile(r'Key Takeaways'))
    if el:
        it = el.parent.find('ul')
        if it:
            new_html = '<h3>Key Takeaways</h3>' + str(it)
            new_el = BeautifulSoup(new_html, 'html.parser')
            lede_fig.insert_before(new_el)

    el = soup.find(class_='lead-in-text')
    if el:
        new_el = soup.new_tag('hr')
        lede_fig.insert_after(new_el)
        el.attrs = {}
        el['style'] = 'font-style:italic;'
        lede_fig.insert_after(el)

    item['content_html'] = str(content)
    return item


def get_feed(url, args, site_json, save_debug=False):
    if '/wp-json/' in args['url']:
        return wp_posts.get_feed(url, args, site_json, save_debug)
    else:
        return rss.get_feed(url, args, site_json, save_debug, get_content)
