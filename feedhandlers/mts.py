import html, json, pytz, random, re, requests, string, tldextract
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    # Check recent articles in the homepage feed - this is the only way to guarantee getting the full content
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    article_id = int(paths[1])
    tld = tldextract.extract(args['url'])
    sites_json = utils.read_json_file('./sites.json')
    for api_url in sites_json[tld.domain]['homepage_feed']:
        api_json = utils.get_url_json(re.sub(r'&to=\d+', '&to=20', api_url))
        article = next((it for it in api_json if it['Id'] == article_id), None)
        if article:
            return get_item(article, args, save_debug)

    if save_debug:
        logger.debug('article not found in feed, trying to get content from widget')

    # Try to load the widget to get the content
    session = requests.Session()
    r = session.get(url)
    widget_url = '{}://{}/api/widget/getWidget.aspx?loggedIn=false&callback=MTS_widgetCallback'.format(split_url.scheme, split_url.netloc)
    headers = {
        "accept": "text/javascript, application/javascript, application/ecmascript, application/x-ecmascript, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "credentials": "include",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "referrer": url,
        "sec-ch-ua": "\"Microsoft Edge\";v=\"105\", \"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"105\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 Edg/105.0.1343.53",
        "x-requested-with": "XMLHttpRequest"
    }
    post_data = 'page_23_0=%2FContent%2FStoryWrapper.aspx&query_23_0=showPrintData%3Dtrue%26id%3D{0}%26&count_23=1&page_24_0=%2FContent%2FPhotoSlider.aspx&query_24_0=includeAuthor%3D%26hideTitle%3D%26sliderMode%3DNewsItem%26arrowsOutside%3Dfalse%26excludeCounter%3D%26excludeSummary%3Dfalse%26renameHeader%3D%26hideHeader%3Dtrue%26types%3D%26id%3D{0}%26&count_24=1&count=75'.format(article_id)
    #session_id = ''.join(random.choices(string.ascii_letters + string.digits, k=24))
    #cookies = {'ASP.NET_SessionId': session_id, 'path': '/'}
    widget_data = session.post(widget_url, data=post_data, headers=headers)
    if not widget_data:
        return None
    widget_json = json.loads(widget_data.text[19:-2])
    if save_debug:
        utils.write_file(widget_json, './debug/debug.json')
    soup = BeautifulSoup(widget_json['23_0'], 'html.parser')
    if save_debug:
        utils.write_file(str(soup), './debug/debug.html')

    item = {}
    el = soup.find(class_='body')
    if el:
        item['content_html'] = el.decode_contents()
    else:
        logger.warning('unable to get full content for ' + url)
        return None

    item['id'] = article_id
    item['url'] = url

    el = soup.find(class_='title')
    if el:
        item['title'] = el.get_text()

    el = soup.find('time')
    if el:
        date = re.sub(r'([+-])(\d\d)(\d\d)$', r'\1\2:\3', el['datetime'])
        dt = datetime.fromisoformat(date).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    el = soup.find(class_='authorDisplay')
    if el:
        item['author'] = {"name": el.decode_contents().replace('<br/>', ', ')}

    el = soup.find(class_='summary')
    if el:
        item['summary'] = el['value']

    soup = BeautifulSoup(widget_json['24_0'], 'html.parser')
    if save_debug:
        utils.write_file(str(soup), './debug/debug.html')
    m = re.search(r'_MTS_album.push\((.*?)\);', widget_json['24_0'], flags=re.S)
    if m:
        album_json = json.loads(m.group(1))
        el = soup.find(id='featFoto')
        if el:
            for i, img in enumerate(el.find_all('img')):
                m = re.search(r'/(\d+)_\d$', img['data-original'])
                if m:
                    image = next((it for it in album_json['images'] if it['id'] == int(m.group(1))), None)
                    if image:
                        captions = []
                        if image.get('title'):
                            captions.append(image['title'])
                        if image.get('credit'):
                            captions.append(image['credit'])
                        if i == 0:
                            item['content_html'] = utils.add_image(img['data-original'], ' | '.join(captions)) + item['content_html']
                            item['_image'] = img['data-original']
                        elif i == 1:
                            item['content_html'] += '<h3>Featured Media</h3>'
                            item['content_html'] += utils.add_image(img['data-original'], ' | '.join(captions))
                        else:
                            item['content_html'] += utils.add_image(img['data-original'], ' | '.join(captions))
        else:
            logger.warning('no featFoto found in ' + url)
    else:
        logger.warning('no MTS_album info found in ' + url)

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_item(article_json, args, save_debug):
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')
    item = {}
    item['id'] = article_json['Id']
    item['url'] = article_json['Link']
    item['title'] = article_json['Title']

    if article_json['PostDate']['ZoneId'] == 'Eastern Standard Time':
        tz_loc = pytz.timezone('US/Eastern')
    else:
        logger.warning('unhandled timezone in ' + item['url'])
        tz_loc = pytz.timezone('US/Eastern')

    date = article_json['PostDate']['Date']
    m = re.search(r'\.(\d{1,2})$', date)
    if m:
        date = date.replace(m.group(0), '.{}'.format(m.group(1).zfill(3)))
    dt_loc = datetime.fromisoformat(date)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    date = article_json['LastEditDate']['Date']
    m = re.search(r'\.(\d{1,2})$', date)
    if m:
        date = date.replace(m.group(0), '.{}'.format(m.group(1).zfill(3)))
    dt_loc = datetime.fromisoformat(date)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    item['author']['name'] = article_json['AuthorInfo']['Name'].replace('\n', ', ')

    item['tags'] = []
    for it in article_json['TagList']:
        if it.get('getTitle'):
            item['tags'].append(it['getTitle'])

    item['summary'] = article_json['Summary']

    item['content_html'] = html.unescape(article_json['Body'])

    if article_json.get('MediaList'):
        # Assumes all media are images
        for i, media in enumerate(article_json['MediaList']):
            captions = []
            if media.get('Title'):
                captions.append(media['Title'])
            if media.get('Credit'):
                captions.append(media['Credit'])
            if i == 0:
                item['_image'] = media['ImgLink']
                item['content_html'] = utils.add_image(media['ImgLink'], ' | '.join(captions)) + item['content_html']
            elif i == 1:
                item['content_html'] += '<h3>Featured Media</h3>'
                item['content_html'] += utils.add_image(media['ImgLink'], ' | '.join(captions))
            else:
                item['content_html'] += utils.add_image(media['ImgLink'], ' | '.join(captions))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(args, save_debug=False):
    tld = tldextract.extract(args['url'])
    sites_json = utils.read_json_file('./sites.json')
    portal_id = sites_json[tld.domain]['portal_id']

    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) == 0:
        articles = []
        for api_url in sites_json[tld.domain]['homepage_feed']:
            api_json = utils.get_url_json(api_url)
            if api_json:
                for article in api_json:
                    if not next((it for it in articles if it['Id'] == article['Id']), None):
                        print(article['Link'])
                        articles.append(article.copy())
    elif paths[0] == 'news-category':
        if len(paths) == 3:
            # https://medina-gazette.com/news-category/sports/7/
            category = paths[1]
            api_url = '{}://{}/api/v1/portal/news/all/?portal_id={}&from=1&to=15&category={}&filter_id=&filter_type=Category'.format(split_url.scheme, split_url.netloc, portal_id, category)
            articles = utils.get_url_json(api_url)
        elif len(paths) > 3:
            # https://medina-gazette.com/news-category/sports/guardians-notes/7/29/
            category = paths[1]
            subcat = paths[2].replace('-', '%20')
            filter_id = paths[-1]
            api_url = '{}://{}/api/v1/portal/news/all/?portal_id={}&from=1&to=10&category={}&filter_id={}&filter_type=SubCategory&subcategory={}'.format(split_url.scheme, split_url.netloc, portal_id, category, filter_id, subcat)
            articles = utils.get_url_json(api_url)

    if not articles:
        logger.warning('no articles found')
        return None
    if save_debug:
        utils.write_file(articles, './debug/feed.json')

    n = 0
    feed_items = []
    for article in articles:
        if save_debug:
            logger.debug('getting content for ' + article['Link'])
        item = get_item(article, args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    #if feed_title:
    #    feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed