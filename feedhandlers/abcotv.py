import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import unquote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_media(media_json, media_id, site_json):
    if not media_json and media_id:
        api_url = 'https://api.abcotvs.com/v2/content?station={0}&id={1}&key=otv.web.{0}.prism-story'.format(site_json['station'], media_id)
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        #utils.write_file(api_json, './debug/media.json')
        media_json = api_json['data']
    if media_json.get('caption'):
        caption = media_json['caption']
    elif media_json.get('description'):
        caption = media_json['description']
    elif media_json.get('title'):
        caption = media_json['title']
    else:
        caption = ''
    if media_json['type'] == 'videoClip' or media_json['type'] == 'Live_Channel':
        if media_json.get('mp4'):
            return utils.add_video(media_json['mp4'], 'video/mp4', media_json['image']['source'], caption)
        elif media_json.get('m3u8'):
            return utils.add_video(media_json['m3u8'], 'application/x-mpegURL', media_json['image']['source'], caption)
        else:
            logger.warning('unsupported videoClip')
    elif media_json['type'] == 'image':
        return utils.add_image(media_json['source'], caption)
    elif media_json['type'] == 'post':
        if media_json.get('featuredMedia') and media_json['featuredMedia'].get('video'):
            if caption:
                caption += ' | '
            caption += '<a href="{}">Read the article.</a>'.format(media_json['link']['canonical'])
            if media_json['featuredMedia']['video'].get('mp4'):
                return utils.add_video(media_json['featuredMedia']['video']['mp4'], 'video/mp4', media_json['image']['source'], caption)
            elif media_json['featuredMedia']['video'].get('m3u8'):
                return utils.add_video(media_json['featuredMedia']['video']['m3u8'], 'application/x-mpegURL', media_json['image']['source'], caption)
        elif media_json.get('featuredMedia') and media_json['featuredMedia'].get('image'):
            return utils.add_image(media_json['featuredMedia']['image']['source'], caption, link=media_json['link']['canonical'])
    logger.warning('unhandled media type ' + media_json['type'])
    return ''


def get_content_from_api(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    api_url = 'https://api.abcotvs.com/v2/content?station={0}&id={1}&key=otv.web.{0}.prism-story'.format(site_json['station'], paths[-1])
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')
    data_json = api_json['data']

    item = {}
    item['id'] = data_json['id']
    item['url'] = data_json['link']['canonical']
    item['title'] = data_json['title']

    dt = datetime.fromtimestamp(data_json['firstPublished']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromtimestamp(data_json['dateModified']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    if data_json['owner'].get('authors'):
        for it in data_json['owner']['authors']:
            authors.append(it['name'])
    else:
        authors.append(data_json['owner']['source'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if data_json.get('segments'):
        for key, val in data_json['segments'].items():
            for it in val:
                item['tags'].append(it['displayName'])
    if data_json.get('meta') and data_json['meta'].get('keywords'):
        item['tags'] += data_json['meta']['keywords'].split(', ')

    item['content_html'] = ''
    if data_json.get('featuredMedia'):
        if data_json['featuredMedia'].get('video'):
            item['_image'] = data_json['featuredMedia']['video']['image']['source']
            item['content_html'] += add_media(data_json['featuredMedia']['video'], data_json['featuredMedia']['video']['id'], site_json)
        if data_json['featuredMedia'].get('live'):
            item['_image'] = data_json['featuredMedia']['live']['image']['source']
            item['content_html'] += add_media(data_json['featuredMedia']['live'], data_json['featuredMedia']['live']['id'], site_json)
        elif data_json['featuredMedia'].get('image'):
            item['_image'] = data_json['featuredMedia']['image']['source']
            item['content_html'] += add_media(data_json['featuredMedia']['image'], data_json['featuredMedia']['image']['id'], site_json)

    if data_json.get('description'):
        item['summary'] = data_json['description']

    content_html = '<p>' + data_json['bodyText'].replace('[Ads /]', '') + '</p>'
    i = 0
    while re.search(r'\[br /\]', content_html):
        if i % 2 == 0:
            content_html = re.sub(r'\[br /\]', '</p>', content_html, count=1)
        else:
            content_html = re.sub(r'\[br /\]', '<p>', content_html, count=1)
        i += 1

    content_html = re.sub(r'\[(/)?(b|i)\]', r'<\1\2>', content_html)
    content_html = re.sub(r'\[url HREF="([^"]+)"[^\]]+\]', r'<a href="\1">', content_html.replace('[/url]', '</a>'))
    content_html = re.sub(r'\[(/?)h(\d)\]', r'<\1h\2>', content_html)
    def sub_media(matchobj):
        nonlocal site_json
        if matchobj.group(1) == 'media':
            return add_media(None, matchobj.group(2).strip(), site_json)
        elif matchobj.group(1) == 'twitter':
            return utils.add_embed(utils.get_twitter_url(matchobj.group(2).strip()))
        elif matchobj.group(1) == 'newsletter':
            return ''
    content_html = re.sub(r'\[(media|newsletter|twitter) ID="([^"]+)"[^\]]+\]', sub_media, content_html)

    item['content_html'] += content_html
    return item


def render_body(body):
    if isinstance(body, str):
        return body
    body_html = ''
    if body['type'] == 'p' or body['type'] == 'b' or body['type'] == 'i' or body['type'] == 'h2' or body['type'] == 'h3' or body['type'] == 'strong':
        body_html += '<{}>'.format(body['type'])
        for content in body['content']:
            body_html += render_body(content)
        body_html += '</{}>'.format(body['type'])
    elif body['type'] == 'a':
        body_html += '<a href="{}">'.format(body['attrs']['href'])
        for content in body['content']:
            body_html += render_body(content)
        body_html += '</a>'
    elif body['type'] == 'li':
        body_html += '<ul><li>'
        for content in body['content']:
            body_html += render_body(content)
        body_html += '</li></ul>'
    elif body['type'] == 'inline':
        if body['content']['name'] == 'Ad' or body['content']['name'] == 'Chimney' or body['content']['name'] == 'NewsletterForm':
            pass
        elif body['content']['name'] == 'InlineVideo':
            if body['content']['props']['mediaItem']['streamType'] == 'onDemand':
                body_html += utils.add_video(body['content']['props']['mediaItem']['source']['url'], 'application/x-mpegURL', body['content']['props']['mediaItem']['img'], body['content']['props']['mediaItem']['caption'])
            else:
                logger.warning('unhandled InlineVideo type ' + body['content']['props']['mediaItem']['streamType'])
        elif body['content']['name'] == 'Image':
            captions = []
            if body['content']['props'].get('caption'):
                if body['content']['props']['caption'].get('text'):
                    captions.append(body['content']['props']['caption']['text'])
                if body['content']['props']['caption'].get('credit'):
                    captions.append(body['content']['props']['caption']['credit'])
            body_html += utils.add_image(body['content']['props']['image']['src'], ' | '.join(captions))
        elif body['content']['name'] == 'SocialEmbed':
            if body['content']['props']['network'] == 'twitter':
                soup = BeautifulSoup(unquote_plus(body['content']['props']['markup']), 'html.parser')
                links = soup.find_all('a')
                body_html += utils.add_embed(links[-1]['href'])
            elif body['content']['props']['network'] == 'story-promo-external':
                # https://abc7news.com/sports/no-better-feeling-how-draymond-green-klay-thompson-rescued-a-wa/13190040/
                soup = BeautifulSoup(unquote_plus(body['content']['props']['markup']), 'html.parser')
                links = soup.find_all('a')
                if re.search(r'https://www\.espn\.com/video/clip', links[0]['href']):
                    body_html += utils.add_embed(links[0]['href'])
                logger.warning('unhandled SocialEmbed story-promo-external')
            else:
                logger.warning('unhandled SocialEmbed network ' + body['content']['props']['network'])
        elif body['content']['name'] == 'SectionHeader':
            body_html += unquote_plus(body['content']['props']['innerHtml'])
        else:
            logger.warning('unhandled inline content ' + body['content']['name'])
    else:
        logger.warning('unhandled body type ' + body['type'])
    return body_html


def get_content(url, args, site_json, save_debug=False):
    # https://abcotvs.com/index.html
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile(r'window\[\'__abcotv__\'\]='))
    if not el:
        logger.debug('unable to find __abcotv__ data in ' + url)
        return None
    # abcotv_json = json.loads(el.string[21:-1])
    utils.write_file(el.string, './debug/debug.txt')
    i = el.string.find('window[\'__abcotv__\']=') + len('window[\'__abcotv__\']=')
    j = el.string.rfind('}') + 1
    abcotv_json = json.loads(el.string[i:j])
    if save_debug:
        utils.write_file(abcotv_json, './debug/debug.json')
    data_json = abcotv_json['page']['content']['storyData']

    item = {}
    item['id'] = data_json['id']
    item['url'] = data_json['locator']
    item['title'] = data_json['headline']

    dt = datetime.fromisoformat(data_json['date'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if data_json.get('modified'):
        dt = datetime.fromisoformat(data_json['modified'])
        item['date_modified'] = dt.isoformat()

    if data_json.get('contributors'):
        item['authors'] = data_json['contributors'].copy()
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    elif data_json.get('origin'):
        item['author'] = {"name": data_json['origin']['name']}
        item['authors'] = []
        item['authors'].append(item['author'])

    item['tags'] = []
    if data_json.get('tags'):
        item['tags'] = [x['name'].lower() for x in data_json['tags'] if x.get('name')]
    if data_json.get('segments'):
        item['tags'] += [x['displayName'].lower() for x in data_json['segments'] if x.get('displayName') and x['displayName'].lower() not in item['tags']]
    if data_json.get('keywords'):
        item['tags'] += [x.lower() for x in data_json['keywords'] if x.lower() not in item['tags'] and not x.isnumeric()]

    if data_json.get('description'):
        item['summary'] = data_json['description']
    elif data_json.get('metaDescription'):
        item['summary'] = data_json['metaDescription']

    item['content_html'] = ''
    if data_json.get('leadInText'):
        item['content_html'] += '<p><em>' + data_json['leadInText'] + '</em></p>'

    if data_json.get('featuredMedia'):
        if data_json['featuredMediaType'] == 'video':
            item['image'] = data_json['featuredMedia']['featuredMedia']['img']
            item['content_html'] += utils.add_video(data_json['featuredMedia']['featuredMedia']['source']['url'], 'application/x-mpegURL', item['image'], data_json['featuredMedia']['featuredMedia']['caption'])
        elif data_json['featuredMediaType'] == 'image' or (data_json['featuredMediaType'] == 'external' and data_json['featuredMedia']['featuredMedia'].get('img')):
            if data_json['featuredMedia']['featuredMedia'].get('src'):
                item['image'] = data_json['featuredMedia']['featuredMedia']['src']
            elif data_json['featuredMedia']['featuredMedia'].get('img'):
                item['image'] = data_json['featuredMedia']['featuredMedia']['img']
            captions = []
            if data_json['featuredMedia']['featuredMedia'].get('caption'):
                captions.append(data_json['featuredMedia']['featuredMedia']['caption'])
            if data_json['featuredMedia']['featuredMedia'].get('owner'):
                if data_json['featuredMedia']['featuredMedia']['owner'].get('credit'):
                    captions.append(data_json['featuredMedia']['featuredMedia']['owner']['credit'])
                elif data_json['featuredMedia']['featuredMedia']['owner'].get('source'):
                    captions.append(data_json['featuredMedia']['featuredMedia']['owner']['source'])
                elif data_json['featuredMedia']['featuredMedia']['owner'].get('origin'):
                    captions.append(data_json['featuredMedia']['featuredMedia']['owner']['origin'])
            item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))
        else:
            logger.warning('unhandled featuredMediaType {} in {}'.format(data_json['featuredMediaType'], item['url']))

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    body_json = next((it for it in abcotv_json['page']['content']['articleData']['mainComponents'] if it['name'] == 'Body'), None)
    if not body_json:
        logger.warning('no Body found in mainComponents in ' + item['url'])
        return item

    body_html = ''
    for body in body_json['props']['body']:
        if isinstance(body, list):
            for b in body:
                body_html += render_body(b)
        else:
            body_html += render_body(body)

    if body_json['props']['dateline']:
        body_html = re.sub(r'<p>', '<p>{} &ndash; '.format(body_json['props']['dateline']), body_html, count=1)
    body_html = re.sub(r'</ul><ul>', '', body_html)

    item['content_html'] += body_html
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
