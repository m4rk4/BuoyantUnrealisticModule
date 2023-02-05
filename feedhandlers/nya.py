import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from markdown2 import markdown
from urllib.parse import urlsplit

from feedhandlers import rss
import utils

import logging

logger = logging.getLogger(__name__)


def get_article(article_json, args, site_json, save_debug=False):
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['_id']
    item['url'] = 'https://neilyoungarchives.com/news/1/article?id=' + article_json['id']
    item['title'] = re.sub(r'\spage\d$', '', article_json['headline'])

    dt = datetime.fromisoformat(article_json['date']).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['updatedAt'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    item['author'] = {}
    if article_json.get('byline'):
        item['author']['name'] = article_json['byline']
    else:
        item['author']['name'] = 'NYA'

    if article_json.get('excerpt') and article_json['excerpt'] != '&nbsp;':
        soup = BeautifulSoup(markdown(article_json['excerpt'].replace('<p/>', '</p>')), 'html.parser')
        item['summary'] = str(soup)

    content_html = ''
    headline = ''
    if article_json.get('bodyHeadline') and article_json['bodyHeadline'] != '&nbsp;':
        headline = article_json['bodyHeadline']
    elif article_json.get('headlineText') and article_json['headlineText'] != '&nbsp;':
        headline = article_json['headlineText']
    if headline:
        soup = BeautifulSoup(markdown(headline.replace('<p/>', '</p>')), 'html.parser')
        m = re.search('!\[([^\]]+)\]\(([^\)]+)\)', str(soup))
        if m:
            headline = headline.replace(m.group(0), '<img src="{}"/>'.format(m.group(2)))
            soup = BeautifulSoup(markdown(headline.replace('<p/>', '</p>')), 'html.parser')
        for el in soup.find_all('p'):
            if len(el.get_text(strip=True)) == 0:
                if el.img:
                    el.unwrap()
                else:
                    el.decompose()
        n = 0
        if soup.contents[0] == '\n':
            n = 1
        if soup.contents[n].name == 'p' and not soup.contents[n].img:
            if soup.contents[n].br:
                soup.contents[n].br.replace_with(' ')
            item['title'] = soup.contents[n].get_text().replace('\n', ' ')
            soup.contents[n].decompose()
        content_html += str(soup)

    if article_json.get('bodyText') and article_json['bodyText'] != '&nbsp;':
        soup = BeautifulSoup(markdown(article_json['bodyText'].replace('<p/>', '</p>')), 'html.parser')
        content_html += str(soup)

    soup = BeautifulSoup(content_html, 'html.parser')
    for el in soup.find_all('img'):
        if el['src'].startswith('//'):
            img_src = 'https:' + el['src']
        else:
            img_src = el['src']
        if not item.get('_image'):
            item['_image'] = img_src
        new_el = BeautifulSoup(utils.add_image(img_src), 'html.parser')
        if el.parent and el.parent.name == 'p' and len(el.get_text(strip=True)) == 0:
            el.parent.insert_after(new_el)
        else:
            el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('iframe'):
        if 'vimeo.com' in el['src']:
            logger.debug('skipping vimeo embedded ' + el['src'])
            new_el = BeautifulSoup('<blockquote><b>Embedded content from <a href="{0}">{0}</a></b></blockquote>'.format(el['src']), 'html.parser')
        else:
            new_el = BeautifulSoup(utils.add_embed(el['src']), 'html.parser')
        if el.parent and el.parent.name == 'p' and len(el.get_text(strip=True)) == 0:
            el.parent.insert_after(new_el)
        else:
            el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('a'):
        if el['href'].startswith('/'):
            el['href'] = 'https://neilyoungarchives.com' + el['href']

    # Removes any empty paragraphs
    for el in soup.find_all('p'):
        if len(el.get_text(strip=True)) == 0:
            if el.img:
                el.unwrap()
            else:
                el.decompose()

    # Not sure why markdown2 isn't converting these
    def fix_links(matchobj):
        if matchobj.group(2).startswith('/'):
            href = 'https://neilyoungarchives.com/' + matchobj.group(2)
        else:
            hret = matchobj.group(2)
        return '<a href="{}">{}</a>'.format(href, matchobj.group(1))
    content_html = re.sub('\[([^\]]+)\]\(([^\)]+)\)', fix_links, str(soup))

    item['content_html'] = content_html
    return item


def get_content(url, args, site_json, save_debug=False):
    # https://neilyoungarchives.com/news/1/article?id=A-Message-From-Neil-I-Say
    split_url = urlsplit(url)
    m = re.search(r'id=([^&]+)', split_url.query)
    if not m:
        logger.warning('unable to parse article id from ' + url)
        return None
    article_json = utils.get_url_json('https://nya-management-prod.herokuapp.com/api/v2/article/{}'.format(m.group(1)))
    if not article_json:
        return None
    return get_article(article_json['data']['article'], args, site_json, save_debug)


def get_feed(url, args, site_json, save_debug=False):
    m = re.search(r'/news/(\d)', args['url'])
    if m:
        page = m.group(1)
    else:
        page = '1'

    nya_json = utils.get_url_json('https://nya-management-prod.herokuapp.com/api/v2/news/page-' + page)
    if not nya_json:
        return None
    nya_data = json.loads(nya_json['data'])
    if save_debug:
        utils.write_file(nya_data, './debug/feed.json')


    feed = utils.init_jsonfeed(args)
    items = []
    for key, section in nya_data.items():
        for article in section:
            item = get_article(article, args, site_json, save_debug)
            if item:
              if utils.filter_item(item, args) == True:
                items.append(item)

    items = sorted(items, key=lambda i: i['_timestamp'], reverse=True)
    if 'max' in args:
        feed['items'] = items[:int(args['max'])]
    else:
        feed['items'] = items.copy()
    return feed