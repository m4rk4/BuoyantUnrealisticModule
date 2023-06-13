import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

import config, utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    path += '.json'
    if split_url.query:
        path += '?' + split_url.query
    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        #utils.write_file(page_html, './debug/debug.html')
        m = re.search(r'"buildId":"([^"]+)"', page_html)
        if m and m.group(1) != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = m.group(1)
            utils.update_sites(url, site_json)
            next_url = '{}://{}/_next/data/{}/{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
            next_data = utils.get_url_json(next_url)
            if not next_data:
                return None
    return next_data


def get_content(url, args, site_json, save_debug=False):
    # https://tallysight.com/new/widget/tile/nascar/org:the-athletic/event:2023-toyota-save-mart-350/topic:outright-betting/variant:1/outcomes:c950,c951,c958?id=1255fe34-b62f-48f0-9b7d-a32b248c03c6
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    split_url = urlsplit(url)
    query = parse_qs(split_url.query)
    if not (re.search(r'/event:', split_url.path) and re.search(r'/topic:', split_url.path)):
        logger.warning('unhandled url ' + url)
        return None

    options = next_data['pageProps']['options']
    topic = next((it for it in next_data['pageProps']['topics'] if it['slug'] == options['topic']), None)
    if not topic:
        logger.warning('unknown topic in ' + url)
        return None
    if len(topic['markets']) > 1:
        logger.warning('unknown market in ' + url)
        return None
    market = topic['markets'][0]

    item = {}
    item['id'] = topic['_id']
    item['url'] = url
    item['title'] = '{}: {}'.format(topic['event']['name'], topic['name'])

    item['content_html'] = '<table style="min-width:50%; max-width:100%; margin-left:auto; margin-right:auto; padding:8px; border:1px solid black;"><tr><td colspan="2" style="text-align:center; font-weight:bold;">{} &bull; {}</td></tr><tr><td colspan="2" style="font-size:1.2em; font-weight:bold;"><a href="{}">{}</a></td></tr>'.format(topic['event']['sport']['name'], topic['event']['name'], item['url'], topic['name'])
    if options.get('outcomes'):
        for oc in options['outcomes']:
            outcome = next((it for it in market['outcomes'] if it['_id'].endswith(oc)), None)
            if outcome['sportsbooks'][0]['odds'] >= 0:
                odds = '+{}'.format(outcome['sportsbooks'][0]['odds'])
            else:
                odds = str(outcome['sportsbooks'][0]['odds'])
            item['content_html'] += '<tr><td>{}</td><td style="text-align:center;">{}</td></tr>'.format(outcome['entity']['name'], odds)
            dt = datetime.fromisoformat(outcome['sportsbooks'][0]['timestamp'].replace('Z', '+00:00'))
            if item.get('_timestamp'):
                if dt.timestamp() > item['_timestamp']:
                    item['_timestamp'] = dt.timestamp()
            else:
                item['_timestamp'] = dt.timestamp()
    else:
        for i, outcome in enumerate(market['outcomes']):
            if outcome['sportsbooks'][0]['odds'] >= 0:
                odds = '+{}'.format(outcome['sportsbooks'][0]['odds'])
            else:
                odds = str(outcome['sportsbooks'][0]['odds'])
            item['content_html'] += '<tr><td>{}</td><td style="text-align:center;">{}</td></tr>'.format(outcome['entity']['name'], odds)
            dt = datetime.fromisoformat(outcome['sportsbooks'][0]['timestamp'].replace('Z', '+00:00'))
            if item.get('_timestamp'):
                if dt.timestamp() > item['_timestamp']:
                    item['_timestamp'] = dt.timestamp()
            else:
                item['_timestamp'] = dt.timestamp()
            if i == 4:
                break
    dt = datetime.fromtimestamp(item['_timestamp']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_display_date'] = utils.format_display_date(dt)
    item['content_html'] += '<tr><td colspan="2" style="text-align:center;"><small>Odds updated {}</small></td></tr></table>'.format(item['_display_date'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return None
