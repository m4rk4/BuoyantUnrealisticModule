import base64, feedparser, json, pybatchexecute, pytz, random, re
import curl_cffi, requests
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from lxml import etree
from urllib.parse import parse_qs, quote_plus, urlencode, urlsplit, unquote_plus
from yt_dlp import YoutubeDL

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    item = {}
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if split_url.netloc == 'news.google.com':
        return get_news(url, args, site_json, save_debug)
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
    elif split_url.netloc == 'docs.google.com' and 'forms' in paths:
        page_html = utils.get_url_html(url)
        if page_html:
            soup = BeautifulSoup(page_html, 'lxml')
            el = soup.find('meta', attrs={"property": "og:url"})
            if el:
                item['url'] = el['content']
            else:
                el = soup.find('meta', attrs={"itemprop": "embedURL"})
                if el:
                    item['url'] = el['content']
                else:
                    item['url'] = url
            item['id'] = item['url']
            el = soup.find('meta', attrs={"property": "og:title"})
            if el:
                item['title'] = el['content']
            el = soup.find('meta', attrs={"property": "og:image"})
            if el:
                item['image'] = el['content']
            el = soup.find('meta', attrs={"property": "og:description"})
            if el:
                item['summary'] = el['content']
            else:
                el = soup.find('meta', attrs={"itemprop": "description"})
                if el:
                    item['summary'] = el['content']
            item['content_html'] = utils.format_embed_preview(item)
            return item
    elif split_url.netloc == 'drive.google.com':
        ydl_opts = {
            "skip_download": True,
            "forcejson": True,
            "noprogress": True,
            "quiet": True
        }
        try:
            video_info = YoutubeDL(ydl_opts).extract_info(url, download=False)
        except:
            video_info = None
        if video_info and video_info.get('thumbnails'):
            if save_debug:
                utils.write_file(video_info, './debug/ytdl.json')
            item['url'] = video_info['url']
            item['title'] = video_info['fulltitle']
            img_src = utils.get_redirect_url(video_info['thumbnails'][0]['url'])
            img_src = re.sub(r'=s\d+', '=s1600', img_src)
            item['_image'] = 'https://wsrv.nl/?url=' + quote_plus(img_src)
            if video_info['ext'] == 'mp4':
                # https://drive.google.com/file/d/1-MsmrVJwHJl4hEa-fJlQ2lxVf6SfTC0z/preview
                video = utils.closest_dict(video_info['formats'], 'height', 720)
                if video:
                    item['_video'] = video['url']
                    item['_video_headers'] = video['http_headers']
                    item['_video_headers']['cookie'] = video['cookies']
                    video_src = config.server + '/proxy/' + url
                    item['content_html'] = utils.add_video(video_src, 'video/mp4', item['_image'], item['title'], use_videojs=True)
            else:
                item['content_html'] = utils.add_image(item['_image'], item['title'], link=url)
            return item
        if 'viewer' in paths:
            page_html = utils.get_url_html(url)
            if not page_html:
                return None
            soup = BeautifulSoup(page_html, 'lxml')
            el = soup.find('img', class_='drive-viewer-prerender-thumbnail')
            if el:
                img_src = el['src']
            else:
                el = soup.find('link', id='texmex-thumb')
                if el:
                    img_src = 'https://wsrv.nl/?url=' + quote_plus(el['href'])
            if el:
                item['title'] = soup.title.get_text()
                item['url'] = url
                caption = '<a href="{}">View document:</a> {}'.format(item['url'], item['title'])
                if img_src.startswith('/'):
                    item['_image'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, img_src)
                else:
                    item['_image'] = img_src
                item['content_html'] = utils.add_image(item['_image'], caption, link=url)
        elif 'preview' in paths:
            page_html = utils.get_url_html(url)
            if not page_html:
                return None
            img_src = ''
            m = re.search(r'https://lh3\.googleusercontent\.com/drive-viewer/[^"]+', page_html)
            if m:
                img_src = m.group(0).encode('utf-8').decode('unicode_escape')
            else:
                soup = BeautifulSoup(page_html, 'lxml')
                el = soup.find('link', id='texmex-thumb')
                if el:
                    img_src = 'https://wsrv.nl/?url=' + quote_plus(el['href'])
            if img_src:
                item['_image'] = img_src
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
            if '!1m3!' in url:
                m = re.search(r'!2d([\-\.0-9]+)', url)
                if m:
                    lon = m.group(1)
                m = re.search(r'!3d([\-\.0-9]+)', url)
                if m:
                    lat = m.group(1)
            elif '!1m7!' in url:
                m = re.search(r'!1d([\-\.0-9]+)', url)
                if m:
                    lat = m.group(1)
                m = re.search(r'!2d([\-\.0-9]+)', url)
                if m:
                    lon = m.group(1)
            if not (lat and lon):
                logger.warning('unable to parse lat & lon in ' + url)
                return None
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
        if '/rss' not in split_url.path:
            return get_trends(url, args, site_json, save_debug)
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


def get_trends(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    params = parse_qs(split_url.query)
    if 'geo' in params:
        geo = params['geo'][0]
    elif 'geo' in args:
        geo = args['geo']
    else:
        geo = 'US'

    if 'hl' in params:
        lang = params['hl'][0]
    elif 'lang' in args:
        lang = args['lang']
    else:
        lang = 'en-US'

    if 'hours' in params:
        hours = int(params['hours'][0])
    elif 'hours' in args:
        hours = int(args['hours'])
    else:
        hours = '24'

    if 'category' in params:
        cat = int(params['category'][0])
    elif 'category' in args:
        cat = int(args['category'])
    else:
        cat = 0

    r = curl_cffi.get(url, impersonate="chrome")
    if not r or r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, 'lxml')
    el = soup.find('script', string=re.compile(r'WIZ_global_data'))
    if not el:
        logger.warning('unable to find WIZ_global_data in ' + url)
        return None
    i = el.string.find('{')
    j = el.string.rfind('}') + 1
    wiz_global_data = json.loads(el.string[i:j])
    reqid = random.randint(10000, 99999)

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Chromium\";v=\"134\", \"Not:A-Brand\";v=\"24\", \"Microsoft Edge\";v=\"134\"",
        "sec-ch-ua-arch": "\"x86\"",
        "sec-ch-ua-bitness": "\"64\"",
        "sec-ch-ua-form-factors": "\"Desktop\"",
        "sec-ch-ua-full-version": "\"134.0.3124.93\"",
        "sec-ch-ua-full-version-list": "\"Chromium\";v=\"134.0.6998.178\", \"Not:A-Brand\";v=\"24.0.0.0\", \"Microsoft Edge\";v=\"134.0.3124.93\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-model": "\"\"",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-ch-ua-platform-version": "\"15.0.0\"",
        "sec-ch-ua-wow64": "?0",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-same-domain": "1"
    }

    # i0OFE = /FeTrendingService.ListTrends
    rpc = {
        "rpcid": "i0OFE",
        "args": [None, None, geo, 0, lang, hours, 1]
    }
    pbe = pybatchexecute.PreparedBatchExecute(rpcs=[rpc], host="trends.google.com", app=wiz_global_data['qwAQke'])
    params = {
        "rpcids": rpc['rpcid'],
        "source-path": "/trending",
        "f.sid": wiz_global_data['FdrFJe'],
        "bl": wiz_global_data['cfb2h'],
        "hl": lang,
        "_reqid": reqid,
        "rt": "c"
    }
    r = requests.post(pbe.url + '?' + urlencode(params), data=urlencode(pbe.data), headers=headers)
    if r.status_code != 200:
        logger.warning('unable to get FeTrendingService.ListTrends')
        return None
    batchexe = pybatchexecute.decode(r.text, rt=params['rt'])
    idx, rpcid, trend_list = batchexe[0]
    if save_debug:
        utils.write_file(trend_list, './debug/trends.json')

    i = 1
    n = 0
    feed_items = []
    for trend in trend_list[1]:
        print(trend[0], trend[10])
        if cat > 0:
            if cat not in trend[10]:
                continue
        item = {}
        # id = title:timestamp
        item['id'] = quote_plus(trend[0]) + ':' + str(trend[3][0])
        item['url'] = 'https://trends.google.com/trends/explore?q={}&date=now%201-d&geo={}&hl={}'.format(quote_plus(trend[0]), geo, lang)
        # item['url'] = 'https://www.google.com/search?q={}&hl=en-US&safe=active&ssui=on'.format(quote_plus(trend[0]), geo, lang)
        item['title'] = trend[0]
        tz_loc = pytz.timezone(config.local_tz)
        dt_loc = datetime.fromtimestamp(trend[3][0])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, False)
        item['author'] = {
            "name": "Google Trends"
        }
        item['authors'] = []
        item['authors'].append(item['author'])
        item['content_html'] = ''
        if len(trend[9]) > 0:
            item['content_html'] += '<h3>Trend breakdown</h3><p>'
            item['tags'] = []
            for j, tag in enumerate(trend[9]):
                item['tags'].append(tag)
                if j > 0:
                    item['content_html'] += ' &bull; '
                item['content_html'] += '<a href="https://trends.google.com/trends/explore?q={}&date=now%201-d&geo={}&hl={}">{}</a>'.format(quote_plus(tag), geo, lang, tag)
            item['content_html'] += '</p>'
    
        # /FeTrendingService.ListNews
        rpc = {
            "rpcid": "w4opAf",
            "args": [trend[-2], 3]
        }
        pbe = pybatchexecute.PreparedBatchExecute(rpcs=[rpc], host="trends.google.com", app=wiz_global_data['qwAQke'])
        params['rpcids'] = rpc['rpcid']
        params['_reqid'] = int(str(i) + str(reqid))
        i += 1
        # print(pbe.url + '?' + urlencode(params))
        # print(pbe.data)
        r = requests.post(pbe.url + '?' + urlencode(params), data=urlencode(pbe.data), headers=headers)
        if r.status_code == 200:
            batchexe = pybatchexecute.decode(r.text, rt=params['rt'])
            idx, rpcid, news_list = batchexe[0]
            if save_debug:
                utils.write_file(news_list, './debug/trend_news.json')
            item['content_html'] += '<h3>In the News</h3>'
            for news in news_list[0]:
                item['content_html'] += utils.add_embed(news[1])
            if 'image' not in item:
                item['image'] = news[-1]
        else:
            logger.warning('unable to get FeTrendingService.ListNews')
        feed_items.append(item)
        n += 1
        if ('max' in args and n == int(args['max'])) or n > 10:
            break

    feed = utils.init_jsonfeed(args)
    feed['title'] = 'Google Trends'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed


def get_news(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    params = parse_qs(split_url.query)
    if 'gl' in params:
        geo = params['gl'][0]
    elif 'geo' in args:
        geo = args['geo']
    else:
        geo = 'US'

    if 'hl' in params:
        lang = params['hl'][0]
    elif 'lang' in args:
        lang = args['lang']
    else:
        lang = 'en-US'

    if 'ceid' in params:
        ceid = params['ceid'][0]
    elif 'ceid' in args:
        ceid = args['ceid']
    else:
        ceid = 'US:en'

    r = curl_cffi.get(url, impersonate="chrome")
    if not r or r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, 'lxml')
    el = soup.find('script', string=re.compile(r'WIZ_global_data'))
    if not el:
        logger.warning('unable to find WIZ_global_data in ' + url)
        return None
    i = el.string.find('{')
    j = el.string.rfind('}') + 1
    wiz_global_data = json.loads(el.string[i:j])
    reqid = random.randint(10000, 99999)

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Chromium\";v=\"134\", \"Not:A-Brand\";v=\"24\", \"Microsoft Edge\";v=\"134\"",
        "sec-ch-ua-arch": "\"x86\"",
        "sec-ch-ua-bitness": "\"64\"",
        "sec-ch-ua-form-factors": "\"Desktop\"",
        "sec-ch-ua-full-version": "\"134.0.3124.93\"",
        "sec-ch-ua-full-version-list": "\"Chromium\";v=\"134.0.6998.178\", \"Not:A-Brand\";v=\"24.0.0.0\", \"Microsoft Edge\";v=\"134.0.3124.93\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-model": "\"\"",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-ch-ua-platform-version": "\"15.0.0\"",
        "sec-ch-ua-wow64": "?0",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-same-domain": "1"
    }

    # WuSwme = /WebAppApiRpcService.GetEditionFullFirstPage
    rpc = {
        "rpcid": "WuSwme",
        "args": ["waareq", [lang, geo, ["FINANCE_TOP_INDICES", "WEB_TEST_1_0_0"], None, None, 1, 1, ceid, None, -240, None, None, None, None, None, 0], paths[-1], None, None, None, None, None, None, None, None, None, 0, 1]
    }
    pbe = pybatchexecute.PreparedBatchExecute(rpcs=[rpc], host="news.google.com", app=wiz_global_data['qwAQke'])
    params = {
        "rpcids": rpc['rpcid'],
        "source-path": split_url.path,
        "f.sid": wiz_global_data['FdrFJe'],
        "bl": wiz_global_data['cfb2h'],
        "hl": lang,
        "gl": geo,
        "soc-app": 140,
        "soc-platform": 1,
        "soc-device": 1,
        "_reqid": reqid,
        "rt": "c"
    }
    r = requests.post(pbe.url + '?' + urlencode(params), data=urlencode(pbe.data), headers=headers)
    if r.status_code != 200:
        logger.warning('unable to get WebAppApiRpcService.GetEditionFullFirstPage (status code {})'.format(r.status_code))
        return None
    batchexe = pybatchexecute.decode(r.text, rt=params['rt'])
    idx, rpcid, news_page = batchexe[0]
    if save_debug:
        utils.write_file(news_page, './debug/news.json')

    item = {}
    item['id'] = split_url.path
    item['url'] = url
    item['title'] = news_page[2][0][2]

    # TODO: date

    item['author'] = {
        "name": "Google News"
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['content_html'] = ''
    for it in news_page[2][1][3]:
        if isinstance(it[-1], str):
            if it[-1].startswith('aa|ui|'):
                i = it[0]
                section = it[i]
                if isinstance(section[1], list):
                    if isinstance(section[1][1], str) and section[1][1].startswith('ui|'):
                        # section heading
                        item['content_html'] += '<h3>' + section[2] + '</h3>'
                        if section[-1][0][0][4] == 'TWITTER_RESULT_GROUP':
                            # https://news.google.com/stories/CAAqNggKIjBDQklTSGpvSmMzUnZjbmt0TXpZd1NoRUtEd2pydGFUT0RSRW1xeTdUVm5FNjlDZ0FQAQ?hl=en-US&gl=US&ceid=US%3Aen
                            for story in section[3]:
                                item['content_html'] += utils.add_embed(story[10][5])
                        elif section[-1][0][0][4] == 'NEWS_QUESTION_RESULT_GROUP':
                            # https://news.google.com/stories/CAAqNggKIjBDQklTSGpvSmMzUnZjbmt0TXpZd1NoRUtEd2ptbXJQUERSSG83cFJmemFHTGt5Z0FQAQ?hl=en-US&gl=US&ceid=US%3Aen
                            for story in section[3]:
                                j = story[0]
                                item['content_html'] += '<div style="font-weight:bold;">' + story[j][1] + '</div>'
                                item['content_html'] += '<p style="margin-left:2em;">' + story[j][2]
                                if story[j][7][1]:
                                    item['content_html'] += '<br><span style="font-size:0.8em;">Source: <a href="{}">{}</a> ({})</span>'.format(story[j][7][1], story[j][7][0], urlsplit(story[j][7][1]).netloc)
                                item['content_html'] += '</p>'
                        elif section[-1][0][0][4] == 'NEWS_TOP_COVERAGE_RESULT_GROUP' or section[-1][0][0][4] == 'NEWS_POINT_OF_VIEW_RESULT_GROUP' or section[-1][0][0][4] == 'NEWS_OPINION_RESULT_GROUP':
                            for story in section[3]:
                                j = story[0]
                                item['content_html'] += utils.add_embed(story[j][6])
                        else:
                            logger.warning('unhandled section type ' + section[-1][0][0][4])
                elif isinstance(section[1], str):
                    # section heading
                    item['content_html'] += '<h3>' + section[1] + '</h3>'
            elif re.search(r'^aa\|[^\|]+', it[-1]):
                story = it
                j = story[0]
                print('  ' + story[j][2] + ', ' + story[j][6])
                item['content_html'] += '<li><a href="{}">{}</a> ({})</li>'.format(story[j][6], story[j][2], urlsplit(story[j][6]).netloc)
    return item


def decode_news_url(url):
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
        return primary_url
    logger.warning('unhandled url ' + url)
    return url
