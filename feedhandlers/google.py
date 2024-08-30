import base64, feedparser, json, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from lxml import etree
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
        # https://trends.google.com/trending/rss?geo=US
        trends_xml = utils.get_url_content(url)
        if trends_xml:
            if save_debug:
                utils.write_file(trends_xml, './debug/feed.html')
            feed_items = []
            item = {}
            parser = etree.HTMLParser()
            tree = etree.fromstring(trends_xml, parser)
            for event, element in etree.iterwalk(tree, events=('start', 'end')):
                if event == 'start':
                    if element.prefix:
                        tag = element.tag.replace('{' + tree.nsmap[element.prefix] + '}', element.prefix + ':')
                    else:
                        tag = element.tag
                    # print(tag)
                    if tag == 'item':
                        item = {}
                        item['content_html'] = ''
                    if not item:
                        continue
                    if tag == 'title':
                        item['title'] = element.text
                        item['url'] = 'https://trends.google.com/trends/explore?q={}&date=now%201-d&geo=US&hl=en-US'.format(quote_plus(element.text))
                    elif tag == 'pubdate':
                        dt = dateutil.parser.parse(element.text).astimezone(timezone.utc)
                        item['date_published'] = dt.isoformat()
                        item['_timestamp'] = dt.timestamp()
                        item['_display_date'] = utils.format_display_date(dt)
                        item['id'] = item['title'] + ' ' + str(item['_timestamp'])
                    elif tag == 'ht:picture':
                        item['_image'] = element.text
                    elif tag == 'ht:approx_traffic':
                        item['content_html'] += '<h2>Search volume:' + element.text + '</h2>'
                    elif tag == 'ht:news_item_url':
                        item['content_html'] += utils.add_embed(element.text)
                elif event == 'end' and element.tag == 'item':
                    feed_items.append(item)
                    item = {}
            feed = utils.init_jsonfeed(args)
            feed['title'] = 'Google Trends'
            feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)

    elif split_url.netloc == 'news.google.com':
        # Top Stories: https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en
        #feed = rss.get_feed(url, args, site_json, save_debug, get_content)
        rss_html = utils.get_url_html(url)
        if not rss_html:
            return None
        if save_debug:
            utils.write_file(rss_html, './debug/feed.html')
        try:
            d = feedparser.parse(rss_html)
        except:
            logger.warning('Feedparser error ' + url)
            return None
        page_html = utils.get_url_html(url.replace('/rss', ''))
        if page_html:
            page_soup = BeautifulSoup(page_html, 'lxml')
        feed_items = []
        for entry in d.entries:
            item = {}
            item['id'] = entry.guid
            if page_html:
                el = page_soup.find('script', string=re.compile(item['id']))
                if el:
                    m = re.search(r'"{}".*?"channel_story_360:([^"]+)"'.format(item['id']), el.string)
                    if m:
                        item['url'] = 'https://news.google.com/stories/{}?hl=en-US&gl=US&ceid=US%3Aen'.format(m.group(1))
            dt = dateutil.parser.parse(entry.published)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
            item['author'] = {"name": "Google News"}
            item['content_html'] = ''
            if entry.description:
                if 'url' in item:
                    page_html = utils.get_url_html(item['url'])
                    if page_html and save_debug:
                        utils.write_file(page_html, './debug/page.html')
                else:
                    page_html = ''
                # soup = BeautifulSoup(entry.description, 'html.parser')
                # links = soup.find_all('a')
                links = re.findall(r'<a[^>]+href="([^"]+)"', entry.description)
                for link in links:
                    if save_debug:
                        logger.debug('finding content url for ' + link)
                    content_url = ''
                    paths = list(filter(None, urlsplit(link).path[1:].split('/')))
                    id = paths[-1]
                    if page_html:
                        el = page_soup.find('script', string=re.compile(id))
                        if el:
                            m = re.search(r'"{}".*?"(https://[^"]+)"'.format(id), el.string)
                            if m:
                                content_url = m.group(1)
                    if not content_url:
                        logger.warning('unable to find content url for ' + link)
                        continue
                    if save_debug:
                        logger.debug('getting content for ' + content_url)
                    entry_item = utils.get_content(content_url, {"embed": True}, False)
                    if entry_item:
                        if 'title' not in item and 'title' in entry_item:
                            item['title'] = entry_item['title']
                        if '_image' not in item and '_image' in entry_item:
                            item['_image'] = entry_item['_image']
                        if 'summary' not in item and 'summary' in entry_item:
                            item['summary'] = entry_item['summary']
                            item['content_html'] += '<p>' + item['summary'] + '</p>'
                        item['content_html'] += entry_item['content_html']
            else:
                entry_item = get_content(entry.link, {"embed": True}, site_json, save_debug)
                if entry_item:
                    if 'title' not in item and 'title' in entry_item:
                        item['title'] = entry_item['title']
                    if '_image' not in item and '_image' in entry_item:
                        item['_image'] = entry_item['_image']
                    if 'summary' not in item and 'summary' in entry_item:
                        item['summary'] = entry_item['summary']
                    item['content_html'] += entry_item['content_html']
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
        feed = utils.init_jsonfeed(args)
        feed['title'] = d.feed.title
        feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
