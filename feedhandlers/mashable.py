import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone

from feedhandlers import rss
import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    soup = BeautifulSoup(page_html, 'lxml')
    ld_json = None
    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        ld_json = json.loads(el.string)
        if ld_json.get('@type') and (ld_json['@type'] == 'Article' or ld_json['@type'] == 'NewsArticle'):
            break
        else:
            ld_json = None
    if not ld_json:
        logger.warning('unable to find ld+json in ' + url)
        return None

    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    item = {}
    item['id'] = ld_json['mainEntityOfPage']
    item['url'] = ld_json['mainEntityOfPage']
    item['title'] = ld_json['headline']

    dt = datetime.fromisoformat(ld_json['datePublished']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if ld_json.get('dateModified'):
        dt = datetime.fromisoformat(ld_json['dateModified']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['authors'] = [{"name": x['name']} for x in ld_json['author']]
    item['author'] = {
        "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
    }

    if ld_json.get('image'):
        if isinstance(ld_json['image'], list):
            item['image'] = ld_json['image'][0]['url']
        elif isinstance(ld_json['image'], dict):
            item['image'] = ld_json['image']['url']
        else:
            item['image'] = ld_json['image']

    item['content_html'] = ''
    if ld_json.get('description'):
        item['summary'] = ld_json['description']
        item['content_html'] += '<p><em>' + ld_json['description'] + '</em></p>'

    body = soup.find('section', attrs={"data-ga-module": ["content-body", "content_body"]})
    if body:
        img = body.find('img')
        if img and not img.find_parent('article'):
            if img.get('srcset'):
                img_src = utils.image_from_srcset(img['srcset'], 1400)
            else:
                img_src = img['src']
            captions = []
            el = img.find_next_sibling('div')
            if el:
                for it in el.find_all('span'):
                    captions.append(it.decode_contents())
            item['content_html'] += utils.add_image(img_src, ' | '.join(captions))

    article = soup.find('article', id='article')
    if not article:
        article = soup.find('article', class_='editor-content')
    if article:
        for el in article.find_all('section'):
            if el.get('data-ga-category') and el['data-ga-category'] == 'newsletters':
                el.decompose()
            elif el.find('span', string='Topics'):
                item['tags'] = []
                for it in el.find_all('a'):
                    item['tags'].append(it.get_text().strip())
                el.decompose()

        for el in article.find_all(class_='related-stories'):
            el.decompose()

        for el in article.find_all('div', recursive=False):
            if re.search(r'^SEE ALSO', el.get_text().strip()):
                el.decompose()
            elif el.find(attrs={"data-ga-item": "mashable_games_general"}):
                el.decompose()

        for el in article.select('div:has(> div[id*="video-container-"])'):
            it = el.find(id=re.compile(r'video-container-'))
            m = re.search(r'video-container-(.*)', it['id'])
            new_html = utils.add_embed('https://www.youtube.com/watch?v=' + m.group(1))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

        for el in article.find_all(class_='eloquent-imagery-image'):
            new_html = ''
            img = el.find('img')
            if img:
                if img.get('srcset'):
                    img_src = utils.image_from_srcset(img['srcset'], 1400)
                else:
                    img_src = img['src']
                captions = []
                divs = el.find_all('div', recursive=False)
                if divs and not divs[-1].img:
                    for it in divs[-1].find_all('span'):
                        captions.append(it.decode_contents())
                new_html = utils.add_image(img_src, ' | '.join(captions))
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled eloquent-imagery-image in ' + item['url'])

        for el in article.find_all('script'):
            el.decompose()

        item['content_html'] += article.decode_contents()
    return item


def get_feed(url, args, site_json, save_debug=False):
    n = 0
    items = []
    feed = rss.get_feed(url, args, site_json, save_debug)
    for feed_item in feed['items']:
        item = get_content(feed_item['url'], args, site_json, save_debug)
        if feed_item.get('tags'):
            item['tags'] = feed_item['tags'].copy()
        if utils.filter_item(item, args) == True:
            items.append(item)
            n += 1
            if 'max' in args:
                if n == int(args['max']):
                    break
    feed['items'] = items.copy()
    return feed
