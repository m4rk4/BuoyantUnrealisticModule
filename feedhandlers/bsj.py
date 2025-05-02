import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from random import randrange
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


# authorization token in https://www.bostonsportsjournal.com/main.605fa37cbe82fe86.js
headers = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "authorization": "Kxuf8ydmEkWc705YO6aenQ==WbJ8TPQ5H0ytJeYiAW3m6Q==",
    "cache-control": "no-cache",
    "content-type": "application/json",
    "device-info": "{\"viewport\":{\"agent\":\"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.2088.46\",\"height\":1200,\"width\":1920}}",
    "pragma": "no-cache",
    "sec-ch-ua": "\"Chromium\";v=\"118\", \"Microsoft Edge\";v=\"118\", \"Not=A?Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.2088.46"
}

api_data = {
    "contentRoute": "",
    "filterParams": {
        "filters": []
    },
    "userData": {
        "cookie": {
            "lastVisit": "",
            "historicalVisits": 0,
            "displayPrompt": False
        },
        "deviceInfo": {
            "model": "Windows NT 10.0",
            "platform": "web",
            "operatingSystem": "windows",
            "osVersion": "Windows NT 10.0; Win64; x64",
            "manufacturer": "Google Inc.",
            "isVirtual": False,
            "webViewVersion": "118.0.2088.46"
        }
    },
    "widgets": [
        "prompts"
    ]
}


def random_date(delta=None):
    # Based on https://stackoverflow.com/questions/553303/generate-a-random-date-between-two-other-dates
    if not delta:
        delta = timedelta(days=-1)
    int_delta = (delta.days * 24 * 60 * 60) + delta.seconds
    random_second = randrange(abs(int_delta))
    if int_delta < 0:
        random_second = -random_second
    rand_dt = datetime.now(timezone.utc) + timedelta(seconds=random_second)
    # format 2023-10-19T20:33:38.864Z
    return rand_dt.isoformat(timespec='milliseconds') + 'Z'


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    api_data['contentRoute'] = paths[-1]
    api_data['userData']['cookie']['lastVisit'] = random_date()
    api_json = utils.post_url('https://www.bostonsportsjournal.com/api/public/content', json_data=api_data, headers=headers)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    article_json = api_json['data']['attributes']
    item = {}
    item['id'] = api_json['data']['id']
    item['url'] = 'https://www.bostonsportsjournal.com/' + article_json['slugUrl']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(api_json['data']['publishedOn'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(api_json['data']['lastModifiedOn'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    authors = []
    authors.append(article_json['author']['label'])
    if article_json.get('coAuthors'):
        for it in article_json['coAuthors']:
            authors.append(it['label'])
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if article_json['seo'].get('keyInfo'):
        for it in article_json['seo']['keyInfo']:
            item['tags'].append(it['label'])
    if article_json.get('specs'):
        for it in article_json['specs']:
            item['tags'].append(it['value'])

    item['content_html'] = ''
    if article_json.get('featuredImage'):
        item['_image'] = 'https://www.bostonsportsjournal.com/' + article_json['featuredImage']
        if not article_json.get('types') or 'video' not in article_json['types']:
            captions = []
            if article_json.get('imageCaption'):
                captions.append(article_json['imageCaption'])
            if article_json.get('imageCredit'):
                captions.append(article_json['imageCredit'])
            item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    if article_json.get('excerpt'):
        item['summary'] = article_json['excerpt']

    soup = BeautifulSoup(article_json['content'], 'html.parser')
    for el in soup.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        if el.parent and el.parent.name == 'div':
            el.parent.insert_after(new_el)
            el.parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all('div', class_='twitter'):
        links = el.find_all('a')
        new_html = utils.add_embed(links[-1]['href'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.select('p > a[href=\"https://www.bostonsportsjournal.com/subscribe\"]'):
        el.parent.decompose()

    item['content_html'] += str(soup)

    if article_json.get('isPremium'):
        item['content_html'] += '<h3 style="text-align:center; color:red;">This is a premium article that requires a subscription for the full content.</h3>'

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    articles = []
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    api_data['userData']['cookie']['lastVisit'] = random_date()
    if len(paths) == 0:
        feed_title = 'Boston Sports Journal'
        api_data['contentRoute'] = 'homepage'
        api_json = utils.post_url('https://www.bostonsportsjournal.com/api/public/content', json_data=api_data, headers=headers)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')
        articles.append(api_json['data']['attributes']['featuredArticle']['slugUrl'])
        if api_json['data']['attributes'].get('navSections'):
            for section in api_json['data']['attributes']['navSections']:
                for data in section['data']:
                    for filtr in data['filters']:
                        for value in filtr['values']:
                            articles.append(value['slugUrl'])
    elif 'team' in paths or 'tag' in paths or 'author' in paths:
        if paths[0] == 'tag':
            filter_prop = 'specs.tag'
            filter_val = [paths[1]]
            feed_title = paths[1].replace('-', ' ').title() + ' | Boston Sports Journal'
        elif paths[0] == 'team':
            if paths[1] == 'redsox':
                filter_prop = 'specs.tag'
                filter_val = ['boston-red-sox']
                feed_title = 'Red Sox | Boston Sports Journal'
            elif paths[1] == 'celtics':
                filter_prop = 'specs.tag'
                filter_val = ['boston-celtics']
                feed_title = 'Celtics | Boston Sports Journal'
            elif paths[1] == 'bruins':
                filter_prop = 'specs.tag'
                filter_val = ['boston-bruins']
                feed_title = 'Bruins | Boston Sports Journal'
            elif paths[1] == 'patriots':
                filter_prop = 'specs.tag'
                filter_val = ['new-england-patriots']
                feed_title = 'Patriots | Boston Sports Journal'
        elif 'author' in paths:
            api_data['contentRoute'] = paths[1]
            api_json = utils.post_url('https://www.bostonsportsjournal.com/api/public/content', json_data=api_data, headers=headers)
            if api_json:
                if save_debug:
                    utils.write_file(api_json, './debug/feed.json')
                filter_prop = 'specs.author'
                filter_val = [api_json['data']['name'], api_json['data']['attributes']['title'], api_json['data']['id']]
                feed_title = api_json['data']['name'] + ' | Boston Sports Journal'
            else:
                filter_prop = 'specs.author'
                filter_val = [paths[1]]
                feed_title = paths[1].replace('-', ' ').title() + ' | Boston Sports Journal'
        data = {
            "filters": [
                {
                    "property": filter_prop,
                    "values": filter_val
                },
                {}
            ],
            "template": [
                "article",
                "community-submission",
                "live-file"
            ],
            "size":10
        }
        api_json = utils.post_url('https://www.bostonsportsjournal.com/api/public/contentByFilters', json_data=data, headers=headers)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')
        for record in api_json['data']['records']:
            articles.append(record['slugUrl'])

    if articles:
        n = 0
        feed_items = []
        for article in articles:
            article_url = 'https://www.bostonsportsjournal.com/' + article
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
        feed['title'] = feed_title
        feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
