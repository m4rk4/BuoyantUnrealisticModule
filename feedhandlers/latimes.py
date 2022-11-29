import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_media(media_el, width=1000):
    media_html = ''
    if media_el.find('figure', class_='figure'):
        img = media_el.find('img')
        if img:
            if img.get('srcset'):
                img_src = utils.image_from_srcset(img['srcset'], 1000)
            else:
                img_src = img['src']
            captions = []
            it = media_el.find(class_='figure-caption')
            if it:
                captions.append(it.decode_contents())
            it = media_el.find(class_='figure-credit')
            if it:
                captions.append(it.decode_contents())
            media_html = utils.add_image(img_src, ' '.join(captions))

    elif media_el.find(class_='video-enhancement'):
        it = media_el.find('ps-youtubeplayer')
        if it:
            media_html = utils.add_embed('https://www.youtube.com/embed/' + it['data-video-id'])
        elif media_el.find('gn-looping-video-player'):
            poster = ''
            it = media_el.find(class_='gvp-overlay-poster')
            if it:
                if it.img:
                    if it.img.get('srcset'):
                        poster = utils.image_from_srcset(it.img['srcset'], 1000)
                    else:
                        poster = it.img['src']
            video = media_el.find('source', attrs={"type": "video/mp4"})
            if not video:
                video = media_el.find('source', attrs={"type": "application/x-mpegURL"})
            if video:
                video_type = video['type']
                video_src = ''
                if video.get('data-src'):
                    video_src = video['data-src']
                elif video.get('src'):
                    video_src = video['src']
                if video_src:
                    media_html = utils.add_video(video_src, video_type, poster)

    elif media_el.find('ps-tweet-embed'):
        links = media_el.find_all('a')
        media_html = utils.add_embed(links[-1]['href'])

    elif media_el.find('ps-podcast-links'):
        el = media_el.find(class_='podcast-links-wrapper')
        if el:
            media_html = el.decode_contents()

    elif media_el.find('ps-interactive-project'):
        el = media_el.find('noscript')
        if el:
            it = BeautifulSoup(el.decode_contents(), 'html.parser')
            if it.iframe and it.iframe.get('src'):
                if it.iframe['src'].startswith('//'):
                    iframe_src = 'https:' + it.iframe['src']
                else:
                    iframe_src = it.iframe['src']
                if 'latimes.com' in iframe_src:
                    ss_url = '{}/screenshot?url={}&locator=section&width=800&height=800'.format(config.server, quote_plus(iframe_src))
                    if it.iframe.get('title'):
                        caption = '{} <a href="{}">View interactive embed.</a>'.format(it.iframe['title'], iframe_src)
                    else:
                        caption = '<a href="{}">View interactive embed.</a>'.format(iframe_src)
                    media_html = utils.add_image(ss_url, caption, link=iframe_src)
                else:
                    media_html = utils.add_embed(iframe_src)

    elif media_el.find(class_='quote'):
        quote = media_el.find(class_='quote-body')
        if quote:
            it = media_el.find(class_='quote-attribution')
            if it:
                author = it.get_text()
                if author.startswith('—'):
                    author = author[1:]
            else:
                author = ''
            media_html = utils.add_pullquote(quote.decode_contents(), author.strip())

    elif media_el.find(class_='infobox'):
        it = media_el.find(class_='infobox-title')
        if it:
            media_html += '<span style="font-size:1.2em; font-weight:bold">{}</span><br/><br/>'.format(it.get_text())
        it = media_el.find(class_='infobox-description')
        if it:
            media_html += it.decode_contents()
        media_html = utils.add_blockquote(media_html)

    elif media_el.find('hr', class_='divider'):
        media_html = '<hr/>'

    return media_html

def get_content(url, args, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    soup = BeautifulSoup(page_html, 'html.parser')
    ld_json = None
    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        ld_json = json.loads(el.string)
        if ld_json.get('@type') and (ld_json['@type'] == 'NewsArticle' or ld_json['@type'] == 'Article' or ld_json['@type'] == 'WebPage'):
            break
        ld_json = None
    if not ld_json:
        logger.warning('unable to find NewsArticle ld+json in ' + url)
    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    item = {}
    item['id'] = ld_json['url']
    item['url'] = ld_json['url']
    item['title'] = ld_json['headline']

    dt = datetime.fromisoformat(ld_json['datePublished'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(ld_json['dateModified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    authors = []
    if ld_json.get('author'):
        for it in ld_json['author']:
            authors.append(it['name'])
    else:
        el = soup.find(class_='byline')
        if el:
            it = el.find('span', class_='link')
            if it:
                authors.append(it.get_text().strip())
    if authors:
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif ld_json.get('publisher'):
        item['author']['name'] = ld_json['publisher']['name']

    item['tags'] = []
    el = soup.find(class_='tags')
    if el:
        for it in el.find_all('a'):
            item['tags'].append(it.get_text().strip())
    if not item.get('tags'):
        del item['tags']

    if ld_json.get('image'):
        item['_image'] = ld_json['image'][0]['url']

    if ld_json.get('description'):
        item['summary'] = ld_json['description']

    item['content_html'] = ''
    el = soup.find(class_='page-lead-media')
    if el:
        item['content_html'] += add_media(el)

    body = soup.find(class_=['rich-text-article-body-content', 'rich-text-body'])
    if not body:
        logger.warning('unhable to find article-body-content in ' + item['url'])
        return item

    el = body.find(class_='subscriber-content')
    if el:
        el.unwrap()

    for el in body.find_all(class_='enhancement'):
        if el.find(class_='google-dfp-ad-wrapper') or el.find('ps-nativo-module') or el.find('ps-promo') or el.find('ps-newsletter-module'):
            el.decompose()
        elif el.find('a', href=re.compile('https://www\.latimes\.com/subscriptions/newsletters\.html')):
            # Subscription signup
            el.decompose()
        elif el.find(class_='html-module'):
            # Seems to be a stylesheet
            el.decompose()
        else:
            new_html = add_media(el)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled enhancement class in ' + item['url'])

    item['content_html'] += body.decode_contents()

    if soup.html.get('class'):
        if 'poi-list-page' in soup.html['class']:
            for poi in soup.find_all(class_='poi-module'):
                item['content_html'] += '<hr/>'
                el = poi.find(class_='poi-module-media')
                if el:
                    item['content_html'] += add_media(el)
                el = poi.find(class_='poi-module-title')
                if el:
                    item['content_html'] += '<h3 style="margin-bottom:0;">{}</h3>'.format(el.get_text().strip())
                el = poi.find(class_='poi-module-categories')
                if el:
                    categories = []
                    for it in el.find_all(class_=re.compile(r'-categories-(?!icon)')):
                        categories.append(it.get_text().strip())
                    if categories:
                        item['content_html'] += '<div>{}</div>'.format(' | '.join(categories))
                el = poi.find(class_='poi-module-rich-text-body')
                if el:
                    it = el.find(class_='toggle-text-content')
                    if it:
                        it.name = 'p'
                        it.attrs = {}
                        item['content_html'] += str(it)
                    else:
                        el.name = 'p'
                        el.attrs = {}
                        item['content_html'] += str(el)
                item['content_html'] += '<ul>'
                el = poi.find(class_='postal-address')
                if el:
                    item['content_html'] += '<li>' + str(el.div) + '</li>'
                el = poi.find(class_='social')
                if el:
                    for it in el.find_all(class_='icon'):
                        it.decompose()
                    for it in el.find_all(class_=re.compile(r'poi-module-')):
                        it.name = 'li'
                        it.attrs = {}
                        item['content_html'] += str(it)
                item['content_html'] += '</ul>'
    item['content_html'] = re.sub(r'</(div|figure|table)>\s*<(div|figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
