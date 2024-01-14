import pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if '/article/' not in split_url.path:
        logger.warning('unhandled url ' + url)
        return None
    api_json = utils.get_url_json('https://web-api-cdn.ground.news/api/public/event/' + paths[-1])
    if not api_json:
        return None
    event_json = api_json['event']
    if save_debug:
        utils.write_file(event_json, './debug/debug.json')

    item = {}
    item['id'] = event_json['id']
    item['url'] = event_json['shareUrl']
    item['title'] = event_json['title']

    dt = datetime.fromisoformat(event_json['start'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(event_json['lastModified'])
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": "Ground News AI"}

    item['content_html'] = ''

    if event_json.get('latestMedia'):
        image = event_json['latestMedia']
    elif event_json.get('fallbackMedia'):
        image = event_json['fallbackMedia']
    else:
        image = None
    if image:
        item['_image'] = image['url']
        captions = []
        if image.get('caption'):
            captions.append(image['caption'].strip())
        if image.get('attributionName'):
            captions.append(image['attributionName'].strip())
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    if event_json.get('summary'):
        item['summary'] = event_json['summary']
    elif event_json.get('description'):
        item['summary'] = event_json['description']

    item['content_html'] += '<h2>Summary</h2>'
    item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:1em; align-items:flex-start;">'
    for it in ['left', 'right', 'center']:
        if event_json['chatGptSummaries'].get(it):
            item['content_html'] += '<div style="flex:1; min-width:256px; max-width:800px; padding:8px; border:1px solid black; border-radius:10px;"><div style="font-size:1.1em; font-weight:bold; text-align:center;">{}</div><ul>'.format(it.title())
            for li in event_json['chatGptSummaries'][it].split('\n'):
                if li.strip():
                    item['content_html'] += '<li>' + re.sub(r'^\d\.\s*', '', li.strip()).capitalize() + '</li>'
            item['content_html'] += '</ul></div>'
    item['content_html'] += '</div><div>&nbsp;</div><div style="font-size:1.1em; font-weight:bold;">Bias Insights:</div><ul>'
    for li in event_json['chatGptSummaries']['analysis'].split('\n'):
        if li.strip():
            item['content_html'] += '<li>' + re.sub(r'^\d\.\s*', '', li.strip()).capitalize() + '</li>'
    item['content_html'] += '</ul>'

    item['content_html'] += '<div style="font-size:1.1em; font-weight:bold">Coverage Details:</div><table>'
    item['content_html'] += '<tr><td>Total News Sources</td><td style="padding:8px;"><b>{}</b></td></tr>'.format(len(event_json['sources']))
    item['content_html'] += '<tr><td>Leaning Left</td><td style="padding:8px;"><b>{} ({}%)</b></td></tr>'.format(event_json['leftSrcCount'], event_json['blindspotData']['leftPercent'])
    item['content_html'] += '<tr><td>Leaning Right</td><td style="padding:8px;"><b>{} ({}%)</b></td></tr>'.format(event_json['rightSrcCount'], event_json['blindspotData']['rightPercent'])
    item['content_html'] += '<tr><td>Center</td><td style="padding:8px;"><b>{} ({}%)</b></td></tr>'.format(event_json['cntrSrcCount'], event_json['blindspotData']['centerPercent'])

    # item['content_html'] += '<tr><td>Bias Distribution</td><td style="padding:8px;"><b>{}</b></td></tr>'.format(bias['center'])
    item['content_html'] += '</table>'

    item['content_html'] += '<h2>Articles</h2>'
    for source in event_json['firstTenSources']:
        item['content_html'] += '<div><b>{}</b> <small>(bias: {}, factuality: {})</small></div>'.format(source['sourceInfo']['name'], source['sourceInfo']['bias'], source['sourceInfo']['factuality'])
        item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(source['url'], source['title'])
        if source.get('description'):
            item['content_html'] += '<div>' + source['description'] + '</div>'
        item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if '/interest/' not in split_url.path:
        logger.warning('unhandled url ' + url)
        return None

    interest_json = utils.get_url_json('https://web-api-cdn.ground.news/api/public' + split_url.path)
    if not interest_json:
        return None

    events_json = utils.get_url_json('https://web-api-cdn.ground.news/api/public/interest/{}/events?sort=time'.format(interest_json['interest']['id']))
    if not events_json:
        return None

    for event_id in events_json['eventIds']:
        event_json = utils.get_url_json('https://web-api-cdn.ground.news/api/public/event/' + event_id)
        if event_json:
            print(event_json['event']['title'])

    return None
