import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://fossweekly.beehiiv.com/p/foss-weekly-34-another-risc-v-laptop-android-14-updates-from-peertube-and-thunderbird?_data=routes%2Fp%2F%24slug
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    api_url = url + '?_data=routes%2F{}%2F%24slug'.format(paths[0])
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')
    post_json = api_json['post']

    item = {}
    item['id'] = post_json['id']
    item['url'] = api_json['requestUrl']
    item['title'] = post_json['meta_default_title']

    dt = datetime.fromisoformat(post_json['created_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['updated_at'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in post_json['authors']:
        authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if post_json.get('image_url'):
        item['_image'] = post_json['image_url']

    if post_json.get('meta_default_description'):
        item['summary'] = post_json['meta_default_description']

    item['content_html'] = ''
    if post_json.get('web_subtitle'):
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['web_subtitle'])

    soup = BeautifulSoup(post_json['html'], 'lxml')
    content = soup.find(id='content-blocks')
    if content:
        if save_debug:
            utils.write_file(content.decode_contents(), './debug/debug.html')
        for el in content.find_all(['script', 'style']):
            el.decompose()

        for el in content.find_all(recursive=False):
            it = el.find(class_='button')
            if not it:
                it = el.find('button')
            if it:
                if re.search(r'Subscribe', it.get_text().strip(), flags=re.I):
                    el.decompose()
                    continue

            it = el.find(class_='twitter-wrapper')
            if it:
                links = it.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
                continue

            it = el.find('iframe')
            if it:
                new_html = utils.add_embed(it['src'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
                continue

            it = el.find('img')
            if it and it.get('style'):
                m = re.search(r'width:\s?(\d+)%', it['style'])
                if m and int(m.group(1)) >= 50:
                    img_src = it['src']
                    if it.find('small'):
                        caption = it.get_text().strip()
                    else:
                        caption = ''
                    if it.parent and it.parent.name == 'a':
                        link = it.parent['href']
                    else:
                        link = ''
                    new_html = utils.add_image(img_src, caption, link=link)
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_after(new_el)
                    el.decompose()
                    continue

            if el.name == 'div':
                if el.get('style'):
                    m = re.search(r'background-color:\s?([^;]+)', el['style'])
                    if m:
                        if m.group(1) != 'transparent':
                            continue
                el.unwrap()

        for el in content.find_all(['p', 'h1', 'h2', 'h3', 'ol', 'ul', 'li']):
            el.attrs = {}

        for el in content.find_all('div', attrs={"style": re.compile(r'border-top:\s?[^;]+dashed')}):
            el.insert_after(soup.new_tag('hr'))
            el.decompose()

        for el in content.find_all('a', href=re.compile(r'flight\.beehiiv\.net/v2/clicks')):
            link = utils.get_redirect_url(el['href'])
            el.attrs = {}
            el['href'] = link

        item['content_html'] += content.decode_contents()
    return item


def get_feed(url, args, site_json, save_debug=False):
    #
    if url.startswith('https://rss.beehiiv.com'):
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    split_url = urlsplit(url)
    api_url = '{}://{}?_data=routes%2Findex'.format(split_url.scheme, split_url.netloc)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    feed = utils.init_jsonfeed(args)
    for post in api_json['paginatedPosts']['posts']:
        url = '{}://{}/p/{}'.format(split_url.scheme, split_url.netloc, post['slug'])
        if save_debug:
            logger.debug('getting content from ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed['items'] = feed_items.copy()
    return feed
