import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_oovvuu_video(video_id):
    video_json = utils.get_url_json('https://playback.oovvuu.media/embed/d3d3LnRoZXN0YXIuY29t/{}'.format(video_id))
    if not video_json:
        return ''
    utils.write_file(video_json, './debug/video.json')
    #"data-key": "BCpkADawqM02UpPUkzc8xH5Bd3-cUq0R9yd9J44SrfoXNajUlAnL6l--3PUnKFaoBa2cWhTYVjtnL20g-dK2t5i2TPJSnXqImIvT_aNrKa4oZN4_ZI3PVVR4S1A-hxd2XgABF1ZBQI-7bQvzHnInuey3CFEvla5Awnx-tf5_iq_IS9XXNLt1w00d3PLm8cnKcX4Qmi2yRSQZimMQyGUhbXywrF6YTC5WaBPG5jqpO-_Ht4LrOZoVlKLkPRhqGh1Pq0Bmn4ucWl1J_hHRVIPBY9Pwd1b7IuenAaGcCg",
    poster = utils.clean_url(video_json['videos'][0]['video']['thumbnail']) + '?ixlib=js-2.3.2&w=1080&fit=crop&crop=entropy'
    video_args = {
        "embed": True,
        "data-account": video_json['videos'][0]['brightcoveAccountId'],
        "data-video-id": video_json['videos'][0]['brightcoveVideoId'],
        "poster": poster,
        "title": 'Watch: ' + video_json['videos'][0]['video']['title']
    }
    return utils.add_embed(video_json['playerScript'], video_args)


def add_image(image, width=1080):
    # item['_image'] = '{}://{}'.format(split_url.scheme, split_url.netloc, article_json['mainart']['url'])
    img = utils.closest_dict(image['renditions'], 'width', width)
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('credit'):
        captions.append(image['credit'])
    if image.get('source'):
        captions.append(image['source'])
    return utils.add_image(img['url'], ' | '.join(captions))


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile(r'__PRELOADED_STATE__'))
    if not el:
        logger.warning('unable to parse __PRELOADED_STATE__ data in ' + url)
        return None

    i = el.string.find('{')
    j = el.string.rfind('}') + 1
    article_json = json.loads(el.string[i:j])
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['storyuuid']
    item['url'] = article_json['urlMetatag']
    item['title'] = article_json['headline']

    dt = datetime.fromtimestamp(article_json['publishedepoch']/1000).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('lastmodifiedepoch'):
        dt = datetime.fromtimestamp(article_json['lastmodifiedepoch']/1000).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

    authors = []
    for it in article_json['authors']:
        if it.get('author'):
            if it.get('credit') and not it.get('tag'):
                # Usually a non-staff reporter
                authors.append('{} ({})'.format(it['author'], it['credit']))
            else:
                authors.append(it['author'])
        else:
            if it.get('credit'):
                authors.append(it['credit'])
            else:
                authors.append(split_url.netloc)
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = [it.strip() for it in article_json['seoKeywords'].split(',')]

    if article_json.get('mainart') and article_json['mainart'].get('type'):
        if article_json['mainart']['type'] == 'image':
            image = utils.closest_dict(article_json['mainart']['renditions'], 'width', 1080)
            item['_image'] = image['url']
        elif article_json['mainart']['type'] == 'slideshow':
            image = utils.closest_dict(article_json['mainart']['images'][0]['renditions'], 'width', 1080)
            item['_image'] = image['url']
        else:
            logger.warning('unhandled mainart type {} in {}'.format(article_json['mainart']['type'], item['url']))

    item['summary'] = article_json['abstract']

    item['content_html'] = ''
    for block in article_json['body']:
        if block['type'] == 'text':
            # remove onclick and other attributes from links
            text = re.sub(r'<a\s.*?href="([^"]+)"[^>]*>(.*?)<\/a>', r'<a href="\1">\2</a>', block['text'])
            if block['isParagraph']:
                item['content_html'] += '<p>{}</p>'.format(text)
            else:
                item['content_html'] += text
        elif block['type'] == 'mainart':
            if block['data']['type'] == 'image':
                item['content_html'] += add_image(block['data'])
            elif block['data']['type'] == 'slideshow':
                for it in block['data']['images']:
                    item['content_html'] += add_image(it)
        elif block['type'] == 'genericimage':
            item['content_html'] += add_image(block)
        elif block['type'] == 'youtube':
            item['content_html'] += utils.add_embed('https://www.youtube.com/watch?v={}'.format(block['youtubeid']))
        elif block['type'] == 'oovvuuVideo':
            item['content_html'] += add_oovvuu_video(block['id'])
        elif block['type'] == 'inbrief':
            if block.get('items'):
                logger.warning('unhandled block inbrief in ' + item['url'])
        elif block['type'] == 'endnote':
            if not block.get('author'):
                item['content_html'] += '<hr/><p><em>{}</em></p>'.format(block['text'])
        elif block['type'] == 'star-rating':
            item['content_html'] = '<h2>Rating: {} / 4</h2>'.format(block['stars'])
        elif re.search(r'\bad\b|conversations|\bcta\b|related|shareBar|slimcut|textBreakPoint|trustBar', block['type'], flags=re.I):
            continue
        else:
            logger.warning('unhandled block type {} in {}'.format(block['type'], item['url']))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
