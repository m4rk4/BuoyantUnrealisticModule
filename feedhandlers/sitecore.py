import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    api_url = '{}://{}/sitecore/api/layout/render/jss?item={}&sc_lang=en-US&sc_apikey={}'.format(split_url.scheme, split_url.netloc, quote_plus(split_url.path), quote_plus(site_json['sitecoreApiKey']))
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id'] = api_json['sitecore']['route']['itemId']
    item['url'] = api_json['sitecore']['context']['httpContext']['url']

    fields = api_json['sitecore']['route']['fields']

    if fields['ogTitle'].get('value'):
        item['title'] = fields['ogTitle']['value']
    elif fields['pageTitle'].get('value'):
        item['title'] = fields['pageTitle']['value']

    dt = datetime.fromisoformat(fields['storyDate']['value'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if fields['author'].get('value'):
        item['author'] = {"name": fields['author']['value']}
    else:
        item['author'] = {"name": api_json['sitecore']['context']['site']['name']}

    item['tags'] = []
    if fields['category'].get('name'):
        item['tags'].append(fields['category']['name'])
    if fields.get('tags'):
        for it in fields['tags']:
            item['tags'].append(it['name'])

    if fields['metaDescription'].get('value'):
        item['summary'] = fields['metaDescription']['value']
    elif fields['ogDescription'].get('value'):
        item['summary'] = fields['ogDescription']['value']

    item['content_html'] = ''
    if fields['storyHeading'].get('value') and fields['storyHeading']['value'].lower() != item['title'].lower():
        item['content_html'] += '<p><em>' + fields['storyHeading']['value'] + '</em></p>'

    if fields['subTitle'].get('value'):
        item['content_html'] += '<p><em>' + fields['subTitle']['value'] + '</em></p>'

    if fields['metaImage'].get('value'):
        item['_image'] = fields['metaImage']['value']['src']
    elif fields['thumbnailImage'].get('value'):
        item['_image'] = fields['thumbnailImage']['value']['src']
    if item.get('_image'):
        item['content_html'] += utils.add_image(item['_image'], fields['thumbnailImageText'].get('value'))

    for jss_main in api_json['sitecore']['route']['placeholders']['jss-main']:
        for key, val in jss_main['placeholders'].items():
            if key == 'jss-layout-story-template':
                for component in val:
                    if component['componentName'] == 'TextBlock':
                        # TODO: component['fields']['heading']
                        soup = BeautifulSoup(component['fields']['bodyText']['value'], 'html.parser')
                        for el in soup.find_all('div', class_='twitter-tweet'):
                            it = el.find('iframe')
                            if it and it.get('data-tweet-id'):
                                new_html = utils.add_embed('https://twitter.com/__/status/{}'.format(it['data-tweet-id']))
                                new_el = BeautifulSoup(new_html, 'html.parser')
                                if el.parent and el.parent.name == 'center':
                                    el.parent.replace_with(new_el)
                                else:
                                    el.replace_with(new_el)
                        for el in soup.find_all(['script', 'style']):
                            el.decompose()
                        item['content_html'] += str(soup)

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) == 0 or paths[0] == 'stories':
        if len(paths) == 0:
            api_url = 'https://www.ussoccer.com/api/stories/10/1'
        else:
            api_url = 'https://www.ussoccer.com/api/stories/category/{}/10/1'.format(quote_plus(paths[1]))
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')
        stories = api_json['stories']
    else:
        api_url = '{}://{}/sitecore/api/layout/render/jss?item={}&sc_lang=en-US&sc_apikey={}'.format(split_url.scheme, split_url.netloc, quote_plus(split_url.path), quote_plus(site_json['sitecoreApiKey']))
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')
        stories = []
        for jss_main in api_json['sitecore']['route']['placeholders']['jss-main']:
            for key, val in jss_main['placeholders'].items():
                if key == 'jss-layout-standard-template':
                    for component in val:
                        if component['componentName'] == 'StoryGrid':
                            stories += component['stories'].copy()

    n = 0
    feed_items = []
    for story in stories:
        story_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, story['link'])
        if save_debug:
            logger.debug('getting content for ' + story_url)
        item = get_content(story_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    if api_json.get('sitecore'):
        feed['title'] = api_json['sitecore']['context']['pageTitle']
    elif len(paths) == 0:
        feed['title'] = 'U.S. Soccer'
    else:
        feed['title'] = api_json['stories'][0]['categoryKey'] + ' | U.S. Soccer'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
