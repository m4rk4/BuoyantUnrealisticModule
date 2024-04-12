import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    m = re.search(r'-(\d+)_\d\.html$', paths[-1])
    if not m:
        logger.warning('unable to determine article id in ' + url)
        return None
    api_json = utils.get_url_json('https://apibs.business-standard.com/article/detail?articleId={}&bsr=1&isNew=1'.format(m.group(1)))
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    article_json = api_json['data']
    item = {}
    item['id'] = article_json['articleId']
    item['url'] = 'https://www.business-standard.com' + article_json['articleUrl']
    item['title'] = article_json['pageTitle']

    dt = datetime.fromtimestamp(int(article_json['publishDate'])).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromtimestamp(int(article_json['modificationDate'])).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    if article_json.get('authorName'):
        item['author'] = {"name": article_json['authorName']}
    elif article_json.get('articleMappedMultipleAuthors'):
        authors = []
        for key, val in article_json['articleMappedMultipleAuthors'].items():
            authors.append(val)
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif article_json.get('sourceTitle'):
        item['author'] = {"name": article_json['sourceTitle']}

    if article_json.get('metaKeywords'):
        item['tags'] = [it.strip() for it in article_json['metaKeywords'].split(',')]

    if article_json.get('description'):
        item['summary'] = article_json['description']
    elif article_json.get('metaDescription'):
        item['summary'] = article_json['metaDescription']

    item['content_html'] = ''

    if article_json.get('subHeading'):
        item['content_html'] += '<p><em>' + article_json['subHeading'] + '</em></p>'

    if article_json.get('featuredImageObj'):
        item['_image'] = article_json['featuredImageObj']['url']
        item['content_html'] += utils.add_image(item['_image'], article_json['featuredImageObj'].get('caption'))

    if 'embed' in args:
        item['content_html'] = '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(split_url.netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}">Read</a></p></div></div>'.format(config.server, quote_plus(item['url']))
        return item

    if article_json.get('contentMp3'):
        item['_audio'] = 'https://bsmedia.business-standard.com/' + article_json['contentMp3']
        attachment = {}
        attachment['url'] = item['_audio']
        attachment['mime_type'] = 'audio/mpeg'
        item['attachments'] = []
        item['attachments'].append(attachment)
        item['content_html'] += '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">Listen</a></span></div><div>&nbsp;</div>'.format(item['_audio'], config.server)

    soup = BeautifulSoup(article_json['htmlContent'], 'html.parser')
    if len(soup.find_all('div', recursive=False)) == 1:
        soup.div.unwrap()

    for el in soup.find_all(recursive=False):
        if el.name == 'blockquote' or (el.name == 'div' and el.blockquote):
            if el.name == 'blockquote':
                it = el
            else:
                it = el.blockquote
            if it.get('class'):
                if 'twitter-tweet' in it['class']:
                    links = it.find_all('a')
                    new_html = utils.add_embed(links[-1]['href'])
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.replace_with(new_el)
                elif 'instagram-media' in it['class']:
                    new_html = utils.add_embed(it['data-instgrm-permalink'])
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.replace_with(new_el)
                else:
                    logger.warning('unhandled blockquote class {} in {}'.format(el['class'], item['url']))
            else:
                new_html = utils.add_blockquote(it.decode_contents())
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
        elif el.name == 'div':
            el.name = 'p'
            it = el.find('img', class_='imgCont')
            if it:
                new_html = utils.add_image(it['src'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                it.parent.decompose()
        elif el.name == 'br':
            el.decompose()

    for el in soup.find_all(class_='read_more'):
        el.decompose()

    for el in soup.find_all('br'):
        el.decompose()

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    # api: https://apibs.business-standard.com/article/latest-news?limit=10&page=0&offset=0
    # rss: https://www.business-standard.com/rss-feeds/listing
    return rss.get_feed(url, args, site_json, save_debug, get_content)
