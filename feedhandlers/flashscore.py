import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

from feedhandlers import dirt
import config, utils

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    split_url = urlsplit(img_src)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if split_url.netloc != 'livesport-ott-images.ssl.cdn.cra.cz':
        return img_src
    return 'https://livesport-ott-images.ssl.cdn.cra.cz/r{}xfq60/{}'.format(width, paths[-1])


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    gql_url = 'https://2.ds.lsapp.eu/pq_graphql?_hash=fsa&projectId=2&articleId=' + paths[-1]
    gql_json = utils.get_url_json(gql_url)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')
    article_data = gql_json['data']['findNewsArticleById']

    item = {}
    item['id'] = article_data['id']
    item['url'] = article_data['url']
    item['title'] = article_data['title']

    tz_loc = pytz.timezone(config.local_tz)
    dt_loc = datetime.fromtimestamp(article_data['published'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {
        "name": article_data['credit']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['tags'] = []
    if article_data.get('mentions'):
        item['tags'] = [x['name'] for x in article_data['mentions']]
    if article_data.get('entities'):
        for it in article_data['entities']:
            if it.get('participant'):
                item['tags'].append(it['participant']['name'])
            elif it.get('sport'):
                item['tags'].append(it['sport']['name'])
            elif it.get('tournamentTemplate'):
                item['tags'].append(it['tournamentTemplate']['name'])
            elif it.get('tag'):
                item['tags'].append(it['tag']['name'])
    if len(item['tags']) == 0:
        del item['tags']

    item['content_html'] = ''
    if article_data.get('perex'):
        item['summary'] = article_data['perex']
        item['content_html'] = '<p><em>' + item['summary'] + '</em></p>'

    if article_data.get('images'):
        item['image'] = resize_image(article_data['images'][0]['url'])
        item['content_html'] += utils.add_image(item['image'], article_data['images'][0].get('credit'))

    def sub_html_tag(matchobj):
        m = re.search(r'^[^\s]+', matchobj.group(1))
        tag = m.group(0)
        if tag.startswith('/') or len(tag) <= 2:
            if tag.startswith('/lslink-'):
                return '</a>'
            return '<' + tag + '>'
        elif tag == 'a' or tag.startswith('lslink-'):
            m = re.search(r'href="([^"]+)', matchobj.group(1))
            if m:
                if m.group(1).startswith('/'):
                    return '<a href="https://www.flashscore.com' + m.group(1) + '">'
                else:
                    return '<a href="' + m.group(1) + '">'
            else:
                logger.warning('unhandled link href ' + matchobj.group(1))
        elif tag == 'embed':
            m = re.search(r'url="([^"]+)', matchobj.group(1))
            if m:
                return utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled embed ' + matchobj.group(0))
        elif tag == 'image':
            m = re.search(r'\sid="([^"]+)', matchobj.group(1))
            img_src = 'https://livesport-ott-images.ssl.cdn.cra.cz/r1200xfq60/' + m.group(1)
            m = re.search(r'credit-line="([^"]+)', matchobj.group(1))
            return utils.add_image(img_src, m.group(1))
        else:
            logger.warning('unhandled tag ' + matchobj.group(0))
        return matchobj.group(0)

    item['content_html'] += re.sub(r'\[([^\]]+)\]', sub_html_tag, article_data['content'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    # TODO: Better way to get the entityTypeId?
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    page_soup = BeautifulSoup(page_html, 'lxml')
    el = page_soup.find('script', string=re.compile(r'window\.fsNewsData'))
    if not el:
        logger.warning('unable to find fsNewsData in ' + url)
        return None
    i = el.string.find('{')
    j = el.string.rfind('}') + 1
    news_data = json.loads(el.string[i:j])
    if save_debug:
        utils.write_file(news_data, './debug/debug.json')

    gql_url = 'https://2.ds.lsapp.eu/pq_graphql?_hash=fsnulae&projectId={}&entityId={}&entityTypeId={}&layoutTypeId={}&page=1&perPage=10'.format(news_data['fsdsRequestData']['projectId'], news_data['fsdsRequestData']['topicId'], news_data['fsdsRequestData']['entityTypeId'], news_data['fsdsRequestData']['layoutTypeId'])
    gql_json = utils.get_url_json(gql_url)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/feed.json')

    n = 0
    feed_items = []
    for article in gql_json['data']['findNewsLayoutForEntity']['sections'][0]['articles']:
        article_url = 'https://www.flashscore.com/news/-/' + article['id'] + '/'
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
    if gql_json['data']['findNewsLayoutForEntity'].get('relatedEntity'):
        for key, val in gql_json['data']['findNewsLayoutForEntity']['relatedEntity'].items():
            if not val:
                continue
            elif key == 'participant' or key == 'sport' or key == 'tag':
                feed['title'] = val['name'] + ' | Flashscore.com'
            elif key == 'tournamentTemplate':
                feed['title'] = val['name']
                if val.get('sport'):
                    feed['title'] += ' | ' + val['sport']['name']
                feed['title'] += ' | Flashscore.com'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed

