import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    soup = BeautifulSoup(page_html, 'lxml')
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
    item['id'] = ld_json['mainEntityOfPage']['@id']
    item['url'] = ld_json['mainEntityOfPage']['url']
    item['title'] = ld_json['headline']

    dt = datetime.fromisoformat(ld_json['datePublished'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(ld_json['dateModified'])
    item['date_modified'] = dt.isoformat()

    authors = []
    if ld_json.get('author'):
        if isinstance(ld_json['author'], list):
            for it in ld_json['author']:
                authors.append(it['name'])
        else:
            authors.append(ld_json['author']['name'])
    elif ld_json.get('publisher'):
        authors.append(ld_json['publisher']['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if ld_json.get('keywords'):
        item['tags'] = ld_json['keywords'].copy()
    else:
        el = soup.find(class_='articleTopicsRow')
        if el:
            item['tags'] = []
            for it in el.find_all('a'):
                item['tags'].append(it.get_text())

    if ld_json.get('image'):
        item['_image'] = ld_json['image']['url']
    elif ld_json.get('thumbnailUrl'):
        item['_image'] = ld_json['thumbnailUrl']

    if ld_json.get('description'):
        item['summary'] = ld_json['description']

    item['content_html'] = ''
    el = soup.find('ul', class_='mol-bullets-with-font')
    if el and el.parent and el.parent.get('class') and 'article-text' in el.parent['class']:
        item['content_html'] += str(el)

    if item.get('_image'):
        item['content_html'] += utils.add_image(item['_image'])

    if 'embed' in args:
        item['content_html'] = '<div style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(urlsplit(item['url']).netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}" target="_blank">Read</a></p></div></div><div>&nbsp;</div>'.format(config.server, quote_plus(item['url']))
        return item

    body = soup.find(attrs={"itemprop": "articleBody"})
    if body:
        if save_debug:
            utils.write_file(str(body), './debug/debug.html')

        for el in body.find_all(class_=['art-ins', 'molads_ff', 'fff-inline', 'perform-player']):
            # perform-play4er seems to be unrelated videos
            el.decompose()

        for el in body.find_all(class_='moduleFull'):
            if el.find(class_='fff-inline'):
                el.decompose()
            else:
                logger.warning('unhandled moduleFull in ' + item['url'])

        for el in body.find_all(class_='related-carousel'):
            if el.parent and el.parent.name == 'div':
                el.parent.decompose()
            else:
                el.decompose()

        for el in body.find_all(attrs={"data-podcast-container": True}):
            el.decompose()

        for el in body.find_all(class_='mol-img-group'):
            new_html = ''
            it = el.find(class_='imageCaption')
            if it:
                caption = it.decode_contents()
            else:
                caption = ''
            images = el.find_all(class_='mol-img')
            if len(images) == 1:
                it = el.find('img')
                if it:
                    new_html = utils.add_image(it['data-src'], caption)
            else:
                new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                for img in images:
                    it = img.find('img')
                    if it:
                        new_html += '<div style="flex:1; min-width:256px;">{}</div>'.format(utils.add_image(it['data-src']))
                new_html += '</div>'
                if caption:
                    new_html += '<!--caption--><div><small>{}</small></div>'.format(caption)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled mol-img-group in ' + item['url'])

        for el in body.find_all(class_='mol-video'):
            it = el.find('video')
            if it:
                video_json = json.loads(it['data-opts'])
                if save_debug:
                    utils.write_file(video_json, './debug/video.json')
                new_html = utils.add_video(video_json['src'], 'video/mp4', video_json['poster'], 'Watch: ' + video_json['title'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled mol-embed in ' + item['url'])

        for el in body.find_all(class_='mol-embed'):
            new_html = ''
            if el.find(class_='twitter-tweet'):
                links = el.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
            elif el.find(class_='tiktok-embed'):
                it = el.find('blockquote')
                new_html = utils.add_embed(it['cite'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled mol-embed in ' + item['url'])

        item['content_html'] += body.decode_contents()

    item['content_html'] = re.sub(r'</(div|figure|table)>\s*<(div|figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item