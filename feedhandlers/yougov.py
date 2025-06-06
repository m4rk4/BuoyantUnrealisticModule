import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_survey(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    i = paths.index('survey-results') + 2
    api_url = 'https://today.yougov.com/_pubapis/v5/us/surveys/results/' + '/'.join(paths[i:])
    survey_json = utils.get_url_json(api_url)
    if not survey_json:
        return None
    if save_debug:
        utils.write_file(survey_json, './debug/debug.json')

    item = {}
    item['id'] = survey_json['survey_id']
    item['url'] = url
    item['title'] = survey_json['title']

    dt = datetime.fromisoformat(survey_json['published_at'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": "YouGov survey"}

    item['tags'] = []
    if survey_json.get('cms_categories'):
        item['tags'] = survey_json['cms_categories'].copy()
    if survey_json.get('primary_category') and survey_json['primary_category'] not in item['tags']:
        item['tags'].append(survey_json['primary_category'])
    if survey_json.get('related_entities'):
        for it in survey_json['related_entities']:
            if it['name'] not in item['tags']:
                item['tags'].append(it['name'])

    item['content_html'] = '<h3>' + survey_json['results'][0]['title'] + '</h3>'
    for data in survey_json['results'][0]['data']:
        item['content_html'] += utils.add_bar(data['label'], data['value'], 100, True)
    item['content_html'] += '<div>Conducted {}. YouGov surveyed {} US adults.</div>'.format(utils.format_display_date(dt, date_only=True), survey_json['total'])
    item['content_html'] += '<div>&nbsp;</div>'

    # Tables
    for result in survey_json['results'][1:]:
        item['content_html'] += '<h3>' + result['title'] + '</h3><table style="table-layout:fixed; border-collapse:collapse;"><tr style="line-height:2em; border-bottom:1pt solid black;"><th></th>'
        w = int(100 / (len(result['labels']) + 2))
        item['content_html'] += '<th style="width:{}%;">{}</th>'.format(w, survey_json['results'][0]['label'])
        for it in result['labels']:
            item['content_html'] += '<th style="width:{}%">{}</th>'.format(w, it)
        item['content_html'] += '</tr>'
        for i, data in enumerate(result['data']):
            if i % 2 == 0:
                item['content_html'] += '<tr style="line-height:2em; border-bottom:1pt solid black; background-color:#ccc;">'
            else:
                item['content_html'] += '<tr style="line-height:2em; border-bottom:1pt solid black;">'
            item['content_html'] += '<td>{}</td>'.format(data['label'])
            item['content_html'] += '<td style="text-align:center;">{}%</td>'.format(survey_json['results'][0]['data'][i]['value'])
            for it in data['values']:
                item['content_html'] += '<td style="text-align:center;">{}</td>'.format(it)
            item['content_html'] += '</tr>'
        item['content_html'] += '</table><div>&nbsp;</div>'
    return item


def get_content(url, args, site_json, save_debug=False):
    if '/survey-results/' in url:
        return get_survey(url, args, site_json, save_debug)

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    m = re.search(r'^(\d+)', paths[-1])
    if not m:
        logger.warning('unhandled url ' + url)
        return None
    api_url = 'https://api-test.yougov.com/public-content/articles/content/{}?cms_instance=editorial'.format(m.group(1))
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')
    article_json = api_json['data']

    item = {}
    item['id'] = article_json['id']
    item['url'] = url
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['published_at'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    authors = []
    for it in article_json['authors']:
        authors.append(it['full_name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json.get('tags'):
        item['tags'] = []
        for it in article_json['tags']:
            item['tags'].append(it['name'])

    if article_json.get('search_description'):
        item['summary'] = article_json['search_description']
    elif article_json['seo'].get('description'):
        item['summary'] = article_json['seo']['description']

    item['content_html'] = ''
    if article_json.get('image'):
        item['_image'] = article_json['image']['full_url']
        item['content_html'] += utils.add_image(item['_image'])

    for content in article_json['content']:
        if content['type'] == 'description':
            if content['content']['text'].startswith('<p'):
                item['content_html'] += content['content']['text']
            else:
                logger.warning('unhandled description content in ' + item['url'])
        elif content['type'] == 'image':
            # TODO: caption?
            item['content_html'] += utils.add_image(content['content']['image']['url'])
        elif content['type'] == 'embed':
            if content['content'].get('url'):
                item['content_html'] += utils.add_embed(content['content']['url'])
            else:
                logger.warning('unhandled embed content in ' + item['url'])
        else:
            logger.warning('unhandled content type {} in {}'.format(content['type'], item['url']))

    return item


def get_feed(url, args, site_json, save_debug=False):
    if '/feeds/' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    feed = None
    if '/topics/' in args['url']:
        split_url = urlsplit(args['url'])
        paths = list(filter(None, split_url.path.split('/')))
        api_url = '{}://{}/_pubapis/v5/us/search/content/articles/?category={}&limit=10'.format(split_url.scheme, split_url.netloc, paths[1])
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')

        n = 0
        feed_items = []
        for article in api_json['data']:
            url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article['url'])
            if save_debug:
                logger.debug('getting content for ' + url)
            item = get_content(url, args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break
        feed = utils.init_jsonfeed(args)
        feed['title'] = 'YouGov | ' + paths[1].title()
        feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)

    return feed