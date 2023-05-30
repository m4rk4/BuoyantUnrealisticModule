import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def format_content(content, records, site_json, url_only):
    print(content['__id'])
    content_html = ''
    if content['__typename'] == 'Text':
        content_html += content['content']
    elif content['__typename'] == 'Paragraph':
        content_html += '<p>'
        for ref in content['contents']['__refs']:
            content_html += format_content(records[ref], records, site_json, url_only)
        content_html += '</p>'
    elif content['__typename'] == 'HyperLink':
        content_html += '<a href="{}">{}</a>'.format(content['url'], content['label'])
    elif content['__typename'] == 'Embed':
        content_html += utils.add_embed(content['url'])
    elif content['__typename'] == 'Picture':
        # TODO: resize
        content_html += content['url']
    elif content['__typename'] == 'Video':
        link = format_content(records[content['link']['__ref']], records, site_json, url_only)
        if url_only == True:
            content_html += link
        else:
            poster = format_content(records[content['picture']['__ref']], records, site_json, url_only)
            if len(content['allowedCountries']) == 0 or config.country in content['allowedCountries']:
                m = re.search(r'_(vid\d+)', link)
                if m:
                    token_json = utils.get_url_json('https://eu3-prod-direct.eurosport.com/token?realm=eurosport')
                    if token_json:
                        headers = config.default_headers.copy()
                        headers['authorization'] = 'Bearer {}'.format(token_json['data']['attributes']['token'])
                        headers['x-disco-client'] = 'WEB:UNKNOWN:escom:0.250.0'
                        headers['cookie'] = 'eurosport_country_code=US; eurosport_is_eu=0; eurosport_user={{%22isRegistered%22:false%2C%22isSubscribed%22:false}}; st={}'.format(site_json['sonicToken'])
                        video_json = utils.get_url_json('https://eu3-prod-direct.eurosport.com/playback/v2/videoPlaybackInfo/sourceSystemId/eurosport-{}?usePreAuth=true'.format(m.group(1)), headers=headers)
                        if video_json:
                            video_src = video_json['data']['attributes']['streaming']['hls']['url']
                            content_html += utils.add_video(video_src, 'application/x-mpegURL', poster, content['title'])
            else:
                caption = '⚠ <a href="{}">This video is unavailable in your country.</a> {}'.format(link, content['title'])
                content_html += utils.add_image(poster, caption, link=link)
    elif content['__typename'] == 'Article' and url_only == True:
        #content_html += '<a href="{}">{}</a>'.format(format_content(records[content['link']['__ref']], records, site_json, url_only), content['title'])
        content_html += format_content(records[content['link']['__ref']], records, site_json, url_only)
    elif re.search(r'H\d', content['__typename']):
        content_html += '<{}>'.format(content['__typename'].lower())
        for ref in content['contents']['__refs']:
            content_html += format_content(records[ref], records, site_json, url_only)
        content_html += '</{}>'.format(content['__typename'].lower())
    elif content['__typename'] == 'List':
        content_html += '<ul>'
        for ref in content['listItems']['__refs']:
            content_html += format_content(records[ref], records, site_json, url_only)
        content_html += '</ul>'
    elif content['__typename'] == 'ListItem':
        for ref in content['contents']['__refs']:
            content_html += '<li>' + format_content(records[ref], records, site_json, url_only) + '</li>'
    elif content['__typename'] == 'HyperLinkInternal':
        link = format_content(records[content['content']['__ref']], records, site_json, True)
        content_html += '<a href="{}">{}</a>'.format(link, content['label'])
    elif content['__typename'] == 'Link':
        content_html += content['url']
    elif content['__typename'] == 'InternalContent':
        content_html += format_content(records[content['content']['__ref']], records, site_json, False)
    elif content['__typename'] == 'BreakLine':
        if content['type'] == 'NEWLINE':
            content_html += '<br/>'
        else:
            logger.warning('unhandled BreakLine type ' + content['type'])
    else:
        logger.warning('unhandled content type ' + content['__typename'])
    return content_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + url)
        return None

    next_data = json.loads(el.string)
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    records = next_data['props']['pageProps']['serverQueryRecords']
    m = re.search(r'\d+$', paths[-2])
    if not m:
        logger.warning('unknown article id in ' + url)
        return None
    article_id = int(m.group(0))
    article_json = None
    for key, val in records.items():
        if val.get('databaseId') and val['databaseId'] == article_id:
            article_json = val
            break
    if not article_json:
        logger.warning('unable to determine article in ' + url)
        return None

    item = {}
    item['id'] = article_json['__id']
    item['url'] = records[article_json['link']['__ref']]['url']
    item['title'] = article_json['seoTitle']

    dt = datetime.fromisoformat(article_json['publicationTime'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['lastUpdatedTime'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    authors = []
    for ref in article_json['authors']['__refs']:
        it = records[ref]
        authors.append('{} {}'.format(it['firstName'], it['lastName']))
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json.get('context'):
        item['tags'] = []
        for ref in article_json['context']['__refs']:
            it = records[ref]
            item['tags'].append(it['name'])

    item['content_html'] = ''
    if article_json.get('teaser'):
        item['summary'] = article_json['teaser']
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['teaser'])

    if article_json.get('illustration'):
        content = records[article_json['illustration']['__ref']]
        item['content_html'] += format_content(content, records, site_json, False)

    if article_json.get('picture'):
        item['_image'] = records[article_json['picture']['__ref']]['url']

    body = records[article_json['graphQLBody']['__ref']]
    for ref in body['contents']['__refs']:
        content = records[ref]
        item['content_html'] += format_content(content, records, site_json, False)

    return item