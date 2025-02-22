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
    if 'article' not in paths:
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

    item['author'] = {
        "name": "Ground News AI"
    }

    item['tags'] = []
    if event_json.get('interests'):
        item['tags'] += [x['name'] for x in event_json['interests']]
    
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

    if event_json.get('blindspotData') and event_json['blindspotData'].get('coverageProfileStatement'):
        item['content_html'] += '<p style="font-weight:bold; font-style:italic;">' + event_json['blindspotData']['coverageProfileStatement']
        if event_json['blindspotData'].get('coverageProfileSubStatement'):
            item['content_html'] += ' &ndash; ' + event_json['blindspotData']['coverageProfileSubStatement']
        item['content_html'] += '</p>'

    item['content_html'] += '<div style="font-size:1.1em; font-weight:bold">Coverage Details:</div><table style="margin-left:40px;">'
    item['content_html'] += '<tr><td>Total News Sources</td><td style="padding:8px;"><b>{}</b></td></tr>'.format(event_json['sourceCount'])
    item['content_html'] += '<tr><td>Leaning Left</td><td style="padding:8px;"><b>{:.1f}%</b></td></tr>'.format(event_json['leftSrcPercent'] * 100)
    item['content_html'] += '<tr><td>Leaning Right</td><td style="padding:8px;"><b>{:.1f}%</b></td></tr>'.format(event_json['rightSrcPercent'] * 100)
    item['content_html'] += '<tr><td>Center</td><td style="padding:8px;"><b>{:.1f}%</b></td></tr>'.format(event_json['cntrSrcPercent'] * 100)
    item['content_html'] += '</table>'

    if event_json['chatGptSummaries'].get('analysis'):
        item['content_html'] += '<div>&nbsp;</div><div style="font-size:1.1em; font-weight:bold;">Bias Insights:</div><ul>'
        for li in event_json['chatGptSummaries']['analysis'].split('\n'):
            if li.strip():
                item['content_html'] += '<li>' + re.sub(r'^\d\.\s*', '', li.strip()) + '</li>'
        item['content_html'] += '</ul>'

    if event_json.get('chatGptSummaries'):
        item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:1em; align-items:flex-start;">'
        for it in ['left', 'right', 'center']:
            if event_json['chatGptSummaries'].get(it):
                item['content_html'] += '<div style="flex:1; min-width:256px; max-width:800px; padding:8px; border:1px solid black; border-radius:10px;"><div style="font-size:1.1em; font-weight:bold; text-align:center;">{}</div><ul>'.format(it.title())
                for li in event_json['chatGptSummaries'][it].split('\n'):
                    if li.strip():
                        item['content_html'] += '<li>' + re.sub(r'^\d\.\s*', '', li.strip()) + '</li>'
                item['content_html'] += '</ul></div>'
        item['content_html'] += '</div>'

    qa_json = utils.get_url_json('https://web-api-cdn.ground.news/api/public/search/startingQsForStoryGuide/' + event_json['id'])
    if qa_json and qa_json.get('questionAnswerPairs'):
        item['content_html'] += '<h2>Q&A</h2><dl>'
        for qa in qa_json['questionAnswerPairs']:
            item['content_html'] += '<dt><b>{}</b></dt><dd style="padding-bottom:1em;">{}</dd>'.format(qa['question'], qa['answer'])
        item['content_html'] += '</dl>'

    item['content_html'] += '<h2>Articles</h2>'
    for source in event_json['firstTenSources']:
        logger.debug('getting embed content for ' + source['url'])
        item['content_html'] += '<div><b>{}</b> <small>(bias: {}, factuality: {})</small></div><div>&nbsp;</div>'.format(source['sourceInfo']['name'], source['sourceInfo']['bias'], source['sourceInfo']['factuality'])
        embed_item = utils.get_content(source['url'], {"embed": True})
        if embed_item:
            item['content_html'] += embed_item['content_html'] + '<div>&nbsp;</div>'
        else:
            item['content_html'] += '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;">'
            item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(urlsplit(source['url']).netloc, source['url'], source['title'])
            if source.get('description'):
                item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(source['description'])
            item['content_html'] += '</div></div><div>&nbsp;</div>'
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if 'interest' not in paths:
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
