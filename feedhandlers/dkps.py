import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


headers = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "authorization": "Kxuf8ydmEkWc705YO6aenQ==WbJ8TPQ5H0ytJeYiAW3m6Q==",
    "cache-control": "no-cache",
    "content-type": "application/json",
    "device-info": "{\"viewport\":{\"agent\":\"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.31\",\"height\":1200,\"width\":1920}}",
    "pragma": "no-cache",
    "sec-ch-ua": "\"Microsoft Edge\";v=\"117\", \"Not;A=Brand\";v=\"8\", \"Chromium\";v=\"117\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.31"
}


content_data = {
    "contentRoute": "",
    "filterParams": {
        "filters": []
    },
    "userData": {
        "cookie": {
            "lastVisit": "",
            "historicalVisits": 1,
            "displayPrompt": False
        },
        "deviceInfo": {
            "model": "Windows NT 10.0",
            "platform": "web",
            "operatingSystem": "windows",
            "osVersion": "Windows NT 10.0; Win64; x64",
            "manufacturer": "Google Inc.",
            "isVirtual": False,
            "webViewVersion": "117.0.2045.31"
        }
    },
    "widgets": [
        "prompts"
    ]
}

contentbyfilter_data = {
    "filters": [],
    "template": [
        "article",
        "community-submission",
        "live-file"
    ],
    "size": 10,
    "from": 0
}


def get_content(url, args, site_json, save_debug=False):
    # the authorization (token) header is in https://dkpittsburghsports.com/main.92501dcea87b1f61.js
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    content_data['contentRoute'] = paths[-1]
    content_data['userData']['cookie']['lastVisit'] = re.sub(r'(\.\d{3})\d+$', r'\1Z', datetime.utcnow().isoformat())
    api_json = utils.post_url('https://dkpittsburghsports.com/api/public/content', json_data=content_data, headers=headers)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    article_json = api_json['data']['attributes']
    item = {}
    item['id'] = api_json['data']['id']
    item['url'] = 'https://dkpittsburghsports.com/' + article_json['slugUrl']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['createDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['modifiedDate'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    authors = []
    authors.append(article_json['author']['label'])
    if article_json.get('coAuthors'):
        for it in article_json['coAuthors']:
            authors.append(it['label'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if article_json.get('tag'):
        item['tags'].append(article_json['tag'])
    if article_json['seo'].get('keyInfo'):
        for it in article_json['seo']['keyInfo']:
            item['tags'].append(it['label'])
    if not item.get('tags'):
        del item['tags']

    if article_json['seo'].get('excerpt'):
        item['summary'] = article_json['seo']['excerpt']

    item['content_html'] = ''
    if article_json.get('bangHead'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['bangHead'])

    if article_json.get('featuredImage'):
        item['_image'] = 'https://dkpittsburghsports.com' + article_json['featuredImage']
        captions = []
        if article_json.get('imageCaption'):
            captions.append(article_json['imageCaption'])
        if article_json.get('imageCredit'):
            captions.append(article_json['imageCredit'])
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    soup = BeautifulSoup(article_json['content'], 'html.parser')
    for el in soup.find_all(class_='ad-inline'):
        el.decompose()

    for el in soup.find_all('section', class_='articleImage'):
        if el.name == None:
            continue
        new_html = ''
        it = el.find('img')
        if it:
            img_src = 'https://dkpittsburghsports.com' + it['src']
            captions = []
            it = el.find(class_='photoCaption')
            if it:
                captions.append(it.decode_contents())
            it = el.find(class_='photoCredit')
            if it:
                captions.append(it.decode_contents())
            if not captions:
                next_el = el.find_next_sibling()
                if next_el and next_el.get('class') and 'articleImage' in next_el['class']:
                    if not next_el.find('img'):
                        it = next_el.find(class_='photoCaption')
                        if it:
                            captions.append(it.decode_contents())
                        it = next_el.find(class_='photoCredit')
                        if it:
                            captions.append(it.decode_contents())
                        if captions:
                            next_el.decompose()
            new_html = utils.add_image(img_src, ' | '.join(captions))
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled articleImage in ' + item['url'])

    for el in soup.find_all('div', class_='twitter'):
        links = el.find_all('a')
        new_html = utils.add_embed(links[-1]['href'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        if el.parent and (el.parent.name == 'p' or (el.parent.get('class') and 'embed-responsive' in el.parent['class'])):
            el.parent.insert_after(new_el)
            if len(el.parent.find_all('iframe')) == 1:
                el.parent.decompose()
            else:
                el.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()

    item['content_html'] += str(soup)

    if article_json['template'] == 'live-file':
        live_feed = utils.post_url('https://dkpittsburghsports.com/api/public/liveFileItems', json_data={"liveFileId": article_json['sourceId']}, headers=headers)
        if live_feed:
            if save_debug:
                utils.write_file(live_feed, './debug/live.json')
            for live_item in live_feed['data']:
                item['content_html'] += '<hr/>'
                avatar = '{}/image?url={}&width=48&height=48&mask=ellipse'.format(config.server, quote_plus('https://dkpittsburghsports.com' + live_item['attributes']['avatarUrl']))
                dt = datetime.fromisoformat(live_item['createdOn'].replace('Z', '+00:00'))
                item['content_html'] += '<table><tr><td style="width:48px;"><img src="{}" /></td><td><b>{}</b><br/><small>{}</small></td></tr></table>'.format(avatar, live_item['attributes']['from']['display'], utils.format_display_date(dt))
                item['content_html'] += re.sub(r'(</?)div>', r'\1p>', live_item['content'])
                if live_item['attributes'].get('attachments'):
                    for attachment in live_item['attributes']['attachments']:
                        if attachment.get('raw'):
                            if attachment['raw']['type'] == 'twitter':
                                item['content_html'] += utils.add_embed(attachment['raw']['attachment'])
                            elif attachment['raw']['type'] == 'image':
                                item['content_html'] += utils.add_image(attachment['raw']['attachment'].replace('&name=small', ''))
                            else:
                                logger.warning('unhandled live raw attachment type {} in {}'.format(attachment['raw']['type'], live_item['id']))
                        else:
                            logger.warning('unhandled live item attachment in item ' + live_item['id'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    feed_title = ''
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        content_data['contentRoute'] = 'homepage'
        content_data['userData']['cookie']['lastVisit'] = re.sub(r'(\.\d{3})\d+$', r'\1Z', datetime.utcnow().isoformat())
        api_json = utils.post_url('https://dkpittsburghsports.com/api/public/content', json_data=content_data, headers=headers)
        if not api_json:
            return None
        feed_title = 'DK Pittsburgh Sports'
    elif paths[0] == 'team':
        content_data['contentRoute'] = '-'.join(paths)
        content_data['userData']['cookie']['lastVisit'] = re.sub(r'(\.\d{3})\d+$', r'\1Z', datetime.utcnow().isoformat())
        api_json = utils.post_url('https://dkpittsburghsports.com/api/public/content', json_data=content_data, headers=headers)
        if not api_json:
            return None
        feed_title = '{} | DK Pittsburgh Sports'.format(api_json['data']['name'])
    elif paths[0] == 'tag':
        content_filter = {
            "property": "specs.tag",
            "values": [
                paths[1]
            ]
        }
        contentbyfilter_data['filters'] = [content_filter]
        api_json = utils.post_url('https://dkpittsburghsports.com/api/public/contentByFilters', json_data=contentbyfilter_data, headers=headers)
        if not api_json:
            return None
        feed_title = paths[1].replace('-', ' ').title()
    elif paths[0] == 'author':
        content_filter = {
            "property": "specs.author",
            "values": [
                paths[1]
            ]
        }
        content_data['contentRoute'] = paths[1]
        content_data['userData']['cookie']['lastVisit'] = re.sub(r'(\.\d{3})\d+$', r'\1Z', datetime.utcnow().isoformat())
        api_json = utils.post_url('https://dkpittsburghsports.com/api/public/content', json_data=content_data, headers=headers)
        if api_json:
            content_filter['values'].append(api_json['data']['name'])
            feed_title = '{} | DK Pittsburgh Sports'.format(api_json['data']['name'])
        contentbyfilter_data['filters'] = [content_filter]
        api_json = utils.post_url('https://dkpittsburghsports.com/api/public/contentByFilters', json_data=contentbyfilter_data, headers=headers)
        if not api_json:
            return None

    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    articles = []
    if api_json['data'].get('records'):
        articles = api_json['data']['records']
    elif api_json['data'].get('attributes'):
        if api_json['data']['attributes'].get('featuredArticle'):
            articles.append(api_json['data']['attributes']['featuredArticle'])
        if api_json['data']['attributes'].get('sections'):
            for section in api_json['data']['attributes']['sections']:
                if section.get('filters'):
                    for sec_filter in section['filters']:
                        for val in sec_filter['values']:
                            articles.append(val)
        if api_json['data']['attributes'].get('navSections'):
            for section in api_json['data']['attributes']['navSections']:
                if isinstance(section['data'], list):
                    for data in section['data']:
                        if data.get('filters'):
                            for data_filter in data['filters']:
                                for val in data_filter['values']:
                                    print(val['slugUrl'])
                                    articles.append(val)

    n = 0
    feed_items = []
    for article in articles:
        if next((it for it in feed_items if it['id'] == article['slug']), None):
            continue
        article_url = 'https://dkpittsburghsports.com/' + article['slugUrl']
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
    if feed_title:
        feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed