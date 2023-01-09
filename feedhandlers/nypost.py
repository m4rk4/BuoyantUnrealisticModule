import json, re
from bs4 import BeautifulSoup
from datetime import datetime

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    soup = BeautifulSoup(page_html, 'html.parser')
    ld_json = None
    for el in soup.find_all('script', type='application/ld+json'):
        ld_json = json.loads(el.string)
        if ld_json['@type'] == 'NewsArticle':
            break
        else:
            ld_json = None
    if not ld_json:
        return None
    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    item = {}
    item['id'] = ld_json['mainEntityOfPage']
    item['url'] = ld_json['url']
    item['title'] = ld_json['headline']

    dt = datetime.fromisoformat(ld_json['datePublished'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(ld_json['dateModified'])
    item['date_modified'] = dt.isoformat()

    authors = []
    if ld_json.get('author'):
        for it in ld_json['author']:
            authors.append(it['name'])
    elif ld_json.get('creator'):
        for it in ld_json['creator']:
            authors.append(it['name'])
    elif ld_json.get('publisher'):
        authors.append(ld_json['publisher']['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if ld_json.get('keywords'):
        item['tags'] = ld_json['keywords'].copy()

    if ld_json.get('image'):
        item['_image'] = ld_json['image']['url']
    elif ld_json.get('thumbnailUrl'):
        item['_image'] = ld_json['thumbnailUrl']

    item['content_html'] = ''

    if '/video/' in item['url']:
        el = soup.find(id=re.compile(r'jw-player'))
        if el:
            m = re.search(r'jw-player-[^-]+-([^-]+)', el['id'])
            if m:
                item['content_html'] += utils.add_embed('https://cdn.jwplayer.com/v2/media/' + m.group(1))
                return item
        logger.warning('unhandled video url in ' + item['url'])
        return item

    el = soup.find(class_='featured-image__wrapper')
    if not el:
        el = soup.find(id='featured-image-wrapper')
    if el:
        lede = ''
        if el.find(class_='featured-image__figure'):
            img = el.find('img')
            if img:
                if img.get('srcset'):
                    img_src = utils.image_from_srcset(img['srcset'], 1024)
                else:
                    img_src = img['src']
                captions = []
                it = el.find(class_='credit')
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())
                    it.decompose()
                it = el.find('figcaption')
                if it and it.get_text().strip():
                    captions.insert(0, it.get_text().strip())
                lede = utils.add_image(img_src, ' | '.join(captions))
        elif el.find(class_='embed-youtube'):
            it = el.find('iframe')
            if it:
                lede = utils.add_embed(it['src'])
        elif el.find(class_='nyp-video-player'):
            print('nyp-video-player')
            it = el.find(id=re.compile(r'jw-player'))
            if it:
                m = re.search(r'jw-player-[^-]+-([^-]+)', it['id'])
                if m:
                    lede = utils.add_embed('https://cdn.jwplayer.com/v2/media/' + m.group(1))
        elif el.find(class_='s2nFriendlyFrame'):
            it = el.find('script', attrs={"data-type": "s2nScript"})
            if it:
                lede = utils.add_embed(it['src'])
        if lede:
            item['content_html'] += lede
        else:
            logger.warning('unhandled featured-image in ' + item['url'])
    elif item.get('_image'):
        item['content_html'] += utils.add_image(item['_image'])

    content = soup.find(class_='entry-content')
    if content:
        for slideshow in content.find_all(class_='inline-slideshow'):
            new_html = ''
            for slide in slideshow.find_all(class_='inline-slideshow__slide'):
                slide_html = ''
                if 'inline-slideshow__slide--ad-slide' in slide['class']:
                    continue
                fig = slide.find('figure')
                if fig:
                    img = fig.find('img')
                    if img:
                        if img.get('srcset'):
                            img_src = utils.image_from_srcset(img['srcset'], 1024)
                        else:
                            img_src = img['src']
                        captions = []
                        it = fig.find(class_='meta--caption')
                        if it and it.get_text().strip():
                            captions.append(it.get_text().strip())
                        it = fig.find(class_='meta--byline')
                        if it and it.get_text().strip():
                            captions.append(it.get_text().strip())
                        slide_html += utils.add_image(img_src, ' | '.join(captions))
                if slide_html:
                    new_html += slide_html
                else:
                    logger.warning('unhandled inline-slideshow__slide in ' + item['url'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                slideshow.insert_after(new_el)
                slideshow.decompose()

        for el in content.find_all(class_='more-on'):
            if el.parent and el.parent.name == 'div':
                el.parent.decompose()
            else:
                el.decompose()

        content_html = content.decode_contents()
        if save_debug:
            utils.write_file(content_html, './debug/debug.html')
        item['content_html'] += wp_posts.format_content(content_html, item)
        item['content_html'] = re.sub(r'</(div|figure|table)>\s*<(div|figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)