import re
from bs4 import BeautifulSoup
from datetime import datetime

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('a', href=re.compile(r'/editor/'))
    if not el:
        logger.warning('uknown editor in ' + url)
        return None
    ed_url = el['href']
    for i in range(1, 10):
        articles = utils.get_url_json(ed_url + '/page/{}'.format(i), headers={"x-requested-with": "XMLHttpRequest"})
        if not articles:
            return None
        article = next((it for it in articles if it['link'] == url), None)
        if article:
            if save_debug:
                utils.write_file(article, './debug/debug.json')
            return get_item(article, args, site_json, save_debug)
    return None


def get_item(article_json, args, site_json, save_debug):
    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['link']
    item['title'] = article_json['title']

    def format_date(matchobj):
        return '.{}+00:00'.format(matchobj.group(1).zfill(3))
    date = article_json['isoDate']
    if date.endswith('Z'):
        date = re.sub(r'\.(\d+)Z', format_date, date)
    dt = datetime.fromisoformat(date)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {
        "name": article_json['author']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    if article_json.get('tags'):
        item['tags'] = [x['term']['name'] for x in article_json['tags']]

    if article_json.get('firstImage'):
        item['image'] = article_json['firstImage']

    if article_json.get('summary'):
        item['summary'] = article_json['summary']

    def fix_paragraphs(matchobj):
        if matchobj.group(1) == '>' and matchobj.group(2) == '<':
            return '><'
        elif matchobj.group(1) == '>':
            return '><p>' + matchobj.group(2)
        elif matchobj.group(2) == '<':
            return matchobj.group(1) + '</p><'
        else:
            return matchobj.group(1) + '</p><p>' + matchobj.group(2)
    item['content_html'] = '<p>' + re.sub(r'(.)\r\n\r\n(.)', fix_paragraphs, article_json['body']) + '</p>'
    item['content_html'] = re.sub(r'\r\n', '', item['content_html'])

    soup = BeautifulSoup(item['content_html'], 'html.parser')

    if 'image' not in item:
        el = soup.find('img')
        if el:
            item['image'] = el['src']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    for el in soup.find_all('div', attrs={"align": "center"}):
        new_html = ''
        if el.iframe:
            new_html = utils.add_embed(el.iframe['src'])
        elif el.find(class_='twitter-tweet'):
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
        elif el.find(class_='tiktok-embed'):
            new_html = utils.add_embed(el.blockquote['cite'])
        elif el.img:
            new_html = utils.add_image(el.img['src'], el.get_text().strip())
        elif el.find(class_='deal-highlight'):
            continue
        elif re.search(r'youtube\.com/c/appleinsider\?sub_confirmation=1', str(el)):
            el.decompose()
            continue
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled center div content in ' + item['url'])

    for el in soup.find_all('iframe', class_='juxtapose'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('a', attrs={"rel": "sponsored"}):
        href = utils.get_redirect_url(el['href'])
        el.attrs = {}
        el['href'] = href

    if article_json.get('reviewStars') and article_json['reviewStars']['score'] != '0.0':
        el = soup.find('figure')
        new_el = BeautifulSoup('<h2>Rating: {} out of 5</h2>'.format(article_json['reviewStars']['score']), 'html.parser')
        el.insert_after(new_el)

    item['content_html'] = str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    if '/rss/' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    articles = utils.get_url_json(args['url'] + '/page/1', headers={"x-requested-with": "XMLHttpRequest"})
    if not articles:
        return None
    if save_debug:
        utils.write_file(articles, './debug/feed.json')

    n = 0
    feed_items = []
    for article in articles:
        if save_debug:
            logger.debug('getting content for ' + article['link'])
        item = get_item(article, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    #feed['title'] = 'Game Developer | ' + next_data['pageProps']['data']['labelInfo']['title']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed