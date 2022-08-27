import io, re, requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    #page_html = utils.get_url_html(url)
    r = requests.get(url)
    if r == None or (r != None and r.status_code != 200):
        return None
    page_html = r.text
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    soup = BeautifulSoup(page_html, 'html.parser')

    item = {}
    el = soup.find('meta', attrs={"name": "dc.identifier"})
    if el:
        item['id'] = el['content']

    item['url'] = r.url

    el = soup.find('meta', attrs={"property": "og:title"})
    if el:
        item['title'] = el['content']
    elif soup.title:
        item['title'] = soup.title.get_text()

    el = soup.find('meta', attrs={"property": "article:published_time"})
    if el:
        # Thursday, August 18, 2022 - 05:00
        # TODO: check timezone
        dt = datetime.strptime(el['content'], '%A, %B %d, %Y - %H:%M')
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
    el = soup.find('meta', attrs={"property": "article:modified_time"})
    if el:
        # Thursday, August 18, 2022 - 05:00
        # TODO: check timezone
        dt = datetime.strptime(el['content'], '%A, %B %d, %Y - %H:%M')
        item['date_modified'] = dt.isoformat()

    authors = []
    for el in soup.find_all('meta', attrs={"name": "citation_author"}):
        authors.append(el['content'])
    if not authors:
        for el in soup.find_all(class_='author-byline'):
            authors.append(el.get_text().replace('By ', ''))
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if '/newsletter/' in item['url']:
        item['_image'] = 'https://knowablemagazine.org/do/10.1146/knowable-080922-1/tocsearch/media/knowable-banner-500x288.jpeg'
    else:
        el = soup.find('meta', attrs={"property": "og:image"})
        if el:
            item['_image'] = el['content']

    item['tags'] = []
    el = soup.find('ul', class_='article-tags')
    if el:
        for it in el.find_all('li'):
            item['tags'].append(it.get_text().strip())

    el = soup.find('meta', attrs={"name": "description"})
    if el:
        item['summary'] = el['content']

    article_content = soup.find(class_='article-content')
    if not article_content:
        logger.warning('unable to find article-content in ' + url)
        return item

    for el in article_content.find_all('aside', class_='promo'):
        el.decompose()

    for el in article_content.find_all(id='newsletter-promo-item'):
        el.decompose()

    for el in article_content.find_all(class_='article-image'):
        if not el.name:
            continue
        images = el.find_all(class_='article-image')
        if images:
            for it in images:
                img = it.find('img')
                img_src = 'https://knowablemagazine.org' + img['src']
                captions = []
                cap = it.find(class_='caption')
                if cap:
                    captions.append(cap.get_text().strip())
                cap = it.find(class_='credit')
                if cap:
                    captions.append(cap.get_text().strip())
                new_html = utils.add_image(img_src, ' | '.join(captions))
                new_el = BeautifulSoup(new_html, 'html.parser')
                it.insert_after(new_el)
                it.decompose()
            el.unwrap()
        else:
            img = el.find('img')
            img_src = 'https://knowablemagazine.org' + img['src']
            captions = []
            cap = el.find(class_='caption')
            if cap:
                captions.append(cap.get_text().strip())
            cap = el.find(class_='credit')
            if cap:
                captions.append(cap.get_text().strip())
            new_html = utils.add_image(img_src, ' | '.join(captions))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    for el in article_content.find_all(class_='article-video'):
        it = el.find('iframe')
        if it:
            new_html = utils.add_embed(it['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled article-video in ' + url)

    for el in article_content.find_all('aside', class_='article-sidebar'):
        el.name = 'blockquote'
        el.attrs = {}
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

        for it in el.find_all(class_='article-sidebar-img'):
            img = it.find('img')
            img_src = 'https://knowablemagazine.org' + img['src']
            captions = []
            cap = el.find(class_='caption')
            if cap:
                captions.append(cap.get_text().strip())
                cap.decompose()
            cap = el.find(class_='source')
            if cap:
                captions.append(cap.get_text().strip())
                cap.decompose()
            new_html = utils.add_image(img_src, ' | '.join(captions))
            new_el = BeautifulSoup(new_html, 'html.parser')
            it.insert_after(new_el)
            it.decompose()

        it = el.find(class_='article-sidebar-text')
        if it:
            it.unwrap()

    for el in article_content.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    el = article_content.find(class_='article-text')
    if el:
        el.unwrap()

    el = article_content.find(class_='article-info')
    if el:
        el.decompose()

    item['content_html'] = ''
    el = soup.find(class_='article-subhead')
    if el:
        item['content_html'] += '<p><em>{}</em></p>'.format(el.decode_contents())

    el = soup.find(class_='article-hero')
    if el:
        img_src = ''
        m = re.search(r'background-image: url\((.*)\);', el['style'])
        if m:
            img_src = 'https://knowablemagazine.org' + m.group(1)
        if img_src:
            captions = []
            cap = soup.find(class_='article-photo-info-caption')
            if cap:
                captions.append(cap.get_text().strip())
            cap = soup.find(class_='article-photo-info-credit')
            if cap:
                captions.append(cap.get_text().strip())
            item['content_html'] += utils.add_image(img_src, ' | '.join(captions))
        else:
            logger.warning('unhandled article hero image in ' + url)

    item['content_html'] += article_content.decode_contents()
    return item


def get_feed(args, save_debug=False):
    # Generate feeds from search:
    # https://knowablemagazine.org/multisearch/do?sortBy=Earliest_desc&countTerms=true
    # Parse links manually
    feed_xml = utils.get_url_html(args['url'])
    tree = ET.parse(io.StringIO(feed_xml))
    root = tree.getroot()
    urls = []
    for item in root:
        if item.tag == '{http://purl.org/rss/1.0/}item':
            for child in item:
                if child.tag == '{http://purl.org/rss/1.0/}link':
                    urls.append(child.text)

    feed = utils.init_jsonfeed(args)
    #feed['title'] = soup.title.get_text()
    feed_items = []
    n = 0
    for url in urls:
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args and n == int(args['max']):
                    break

    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed