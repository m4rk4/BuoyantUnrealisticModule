import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_next_data(url):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile(r'__NEXT_DATA__'))
    if not el:
        logger.warning('unable to find NEXT_DATA in ' + url)
        return None
    m = re.search(r'__NEXT_DATA__\s?=\s?(.*)', el.string.strip())
    if not m:
        logger.warning('unable to parse NEXT_DATA json in ' + url)
        return None
    return json.loads(m.group(1))


def format_content(content, item):
    if isinstance(content, str):
        return content

    content_html = ''
    if content.get('tagName'):
        if re.search(r'^(p|ol|ul|h\d|strong)$', content['tagName']):
            if content.get('source'):
                source = content['source']
            else:
                source = '&nbsp;'
            content_html += '<{0}>{1}</{0}>'.format(content['tagName'], source)
        elif content['tagName'] == 'a':
            content_html += '<a href="{}">{}</a>'.format(content['attributes']['href'], content['source'])
        elif content['tagName'] == 'span':
            for cnt in content['children']:
                content_html += format_content(cnt, item)
        elif content['tagName'] == 'hr':
            content_html += '<hr/>'
        elif content['tagName'] == 'blockquote':
            content_html += utils.add_blockquote(content['source'])
        elif content['tagName'] == 'iframe':
            content_html += utils.add_embed(content['attributes']['src'])
        elif content['tagName'] == 'div':
            if content.get('source'):
                if content['source'].startswith('<figure'):
                    el = BeautifulSoup(content['source'], 'html.parser')
                    img_src = ''
                    it = el.find('img')
                    if it:
                        if it['src'].startswith('/'):
                            img_src = 'https:' + it['src']
                        else:
                            img_src = it['src']
                        img_src = utils.clean_url(img_src) + '?w=1000'
                    else:
                        it = el.find('lazy-image')
                        if it:
                            if re.search(r'HeadShot', it['src']):
                                return ''
                            else:
                                img_src = utils.clean_url('https:' + it['src']) + '?w=1000'
                    if img_src:
                        it = el.find('figcaption')
                        if it:
                            caption = it.get_text()
                        else:
                            caption = ''
                        content_html += utils.add_image(img_src, caption)
                        if not item.get('_image'):
                            item['_image'] = img_src
                    else:
                        logger.warning('unhandled figure in ' + item['url'])
                elif content['source'].startswith('<p') and not item['content_html']:
                    el = BeautifulSoup(content['source'], 'html.parser')
                    el.p.attrs = {}
                    el.p['style'] = 'font-style:italic;'
                    content_html += str(el)
                elif content['source'].startswith('<table'):
                    el = BeautifulSoup(content['source'], 'html.parser')
                    el.table.attrs = {}
                    el.table['style'] = 'width:100%; table-layout:fixed; border-collapse:collapse;'
                    for it in el.table.find_all(['th', 'td']):
                        it['style'] = 'border-collapse:collapse; border:1px solid black;'
                    for i, it in enumerate(el.table.find_all('tr')):
                        if not i%2:
                            it['style'] = 'background-color:lightgrey;'
                    content_html += str(el)
                else:
                    logger.warning('unhandled div in ' + item['url'])
            elif content.get('attributes') and content['attributes'].get('className'):
                if 'wp-block-healthline-jwplayer' in content['attributes']['className'].split(' '):
                    content_html += utils.add_embed('https://cdn.jwplayer.com/players/' + content['children'][0]['widget']['id'])
                elif 'button-cta-div' in content['attributes']['className'].split(' '):
                    content_html += '<div style="width:250px; padding:10px; margin-bottom:1em; background-color:lightgrey; text-align:center;">'
                    for cnt in content['children']:
                        content_html += format_content(cnt, item)
                    content_html += '</div>'
                else:
                    logger.warning('unhandled div in ' + item['url'])
            else:
                logger.warning('unhandled div in ' + item['url'])
        elif content['tagName'] == 'script':
            if content.get('attributes') and content['attributes'].get('type') and content['attributes']['type'] == 'application/ld+json':
                return ''
            logger.warning('unhandled script in ' + item['url'])
        else:
            logger.warning('unhandled tag {} in {}'.format(content['tagName'], item['url']))

    elif content.get('widget'):
        if content['widget']['widgetFormat'] == 'widget-call-out':
            content_html = '<div style="background-color:lightgrey; padding:0.5em; border-radius:10px;">'
            for it in content['widget']['items']:
                if it.get('headerTitle'):
                    content_html += '<h2>'
                    for cnt in it['headerTitle']:
                        content_html += format_content(cnt, item)
                    content_html += '</h2>'
                if it.get('content'):
                    for cnt in it['content']:
                        content_html += format_content(cnt, item)
            content_html += '</div>'
        elif content['widget']['widgetFormat'] == 'wp-block-group':
            for cnt in content['widget']['children']:
                content_html += format_content(cnt, item)
    return content_html


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    if next_data.get('pathname'):
        if next_data['pathname'] == '/category' or next_data['pathname'] == '/subcategory' or next_data['pathname'] == '/program-landing':
            return None

    article_json = next_data['props']['data']
    app_state = next_data['appState']

    item = {}
    item['id'] = article_json['id']
    item['url'] = app_state['canonical']
    item['title'] = app_state['title']

    dt = datetime.fromtimestamp(app_state['byline']['articleDates']['published']['date']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromtimestamp(app_state['byline']['articleDates']['modified']['date']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in article_json['authors']:
        authors.append(it['name']['display'])
    for it in article_json['editors']:
        authors.append('{} ({})'.format(it['name']['display'], it['role']))
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    for it in article_json['categories']:
        item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''
    if article_json.get('tabs'):
        for tab in article_json['tabs']:
            if tab.get('header'):
                item['content_html'] += '<h2>'
                for content in tab['header']:
                    item['content_html'] += format_content(content, item)
                item['content_html'] += '</h2>'
            for content in tab['body']:
                item['content_html'] += format_content(content, item)
    elif article_json.get('body'):
        for content in article_json['body']:
            item['content_html'] += format_content(content, item)
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    articles = []
    if next_data['pathname'] == '/home-page':
        for widget in next_data['props']['data']['widgets']:
            if widget.get('items'):
                articles += widget['items']
    elif next_data['props'].get('type') and next_data['props']['type'] == 'page':
        for widget in next_data['props']['pageWidgets']:
            if widget.get('items'):
                articles += widget['items']
    elif next_data['props'].get('items'):
        articles += next_data['props']['items']

    split_url = urlsplit(url)
    n = 0
    feed_items = []
    for article in articles:
        if article['link'].count('/') == 1:
            # Skip topics
            continue
        if article['link'].startswith('/'):
            article_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article['link'])
        else:
            article_url = article['link']
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_content(article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    #feed['title'] = soup.title.get_text()
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed