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
        if caption:
            caption = 'Watch: ' + caption
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
                caption = 'Watch: ' + caption + ' | ' + '<a href="{}">Read the article.</a>'.format(media_json['link']['canonical'])
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
    if body['type'] == 'p' or body['type'] == 'b' or body['type'] == 'i' or body['type'] == 'h2' or body['type'] == 'h3':
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
                body_html += utils.add_video(body['content']['props']['mediaItem']['source']['url'], 'application/x-mpegURL', body['content']['props']['mediaItem']['img'], 'Watch: ' + body['content']['props']['mediaItem']['caption'])
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
            else:
                logger.warning('unhandled SocialEmbed network ' + body['content']['props']['network'])
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
    el = soup.find('script', string=re.compile('__abcotv__'), attrs={"type": "text/javascript"})
    if not el:
        logger.debug('unable to find __abcotv__ data in ' + url)
        return None
    abcotv_json = json.loads(el.string[21:-1])
    if save_debug:
        utils.write_file(abcotv_json, './debug/debug.json')
    data_json = abcotv_json['page']['content']['storyData']

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

    item['author'] = {}
    authors = []
    if data_json.get('owner'):
        if data_json['owner'].get('authors'):
            for it in data_json['owner']['authors']:
                authors.append(it['name'])
        elif data_json['owner'].get('byline'):
            authors.append(re.sub(r'^By ', '', data_json['owner']['byline']))
        elif data_json['owner'].get('source'):
            authors.append(data_json['owner']['source'])
        elif data_json['owner'].get('origin'):
            authors.append(data_json['owner']['origin'])
    if authors:
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = site_json['station'].upper()

    item['tags'] = []
    if data_json.get('segments'):
        for key, val in data_json['segments'].items():
            for it in val:
                item['tags'].append(it['displayName'])
    if data_json.get('meta') and data_json['meta'].get('keywords'):
        item['tags'] += data_json['meta']['keywords'].split(', ')

    if data_json.get('description'):
        item['summary'] = data_json['description']

    item['content_html'] = ''
    if data_json.get('featuredMedia'):
        if data_json['featuredMediaType'] == 'video':
            item['_image'] = data_json['featuredMedia']['featuredMedia']['img']
            item['content_html'] += utils.add_video(data_json['featuredMedia']['featuredMedia']['source']['url'], 'application/x-mpegURL', data_json['featuredMedia']['featuredMedia']['img'], 'Watch: ' + data_json['featuredMedia']['featuredMedia']['caption'])
        elif data_json['featuredMediaType'] == 'image':
            item['_image'] = data_json['featuredMedia']['featuredMedia']['src']
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
            item['content_html'] += utils.add_image(data_json['featuredMedia']['featuredMedia']['src'], ' | '.join(captions))
        else:
            logger.warning('unhandled featuredMediaType {} in {}'.format(data_json['featuredMediaType'], item['url']))

    body_json = next((it for it in abcotv_json['page']['content']['articleData']['mainComponents'] if it['name'] == 'Body'), None)
    if not body_json:
        logger.warning('no Body found in mainComponents in ' + item['url'])
        return item

    for body in body_json['props']['body']:
        if isinstance(body, list):
            for b in body:
                item['content_html'] += render_body(b)
        else:
            item['content_html'] += render_body(body)

    if body_json['props']['dateline']:
        item['content_html'] = re.sub(r'<p>', '<p>{} &ndash; '.format(body_json['props']['dateline']), item['content_html'], count=1)

    item['content_html'] = re.sub(r'</ul><ul>', '', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
