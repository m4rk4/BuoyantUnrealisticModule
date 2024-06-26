import base64, feedparser, json, re
from bs4 import BeautifulSoup
from urllib.parse import parse_qs, quote_plus, urlsplit, unquote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    item = {}
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if split_url.netloc == 'news.google.com':
        # https://stackoverflow.com/questions/51131834/decoding-encoded-google-news-urls
        primary_url = ''
        _ENCODED_URL_PREFIX = "https://news.google.com/rss/articles/"
        _ENCODED_URL_RE = re.compile(fr"^{re.escape(_ENCODED_URL_PREFIX)}(?P<encoded_url>[^?]+)")
        _DECODED_URL_RE = re.compile(rb'^\x08\x13".+?(?P<primary_url>http[^\xd2]+)\xd2\x01')
        match = _ENCODED_URL_RE.match(url)
        if match:
            encoded_text = match.groupdict()["encoded_url"]
            encoded_text += "==="
            decoded_text = base64.urlsafe_b64decode(encoded_text)
            match = _DECODED_URL_RE.match(decoded_text)
            if match:
                primary_url = match.groupdict()["primary_url"]
                primary_url = primary_url.decode()
        if primary_url:
            logger.debug('getting content for ' + primary_url)
            item = utils.get_content(primary_url, args, save_debug)
        else:
            logger.warning('unhandled url ' + url)
    elif split_url.netloc == 'docs.google.com' and 'gview' in paths:
        # https://docs.google.com/gview?url=https://static.fox5atlanta.com/www.fox5atlanta.com/content/uploads/2023/09/23.09.07_DOJ-Letter-re-Clayton-County-Jail.pdf
        query = parse_qs(split_url.query)
        item['url'] = query['url'][0]
        page_html = utils.get_url_html(url)
        if page_html:
            soup = BeautifulSoup(page_html, 'lxml')
            item['title'] = soup.title.get_text()
            el = soup.find('img', class_='drive-viewer-prerender-thumbnail')
            if el:
                item['_image'] = 'https://docs.google.com' + el['src']
                caption = '<a href="{}">{}</a>'.format(item['url'], item['title'])
                item['content_html'] = utils.add_image(item['_image'], item['title'], link=item['url'])
            else:
                item['content_html'] = '<table><tr><td style="width:3em;"><span style="font-size:3em;">🗎</span></td><td><a href="{}">{}</a></td></tr></table>'.format(item['url'], item['title'])
        else:
            item['content_html'] = '<table><tr><td style="width:3em;"><span style="font-size:3em;">🗎</span></td><td><a href="{0}">{0}</a></td></tr></table>'.format(item['url'])
    elif split_url.netloc == 'drive.google.com':
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
            m = re.search(r'https://lh3\.googleusercontent\.com/drive-viewer/[^"]+', page_html)
            if m:
                item['_image'] = m.group(0).encode('utf-8').decode('unicode_escape')
                soup = BeautifulSoup(page_html, 'lxml')
                caption = '<a href="{}">View document</a>'.format(url)
                el = soup.find('meta', attrs={"property": "og:title"})
                if el:
                    caption += ': ' + el['content']
                item['content_html'] = utils.add_image(item['_image'], caption, link=url)
    elif split_url.netloc == 'maps.google.com' or paths[0] == 'maps':
        # URL format: https://andrewwhitby.com/2014/09/09/google-maps-new-embed-format/
        # Staticmap: https://github.com/komoot/staticmap
        query = parse_qs(split_url.query)
        if query.get('pb'):
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
                item['url'] = 'https://www.google.com/maps/search/{}/@{},{},15z'.format(quote_plus(item['title']), lat, lon)
            else:
                item['title'] = ''
                item['url'] = 'https://www.google.com/maps/@{},{},15z'.format(lat, lon)
            item['_image'] = '{}/map?lat={}&lon={}'.format(config.server, lat, lon)
            item['content_html'] = utils.add_image(item['_image'], item['title'], link=item['url'])
        elif 'place' in paths and query.get('q'):
            lat = ''
            lon = ''
            # https://www.google.com/maps/embed/v1/place?key=API_KEY&q=Space+Needle,Seattle+WA
            osm_search = utils.get_url_json('https://nominatim.openstreetmap.org/search?q={}&format=json'.format(quote_plus(query['q'][0])))
            if osm_search:
                lat = osm_search[0]['lat']
                lon = osm_search[0]['lon']
                title = osm_search[0]['display_name']
            else:
                page_html = utils.get_url_html(url)
                if page_html:
                    m = re.search(r'\[(-?\d+\.\d+),(-?\d+\.\d+)\]', page_html)
                    if m:
                        lat = m.group(1)
                        lon = m.group(2)
                        title = unquote_plus(query['q'][0])
            if lat and lon:
                item = {}
                item['title'] = title
                item['url'] = 'https://www.google.com/maps/search/{}/@{},{},15z'.format(quote_plus(query['q'][0]), lat, lon)
                item['_image'] = '{}/map?lat={}&lon={}'.format(config.server, lat, lon)
                item['content_html'] = utils.add_image(item['_image'], item['title'], link=item['url'])
            else:
                logger.warning('unable to find place {} in {}'.format(query['q'][0], url))
                return None
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

    elif split_url.netloc == 'news.google.com':
        #feed = rss.get_feed(url, args, site_json, save_debug, get_content)
        news_feed = utils.get_url_html(url)
        if not news_feed:
            return None
        try:
            d = feedparser.parse(news_feed)
        except:
            logger.warning('Feedparser error ' + url)
            return None
        feed_items = []
        for entry in d.entries:
            if save_debug:
                logger.debug('getting content for ' + entry.link)
            item = get_content(entry.link, args, site_json, save_debug)
            if not item and entry.description:
                soup = BeautifulSoup(entry.description, 'html.parser')
                for link in soup.find_all('a'):
                    item = get_content(link, args, site_json, save_debug)
                    if item:
                        break
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
        feed['title'] = 'Google News'
        feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
