import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

from feedhandlers import rss
import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    article_html = utils.get_url_html(url)
    if not article_html:
        return None
    soup = BeautifulSoup(article_html, 'html.parser')

    item = {}
    m = re.search(r'-(\d+)\.shtml', url)
    item['id'] = int(m.group(1))
    item['url'] = soup.find('link', rel='canonical').get('href')
    item['title'] = soup.title.get_text()

    date = soup.find('meta', property='og:article:published_time').get('content')
    date = re.sub(r'\+(\d\d)(\d\d)$', r'+\1:\2', date)
    dt = datetime.fromisoformat(date)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {}
    item['author']['name'] = soup.find('meta', attrs={"name": "author"}).get('content')

    tags = soup.find('meta', attrs={"name": "keywords"}).get('content')
    item['tags'] = [tag.strip() for tag in tags.split(',')]

    item['_image'] = soup.find('meta', property='og:image').get('content')

    intro = soup.find('p', class_='intro')
    if intro:
        item['summary'] = intro.get_text()
    else:
        item['summary'] = soup.find('meta', property='og:description').get('content')

    item['content_html'] = ''

    if '/news/' in url:
        article = soup.find('article', itemprop='articleBody')
        if not article:
            logger.warning('unable to find articleBody in ' + url)
            return item
        lede = soup.find(class_='main-image')
        if lede:
            img_src = lede.a['href']
            captions = []
            if lede.img.get('title'):
                captions.append(lede.img['title'])
            if lede.img.get('data-description'):
                captions.append(lede.img['data-description'])
            item['content_html'] += utils.add_image(img_src, ' | '.join(captions))

    elif '/reviews/' in url:
        article = soup.find('article', itemprop='reviewBody')
        if not article:
            logger.warning('unable to find reviewBody in ' + url)
            return item

        lede = soup.find(class_='posrel')
        if lede:
            el = lede.find(class_='bbgallery')
            if el:
                img_src = el.a['href']
                captions = []
                if el.img.get('title'):
                    captions.append(el.img['title'])
                if el.img.get('data-description'):
                    captions.append(el.img['data-description'])
                item['content_html'] += utils.add_image(img_src, ' | '.join(captions))
            el = lede.find(class_='rc_infobox')
            if el:
                it = el.find(class_='summary')
                if it:
                    it.name = 'h4'
                    it.string = it.get_text().title()
                    it.attrs = {}
                item['content_html'] += el.decode_contents()
        if intro:
            item['content_html'] += '<strong>{}</strong>'.format(intro.get_text())

    for el in article.find_all(class_=re.compile(r'bbgallery|galart\d$')):
        # Mid-article galleries/images are usually part of the main article gallery
        if False:
            it = el.find(class_=re.compile(r'galart\d_main'))
            img_src = re.sub(r'/fitted/\d+x\d+/|/newsrsz/', '/news2/', it.img['src'])
            caption = it.img.get('title')
            gallery_html = utils.add_image(img_src, caption) + '<br/>'
            for it in el.find_all(class_=re.compile(r'galart\d_img')):
                img_src = re.sub(r'/fitted/\d+x\d+/|/newsrsz/', '/news2/', it.img['src'])
                caption = it.get('data-title')
                gallery_html += utils.add_image(img_src, caption) + '<br/>'
            el.insert_after(BeautifulSoup(gallery_html, 'html.parser'))
        el.decompose()

    for el in article.find_all(class_='videospot'):
        if el.a and el.a.get('data-embed'):
            el.insert_after(BeautifulSoup(utils.add_embed(el.a['data-embed']), 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled videospot in ' + url)

    for el in article.find_all('meta'):
        el.decompose()

    for el in article.find_all(class_=re.compile(r'intro|mgbot_\d\d|mgtop_\d\d|revconcs')):
        el.attrs = {}

    item['content_html'] += article.decode_contents()

    gallery = soup.find('script', id='schema-gallery-data')
    if gallery:
        gallery_json = json.loads(gallery.string)
        item['content_html'] += '<h3>Photo Gallery ({} images)</h3>'.format(len(gallery_json['associatedMedia'][0]))
        for image in gallery_json['associatedMedia'][0]:
            item['content_html'] += utils.add_image(image['contentUrl'], image['text']) + '<br/>'

    return item

def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
