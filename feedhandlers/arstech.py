import json, re
from bs4 import BeautifulSoup, Comment
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_video(video_id, caption=''):
    video_json = utils.get_url_json('https://player.cnevids.com/embed-api.json?videoId={}&embedLocation=arstechnica'.format(video_id))
    source = next((it for it in video_json['video']['sources'] if it['type'] == 'video/mp4'), None)
    if not source:
        source = next((it for it in video_json['video']['sources'] if it['type'] == 'video/webm'), None)
        if not source:
            source = next((it for it in video_json['video']['sources'] if it['type'] == 'application/x-mpegURL'), None)
    if not source:
        return '<blockquote><strong>Watch: <a href="{}">{}</a></strong></blockquote>'.format(video_json['video']['url'], video_json['video']['title'])
    if caption:
        caption ='<strong><a href="{}">{}</a></strong>. {}'.format(video_json['video']['url'], video_json['video']['title'], caption)
    else:
        caption = '<strong><a href="{}">{}</a></strong>'.format(video_json['video']['url'], video_json['video']['title'])
    return utils.add_video(source['src'], source['type'], video_json['video']['poster_frame'], caption)


def get_caption(element):
    captions = []
    it = element.find(class_=['caption', 'caption-text'])
    if it:
        caption = it.get_text().strip()
        if caption:
            captions.append(caption)
    it = element.find(class_=['credit', 'caption-credit'])
    if it:
        caption = it.get_text().strip()
        if caption:
            captions.append(caption)
    return ' | '.join(captions)


def get_content(url, args, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    m = re.search(r'window\.dataLayer\.push\(({.+?})\);\n', page_html)
    if not m:
        logger.warning('unable to find page dataLayer in ' + url)
        return None
    page_data = json.loads(m.group(1).replace(':undefined', ':""'))

    item = {}
    item['id'] = page_data['content']['contentID']
    item['url'] = page_data['page']['canonical']
    item['title'] = page_data['content']['display']

    dt = datetime.fromisoformat(page_data['content']['publishDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(page_data['content']['modifiedDate'])
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('a', attrs={"rel": "author"})
    if el:
        item['author']['name'] = el.get_text()
    else:
        item['author']['name'] = page_data['content']['contributor']

    item['tags'] = page_data['content']['keywords'].split('|')
    item['tags'].append(page_data['content']['contentCategory'])

    el = soup.find('meta', attrs={"property": "og:image"})
    if el:
        item['_image'] = el['content']

    el = soup.find('meta', attrs={"property": "og:description"})
    if el:
        item['summary'] = el['content']

    article_body = soup.find(class_='article-content')
    content_html = article_body.decode_contents()

    nav = soup.find('nav', class_='page-numbers')
    while nav:
        for el in nav.find_all('a'):
            if el.get_text().startswith('Next'):
                if save_debug:
                    logger.debug('getting next page content from ' + el['href'])
                page_html = utils.get_url_html(el['href'])
                if page_html:
                    soup = BeautifulSoup(page_html, 'html.parser')
                    article_body = soup.find(class_='article-content')
                    content_html += article_body.decode_contents()
                    nav = soup.find('nav', class_='page-numbers')
                    break
            else:
                nav = None

    article_body = BeautifulSoup(content_html, 'html.parser')

    for el in article_body.find_all('aside'):
        el.decompose()

    for el in article_body.find_all(class_=['sidebar', 'ars-newsletter-callbox', 'mc_embed_signup', 'toc-container']):
        el.decompose()

    for el in article_body.find_all('div', class_='article-intro'):
        el.name = 'p'
        el.attrs = {}
        el['style'] = 'font-style:italic;'

    # Remove comment sections
    for el in article_body.find_all(text=lambda text: isinstance(text, Comment)):
        el.extract()

    for el in article_body.find_all('blockquote'):
        if el.get('class'):
            if 'twitter-tweet' in el['class']:
                continue
        it = el.find(class_='pullquote-content')
        if it:
            quote = it.get_text().strip()
            it = el.find(class_='pullquote-attribution')
            if it:
                author = it.get_text().strip()
            else:
                author = ''
            new_el = BeautifulSoup(utils.add_pullquote(quote, author), 'html.parser')
        elif el.find_previous_sibling('p').get_text().endswith(':'):
            new_el = BeautifulSoup(utils.add_pullquote(el.decode_contents()), 'html.parser')
        else:
            new_el = BeautifulSoup(utils.add_blockquote(el.decode_contents()), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in article_body.find_all(class_='gallery'):
        for li in el.find_all('li'):
            img_src = li['data-src']
            caption = get_caption(li)
            new_el = BeautifulSoup(utils.add_image(img_src, caption) + '<br/>', 'html.parser')
            el.insert_before(new_el)
        el.decompose()

    for el in article_body.find_all('figure', class_=['image', 'intro-image']):
        img_src = el.img['src']
        if 'wired-logo.png' not in img_src:
            it = el.find(class_='caption-text')
            if it:
                if it.a and it.a.get_text() == 'Enlarge':
                    img_src = it.a['href']
                    it.a.decompose()
                if it.span and 'sep' in it.span['class']:
                    it.span.decompose()
            caption = get_caption(el)
            new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
            el.insert_after(new_el)
        el.decompose()

    for el in article_body.find_all('figure', class_='video'):
        new_el = None
        if el.iframe:
            new_el = BeautifulSoup(utils.add_embed(el.iframe['src']), 'html.parser')
        else:
            caption = get_caption(el)
            it = el.find(class_='ars-video-container')
            if it:
                new_el = BeautifulSoup(add_video(it['data-video-id'], caption), 'html.parser')
            else:
                it = el.find('video')
                if it:
                    if it.get('poster'):
                        poster = it['poster']
                    else:
                        poster = '{}/image?url={}&width=1024'.format(config.server, quote_plus(utils.clean_url(it.source['src'])))
                    new_el = BeautifulSoup(utils.add_video(it.source['src'], it.source['type'], poster, caption), 'html.parser')
        if new_el:
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled video in ' + item['url'])

    for el in article_body.find_all('div', class_='twitter-tweet'):
        it = el.find_all('a')
        new_el = BeautifulSoup(utils.add_embed(it[-1]['href']), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in article_body.find_all('table'):
        el.attrs = {}
        el['border'] = ''
        el['style'] = 'width:100%; border-collapse:collapse;'
        if el.get('class') and 'specifications' in el['class']:
            it = el.find('tr')
            if it.th and re.search(r'Specs at a glance', it.th.get_text(), flags=re.I):
                el.insert_before(BeautifulSoup('<h3 style="margin-bottom:0.5em;">{}</h3>'.format(it.th.get_text()), 'html.parser'))
                it.decompose()

    for el in article_body.find_all(class_='ars-component-buy-box'):
        el_html = '<h3 style="margin-bottom:0;">Buy:</h3><ul style="margin-top:0.5em;">'
        for it in el.find_all('a', class_='ars-buy-box-button'):
            el_html += '<li><a href="{}">{}</a></li>'.format(utils.get_redirect_url(it['href']), it.get_text().strip())
        el_html += '</ul>'
        new_el = BeautifulSoup(el_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in article_body.find_all('pre', class_='wp-block-code'):
        el.attrs = {}
        el['style'] = 'margin-left:2em; padding:0.5em; white-space:pre-wrap; background:#F2F2F2;'

    for el in article_body.find_all(class_='ars-approved-logo'):
        el.name = 'img'
        el.attrs = {}
        el['src'] = 'https://cdn.arstechnica.net/wp-content/themes/ars/assets/img/ars-approved-271f606d5e.png'
        el['style'] = 'float:right; width:128px;'

    item['content_html'] = article_body.decode_contents()
    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
