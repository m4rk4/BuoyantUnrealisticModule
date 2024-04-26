import json, re
from datetime import datetime

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(host, path, width=1000):
    return host + 'c_fill,w_{},f_auto,q_auto,g_auto/'.format(width) + path


def add_image(image):
    img_src = resize_image(image['host'], image['path'])
    captions = []
    if image.get('caption'):
        captions.append(image['caption'].encode('iso-8859-1').decode('utf-8'))
    if image.get('credit'):
        captions.append(image['credit'].encode('iso-8859-1').decode('utf-8'))
    return utils.add_image(img_src, ' | '.join(captions))


def get_content(url, args, site_json, save_debug):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    m = re.search(r'window\.__PRELOADED_STATE__ = ({.+})\s+<\/script>', page_html, flags=re.S)
    if not m:
        logger.warning('unable to parse __PRELOADED_STATE__ in ' + url)
        return None

    preloaded_state = json.loads(m.group(1))
    if save_debug:
        utils.write_file(preloaded_state, './debug/debug.json')
    article_json = preloaded_state['template']

    item = {}
    item['id'] = article_json['articleId']
    item['url'] = url
    item['title'] = article_json['title'].encode('iso-8859-1').decode('utf-8')

    if article_json.get('createdAtISO'):
        dt = datetime.fromisoformat(article_json['createdAtISO'])
    elif article_json.get('createdAt') and article_json['createdAt'].endswith('Z'):
        dt = datetime.fromisoformat(article_json['createdAt'])
    else:
        logger.warning('unknown created date for ' + url)
        dt = None
    if dt:
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    if article_json.get('updatedAtISO'):
        dt = datetime.fromisoformat(article_json['updatedAtISO'])
    elif article_json.get('updatedAt') and article_json['updatedAt'].endswith('Z'):
        dt = datetime.fromisoformat(article_json['updatedAt'])
    else:
        logger.warning('unknown updated date for ' + url)
        dt = None
    if dt:
        item['date_modified'] = dt.isoformat()

    authors = []
    for author in article_json['authors']:
        authors.append(author['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = article_json['tags'].copy()

    item['summary'] = article_json['metadataDescription']

    item['content_html'] = ''
    if article_json.get('intro'):
      item['content_html'] += re.sub(r'^<p>(.*?)</p>$', r'<p><em>\1</em></p>', article_json['intro'].strip().encode('iso-8859-1').decode('utf-8'))

    if article_json['cover'].get('image'):
        item['_image'] = article_json['cover']['image']['host'] + article_json['cover']['image']['path']
        item['content_html'] += add_image(article_json['cover']['image'])

    for content in article_json['body']:
        if content['type'] == 'inline-text':
            item['content_html'] += content['html'].encode('iso-8859-1').decode('utf-8')

        elif content['type'] == 'image':
            item['content_html'] += add_image(content['image'])

        elif re.search(r'iframeEmbed|ceros|gfycat|youtube', content['type']):
            m = re.search('src="([^"]+)"', content['html'])
            src = m.group(1)
            if src.startswith('//'):
                src = 'https:' + src
            item['content_html'] += utils.add_embed(src)

        elif content['type'] == 'mmPlayer':
            video_json = utils.get_url_json(
                'https://videos-content.voltaxservices.io/{0}/{0}.json'.format(content['mediaId']))
            if video_json:
                if save_debug:
                    utils.write_file(video_json, './debug/video.json')
                videos = []
                for src in video_json['data'][0]['sources']:
                    if 'mp4' in src['type'] and src.get('height'):
                        videos.append(src)
                video = utils.closest_dict(videos, 'height', 480)
                caption = video_json['data'][0].get('description')
                if not caption:
                    caption = video_json['data'][0].get('title')
                item['content_html'] += utils.add_video(video['file'], video['type'], video_json['data'][0]['image'], caption)
            else:
                logger.warning('unhandled mmPlayer video in ' + url)

        elif content['type'] == 'quote':
            item['content_html'] += utils.add_pullquote(content['text'].encode('iso-8859-1').decode('utf-8'), content['cite'])

        elif content['type'] == 'table':
            item['content_html'] += '<table style="width:100%; border-collapse:collapse;">'
            for i, tr in enumerate(content['data']):
                if i % 2 == 0:
                    item['content_html'] += '<tr style="line-height:2em; border-bottom:1pt solid black; background-color:#ccc;">'
                else:
                    item['content_html'] += '<tr style="line-height:2em; border-bottom:1pt solid black;">'
                for td in tr:
                    item['content_html'] += '<td style="padding:0 8px 0 8px;">' + re.sub(r'^<p>(.*?)</p>$', r'\1', td.strip().encode('iso-8859-1').decode('utf-8')) + '</td>'
                item['content_html'] += '</tr>'
            item['content_html'] += '</table>'

        elif content['type'] == 'divider':
            item['content_html'] += '<hr/>'

        elif content['type'] == 'relatedTopics' or (content['type'] == 'mm-content-embed' and content['embedType'] == 'GroupOfLinks'):
            continue

        else:
            logger.warning('unhandled content type {} in {}'.format(content['type'], url))

    return item


def get_feed(url, args, site_json, save_debug=False):
    # Topic feeds: https://www.theplayerstribune.com/api/properties/theplayertribune/posts?topic=football&limit=10
    return rss.get_feed(url, args, site_json, save_debug, get_content)
