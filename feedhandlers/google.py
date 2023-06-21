import json, re
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlsplit, unquote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    item = {}
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if split_url.netloc == 'drive.google.com':
        if 'viewer' in paths:
            page_html = utils.get_url_html(url)
            if not page_html:
                return None
            soup = BeautifulSoup(page_html, 'lxml')
            el = soup.find('img', class_='drive-viewer-prerender-thumbnail')
            if el:
                item['title'] = soup.title.get_text()
                item['url'] = url
                caption = '<a href="{}">View document:</a> {}'.format(item['url'], item['title'])
                if el['src'].startswith('/'):
                    item['_image'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, el['src'])
                else:
                    item['_image'] = el['src']
                item['content_html'] = utils.add_image(item['_image'], caption, link=url)
        elif 'preview' in paths:
            page_html = utils.get_url_html(url)
            if not page_html:
                return None
            m = re.search(r'https://lh3.googleusercontent.com/drive-viewer/[^"]+', page_html)
            if m:
                item['_image'] = m.group(0).encode('utf-8').decode('unicode_escape')
                soup = BeautifulSoup(page_html, 'lxml')
                caption = '<a href="{}">View document</a>'.format(url)
                el = soup.find('meta', attrs={"property": "og:title"})
                if el:
                    caption += ': ' + el['content']
                item['content_html'] = utils.add_image(item['_image'], caption, link=url)
    elif split_url.netloc == 'maps.google.com' or paths[0] == 'maps':
        # https://andrewwhitby.com/2014/09/09/google-maps-new-embed-format/
        # https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d316.0465152882427!2d-81.5512302066608!3d41.09612587494313!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x8830d7ae81e95ae5%3A0xb29f75ec4aac5a3c!2sLeeAngelo%E2%80%99s%20(Akron)!5e0!3m2!1sen!2sus!4v1687347021057!5m2!1sen!2sus
        lat = ''
        lon = ''
        m = re.search(r'!2d([\-\.0-9]+)', url)
        if m:
            lon = m.group(1)
        m = re.search(r'!3d([\-\.0-9]+)', url)
        if m:
            lat = m.group(1)
        if not (lat and lon):
            logger.warning('unable to parse lat & lon in ' + url)
        item = {}
        m = re.search(r'!2s([^!]+)', url)
        if m:
            item['title'] = unquote_plus(m.group(1))
            caption = item['title']
            item['url'] = 'https://www.google.com/maps/search/{}/@{},{},15z'.format(quote_plus(item['title']), lat, lon)
        else:
            caption = ''
            item['url'] = 'https://www.google.com/maps/@{},{},15z'.format(lat, lon)
        item['_image'] = '{}/map?lat={}&lon={}'.format(config.server, lat, lon)
        item['content_html'] = utils.add_image(item['_image'], caption, link=item['url'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    feed = None
    split_url = urlsplit(url)
    if split_url.netloc == 'trends.google.com':
        trends_txt = utils.get_url_html('https://trends.google.com/trends/api/dailytrends?hl=en-US&tz=240&geo=US&hl=en-US&ns=15')
        if not trends_txt:
            return None
        n = trends_txt.find('{')
        trends_json = json.loads(trends_txt[n:])
        if save_debug:
            utils.write_file(trends_json, './debug/feed.json')

        feed_items = []
        for day in trends_json['default']['trendingSearchesDays']:
            for trend in day['trendingSearches']:
                item = None
                item_source = ''
                content_html = '<h3>{} searches</h3><ul>'.format(trend['formattedTraffic'])
                for article in trend['articles']:
                    content_html += '<li><a href="{}">{}</a> &bull; {}</li>'.format(article['url'], article['title'], article['source'])
                    if not item:
                        if save_debug:
                            logger.debug('trying to get content from ' + article['url'])
                        item_source = article['source']
                        item = utils.get_content(article['url'], {}, False)
                queries = []
                for query in trend['relatedQueries']:
                    queries.append('<a href="https://trends.google.com{}">{}</a>'.format(query['exploreLink'], query['query']))
                content_html += '</ul><p>Related queries: {}</p><hr/>'.format(', '.join(queries))
                if item:
                    content_html += '<h2><a href="{}">{}</a></h2>'.format(item['url'], item['title'])
                    content_html += '<p>From {}<br/>By {}<br/>{}</p>'.format(item_source, item['author']['name'], item['_display_date'])
                    item['content_html'] = content_html + item['content_html']
                else:
                    item = {}
                item['id'] = '{}-{}'.format(day['date'], quote_plus(trend['title']['query']))
                item['url'] = trend['shareUrl']
                item['title'] = trend['title']['query']
                item['author'] = {"name": "Google Trends"}
                feed_items.append(item)

        feed = utils.init_jsonfeed(args)
        feed['title'] = 'Google Trends'
        feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
