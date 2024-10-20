import base64, feedparser, json, pytz, random, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from lxml import etree
from urllib.parse import parse_qs, quote_plus, urlsplit, unquote_plus
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
        hours = params['hours'][0]
    elif 'hours' in args:
        hours = args['hours']
    else:
        hours = '24'

    page_url = 'https://trends.google.com/trending?geo={}&hl={}'.format(geo, lang)
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "sec-ch-ua": "\"Chromium\";v=\"128\", \"Not;A=Brand\";v=\"24\", \"Microsoft Edge\";v=\"128\"",
        "sec-ch-ua-arch": "\"x86\"",
        "sec-ch-ua-bitness": "\"64\"",
        "sec-ch-ua-form-factors": "\"Desktop\"",
        "sec-ch-ua-full-version": "\"128.0.2739.67\"",
        "sec-ch-ua-full-version-list": "\"Chromium\";v=\"128.0.6613.120\", \"Not;A=Brand\";v=\"24.0.0.0\", \"Microsoft Edge\";v=\"128.0.2739.67\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-model": "\"\"",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-ch-ua-platform-version": "\"15.0.0\"",
        "sec-ch-ua-wow64": "?0",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1"
    }
    page_html = utils.get_url_html(page_url, headers=headers)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile(r'WIZ_global_data'))
    if not el:
        logger.warning('unable to find WIZ_global_data in ' + page_url)
    i = el.string.find('{')
    j = el.string.rfind('}') + 1
    global_data = json.loads(el.string[i:j])

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Chromium\";v=\"128\", \"Not;A=Brand\";v=\"24\", \"Microsoft Edge\";v=\"128\"",
        "sec-ch-ua-arch": "\"x86\"",
        "sec-ch-ua-bitness": "\"64\"",
        "sec-ch-ua-form-factors": "\"Desktop\"",
        "sec-ch-ua-full-version": "\"128.0.2739.67\"",
        "sec-ch-ua-full-version-list": "\"Chromium\";v=\"128.0.6613.120\", \"Not;A=Brand\";v=\"24.0.0.0\", \"Microsoft Edge\";v=\"128.0.2739.67\"",
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
    # https://www.gstatic.com/_/mss/boq-trends/_/js/k=boq-trends.TrendsUi.en_US.gDt5arkdnmg.es5.O/ck=boq-trends.TrendsUi.S_W8qdbhHDA.L.W.O/am=IMGAtQ/d=1/exm=PIVayb,_b,_tp/excm=_b,_tp,trendingnowview/ed=1/wt=2/ujg=1/rs=APgalu4ZiufHJKC7aqz_TFDaDcr20_YDqQ/ee=EVNhjf:pw70Gc;EmZ2Bf:zr1jrb;JsbNhc:Xd8iUd;K5nYTd:ZDZcre;LBgRLc:SdcwHb;Me32dd:MEeYgc;NPKaK:SdcwHb;NSEoX:lazG7b;Pjplud:EEDORb;QGR0gd:Mlhmy;SNUn3:ZwDk9d;ScI3Yc:e7Hzgb;Uvc8o:VDovNc;YIZmRd:A1yn5d;a56pNe:JEfCwb;cEt90b:ws9Tlc;dIoSBb:SpsfSb;dowIGb:ebZ3mb;eBAeSb:zbML3c;iFQyKf:QIhFr;lOO0Vd:OTA3Ae;nAFL3:s39S4;oGtAuc:sOXFj;pXdRYb:MdUzUe;qafBPd:yDVVkb;qddgKe:xQtZb;wR5FRb:O1Gjze;xqZiqf:BBI74;yxTchf:KUM7Z;zxnPse:duFQFc/m=ws9Tlc,n73qwf,UUJqVe,IZT63,e5qFLc,O1Gjze,byfTOb,lsjVmc,xUdipf,OTA3Ae,A1yn5d,fKUV3e,aurFic,Ug7Xab,ZwDk9d,V3dDOb,U4Hp0d,sd0Qyf,Wvm6ze,TMHc6,V8fbed,XTf4dd,TNy4y,Fr52Od,qIjbeb,ehD6Ec,suD16d,PyXkxd,SFt34c,x6qQoe,O6y8ed,MpJwZc,PrPYRd,LEikZe,NwH0H,OmgaI,XVMNvd,L1AAkb,KUM7Z,Mlhmy,s39S4,duFQFc,lwddkf,gychg,w9hDv,EEDORb,RMhBfe,SdcwHb,aW3pY,pw70Gc,EFQ78c,Ulmmrd,ZfAoz,xQtZb,JNoxi,kWgXee,BVgquf,QIhFr,ovKuLd,yDVVkb,hc6Ubd,SpsfSb,ebZ3mb,Z5uLle,BBI74,ZDZcre,MdUzUe,A7fCU,zbML3c,zr1jrb,thbVbd,Uas9Hd,pjICDe
    # i0OFE = /FeTrendingService.ListTrends
    reqid = random.randint(10000, 99999)
    data_url = 'https://trends.google.com/{}/data/batchexecute?rpcids=i0OFE&source-path=%2Ftrending&f.sid={}8&bl={}&hl={}&_reqid=2{}&rt=c'.format(global_data['Im6cmf'], global_data['FdrFJe'], global_data['cfb2h'], lang, reqid)
    # data = "f.req=%5B%5B%5B%22i0OFE%22%2C%22%5Bnull%2Cnull%2C%5C%22US%5C%22%2C0%2C%5C%22{}%5C%22%2C24%2C1%5D%22%2Cnull%2C%22generic%22%5D%5D%5D&".format(lang)
    data = 'f.req=%5B%5B%5B%22i0OFE%22%2C%22%5Bnull%2Cnull%2C%5C%22{}%5C%22%2C0%2C%5C%22{}%5C%22%2C{}%2C1%5D%22%2Cnull%2C%22generic%22%5D%5D%5D&'.format(geo, lang, hours)
    list_trends = utils.post_url(data_url, data=data, headers=headers, r_text=True)
    if not list_trends:
        logger.warning('unable to get ListTrends data from ' + data_url)
        return None

    list_trends = re.sub(r'[\\]{2,}"', r'&quot;', list_trends).replace('\\', '')
    m = re.findall(r'\["([^"]+)"', list_trends)
    # remove dups
    trends = []
    [trends.append(x) for x in m if x not in trends]

    feed_items = []
    n_max = len(trends) - 3
    for n in range(1, 10):
        logger.debug('adding trend: ' + trends[n])
        item = {}
        i = list_trends.find(trends[n])
        j = list_trends.find(trends[n + 1])
        trend = list_trends[i - 2 : j - 4]

        # timestamp
        m = re.search(r'\[(\d+)\]', trend)

        item['id'] = m.group(1) + ':' + quote_plus(trends[n])
        item['url'] = 'https://trends.google.com/trends/explore?q={}&date=now%201-d&geo={}&hl={}'.format(quote_plus(trends[n]), geo, lang)
        item['title'] = trends[n]

        tz_loc = pytz.timezone(config.local_tz)
        dt_loc = datetime.fromtimestamp(int(m.group(1)))
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, False)

        item['author'] = {
            "name": "Google Trends"
        }
        item['authors'] = []
        item['authors'].append(item['author'])

        item['tags'] = []
        item['content_html'] = '<h3>Trend breakdown</h3>'
        i = trend.find(',["')
        j = trend.find('],[')
        for x in trend[i + 2 : j].split(','):
            tag = x.strip('"')
            if tag not in item['tags']:
                item['tags'].append(tag)
                item['content_html'] += '<a href="https://trends.google.com/trends/explore?q={}&date=now%201-d&geo={}&hl={}">{}</a>  '.format(quote_plus(tag), geo, lang, tag)

        i = trend[j + 2:].find('],[')
        n_articles = 3
        data = 'f.req=%5B%5B%5B%22w4opAf%22%2C%22%5B' + quote_plus(trend[j + 2 + i :][2:].replace('"', '\\"')) + '%2C{}%5D%22%2Cnull%2C%22generic%22%5D%5D%5D'.format(n_articles)
        # w4opAf = /FeTrendingService.ListNews
        data_url = 'https://trends.google.com/{}/data/batchexecute?rpcids=w4opAf&source-path=%2Ftrending&f.sid={}8&bl={}&hl={}&_reqid=3{}&rt=c'.format(global_data['Im6cmf'], global_data['FdrFJe'], global_data['cfb2h'], lang, reqid)
        list_news = utils.post_url(data_url, data=data, headers=headers, r_text=True)
        if list_news:
            item['content_html'] += '<h3>In the news</h3>'
            list_news = re.sub(r'\\u003d', '=', list_news).replace('\\', '')
            for m in re.findall(r'"(http[^"]+)"', list_news):
                if 'gstatic.com/images' in m:
                    if 'image' not in item:
                        item['image'] = m
                else:
                    item['content_html'] += utils.add_embed(m)
        feed_items.append(item)

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

    page_url = 'https://trends.google.com/trending?geo={}&hl={}'.format(geo, lang)
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "sec-ch-ua": "\"Chromium\";v=\"128\", \"Not;A=Brand\";v=\"24\", \"Microsoft Edge\";v=\"128\"",
        "sec-ch-ua-arch": "\"x86\"",
        "sec-ch-ua-bitness": "\"64\"",
        "sec-ch-ua-form-factors": "\"Desktop\"",
        "sec-ch-ua-full-version": "\"128.0.2739.67\"",
        "sec-ch-ua-full-version-list": "\"Chromium\";v=\"128.0.6613.120\", \"Not;A=Brand\";v=\"24.0.0.0\", \"Microsoft Edge\";v=\"128.0.2739.67\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-model": "\"\"",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-ch-ua-platform-version": "\"15.0.0\"",
        "sec-ch-ua-wow64": "?0",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1"
    }
    page_html = utils.get_url_html(page_url, headers=headers)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile(r'WIZ_global_data'))
    if not el:
        logger.warning('unable to find WIZ_global_data in ' + page_url)
    i = el.string.find('{')
    j = el.string.rfind('}') + 1
    global_data = json.loads(el.string[i:j])

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Chromium\";v=\"128\", \"Not;A=Brand\";v=\"24\", \"Microsoft Edge\";v=\"128\"",
        "sec-ch-ua-arch": "\"x86\"",
        "sec-ch-ua-bitness": "\"64\"",
        "sec-ch-ua-form-factors": "\"Desktop\"",
        "sec-ch-ua-full-version": "\"128.0.2739.79\"",
        "sec-ch-ua-full-version-list": "\"Chromium\";v=\"128.0.6613.138\", \"Not;A=Brand\";v=\"24.0.0.0\", \"Microsoft Edge\";v=\"128.0.2739.79\"",
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
    reqid = random.randint(10000, 99999)
    if split_url.path == '/home':
        # HOnZud = /SplashApiRpcService.GetHomeForYouPreviewSection
        # i6owq = /SplashApiRpcService.GetHomeNewsClustersSection
        # Rxtpc = /SplashApiRpcService.GetGaramondCarousel
        # M7NAJd = /SplashApiRpcService.GetHomeGenreModulesSection
        rpcids = 'M7NAJd'
        data = 'f.req=%5B%5B%5B%22M7NAJd%22%2C%22%5B%5C%22ghgmsreq%5C%22%2C%5B%5B%5C%22{0}%5C%22%2C%5C%22{1}%5C%22%2C%5B%5C%22FINANCE_TOP_INDICES%5C%22%2C%5C%22WEB_TEST_1_0_0%5C%22%5D%2Cnull%2Cnull%2C1%2C1%2C%5C%22{2}%5C%22%2Cnull%2C-240%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C0%5D%2C%5C%22{0}%5C%22%2C%5C%22{1}%5C%22%2C1%2C%5B2%2C4%2C8%5D%2C1%2C1%2C%5C%22675824581%5C%22%2C0%2C0%2Cnull%2C0%5D%5D%22%2Cnull%2C%221%22%5D%5D%5D'.format(lang, geo, quote_plus(ceid))
    else:
        # Qxytce = /SplashApiRpcService.GetTopicInfo
        # EAfJqe = /SplashApiRpcService.GetTopicSection
        rcpids = quote_plus('Qxytce,EAfJqe')
        data = 'f.req=%5B%5B%5B%22Qxytce%22%2C%22%5B%5C%22gtireq%5C%22%2C%5B%5B%5C%22{0}%5C%22%2C%5C%22{1}%5C%22%2C%5B%5C%22FINANCE_TOP_INDICES%5C%22%2C%5C%22WEB_TEST_1_0_0%5C%22%5D%2Cnull%2Cnull%2C1%2C1%2C%5C%22{2}%5C%22%2Cnull%2C-240%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C0%5D%2C%5C%22{0}%5C%22%2C%5C%22{1}%5C%22%2C1%2C%5B2%2C4%2C8%5D%2C1%2C1%2C%5C%22675824581%5C%22%2C0%2C0%2Cnull%2C0%5D%2C%5C%22{3}%5C%22%5D%22%2Cnull%2C%221%22%5D%2C%5B%22EAfJqe%22%2C%22%5B%5C%22gtsreq%5C%22%2C%5B%5B%5C%22{0}%5C%22%2C%5C%22{1}%5C%22%2C%5B%5C%22FINANCE_TOP_INDICES%5C%22%2C%5C%22WEB_TEST_1_0_0%5C%22%5D%2Cnull%2Cnull%2C1%2C1%2C%5C%22{2}%5C%22%2Cnull%2C-240%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C0%5D%2C%5C%22{0}%5C%22%2C%5C%22{1}%5C%22%2C1%2C%5B2%2C4%2C8%5D%2C1%2C1%2C%5C%22675824581%5C%22%2C0%2C0%2Cnull%2C0%5D%2Cnull%2C%5C%22{3}%5C%22%2C%5C%22%5C%22%5D%22%2Cnull%2C%223%22%5D%5D%5D&'.format(lang, geo, quote_plus(ceid), paths[-1])
    data_url = 'https://news.google.com{}/data/batchexecute?rpcids={}&source-path={}&f.sid={}&bl={}&hl={}&gl={}&soc-app=140&soc-platform=1&soc-device=1&_reqid=1{}&rt=c'.format(rcpids, global_data['Im6cmf'], quote_plus(split_url.path), global_data['FdrFJe'], global_data['cfb2h'], lang, geo, reqid)
