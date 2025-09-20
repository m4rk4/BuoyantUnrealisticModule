import base64, json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://www.thequint.com/api/v1/stories/{story-id}
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', id='static-page')
    if not el:
        logger.warning('unable to find static-page info in ' + url)
        return None

    static_page = json.loads(el.string)
    if save_debug:
        utils.write_file(static_page, './debug/static_page.json')
    story_json = static_page['qt']['data']['story']
    if save_debug:
        utils.write_file(story_json, './debug/debug.json')
    cdn_image = 'https://' + static_page['qt']['config']['cdn-image'] + '/'

    item = {}
    item['id'] = story_json['id']
    item['url'] = story_json['url']
    item['title'] = story_json['headline']

    dt = datetime.fromtimestamp(story_json['published-at'] / 1000).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if story_json.get('updated-at'):
        dt = datetime.fromtimestamp(story_json['updated-at'] / 1000).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['authors'] = [{"name": x['name']} for x in story_json['authors']]
    item['author'] = {
        "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
    }

    item['tags'] = []
    if story_json.get('tags'):
        item['tags'] += [x['name'] for x in story_json['tags']]
    if 'seo' in story_json and story_json['seo'].get('meta-keywords'):
        item['tags'] += story_json['seo']['meta-keywords']
    if len(item['tags']) > 0:
        # Remove duplicates (case-insensitive)
        item['tags'] = list(dict.fromkeys([it.casefold() for it in item['tags']]))
    else:
        del item['tags']

    item['content_html'] = ''
    if 'seo' in story_json and story_json['seo'].get('meta-description'):
        item['summary'] = story_json['seo']['meta-description']
    if story_json.get('summary'):
        item['content_html'] += '<p><em>' + story_json['summary'] + '</em></p>'
        if 'summary' not in item:
            item['summary'] = story_json['summary']
    elif story_json.get('subheadline'):
        item['content_html'] += '<p><em>' + story_json['subheadline'] + '</em></p>'
        if 'summary' not in item:
            item['summary'] = story_json['subheadline']

    if story_json.get('hero-image-s3-key'):
        item['_image'] = cdn_image + quote_plus(story_json['hero-image-s3-key']) + '?auto=format%2Ccompress&fmt=webp&width=720'
        if story_json['story-template'] != 'video':
            captions = []
            if story_json.get('hero-image-caption'):
                m = re.search(r'<p>(.*?)</p>', story_json['hero-image-caption'])
                if m:
                    captions.append(m.group(1))
                else:
                    captions.append(story_json['hero-image-caption'])
            if story_json.get('hero-image-attribution'):
                m = re.search(r'<p>(.*?)</p>', story_json['hero-image-attribution'])
                if m:
                    captions.append(m.group(1))
                else:
                    captions.append(story_json['hero-image-attribution'])
            item['content_html'] += utils.add_image(item['_image'], ' '.join(captions))

    for card in story_json['cards']:
        for element in card['story-elements']:
            if element['type'] == 'text':
                if element.get('metadata') and element['metadata'].get('promotional-message'):
                    pass
                elif not element['subtype']:
                    item['content_html'] += element['text']
                elif element['subtype'] == 'blurb':
                    item['content_html'] += utils.add_blockquote(element['metadata']['content'])
                elif element['subtype'] == 'q-and-a':
                    item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;">' + re.sub(r'</?p>', '', element['metadata']['question']) + '</div>'
                    item['content_html'] += '<div style="margin-left:10px; padding-left:10px;">' + element['metadata']['answer'] + '</div>'
                elif element['subtype'] == 'blockquote':
                    item['content_html'] += utils.add_pullquote(element['metadata']['content'], element['metadata'].get('attribution'))
                elif element['subtype'] == 'also-read':
                    pass
                else:
                    logger.warning('unhandled story element text subtype {} in {}'.format(element['subtype'], item['url']))
            elif element['type'] == 'title':
                item['content_html'] += '<h2>' + element['text'] + '</h2>'
            elif element['type'] == 'image':
                img_src = cdn_image + quote_plus(element['image-s3-key']) + '?auto=format%2Ccompress&fmt=webp&width=720'
                captions = []
                if element.get('image-caption'):
                    m = re.search(r'<p>(.*?)</p>', element['image-caption'])
                    if m:
                        captions.append(m.group(1))
                    else:
                        captions.append(element['image-caption'])
                if element.get('image-attribution'):
                    m = re.search(r'<p>(.*?)</p>', element['image-attribution'])
                    if m:
                        captions.append(m.group(1))
                    else:
                        captions.append(element['image-attribution'])
                item['content_html'] += utils.add_image(img_src, ' '.join(captions))
            elif element['type'] == 'youtube-video':
                item['content_html'] += utils.add_embed(element['url'])
            elif element['type'] == 'jsembed':
                if not element['subtype'] and element.get('embed-js') and element['embed-js'].endswith('='):
                    embed_js = base64.b64decode(element['embed-js']).decode('utf-8')
                    if embed_js.startswith('<iframe'):
                        m = re.search(r'src="([^"]+)"', embed_js)
                        # Skip Listen to article powered by Trinity Audio
                        if 'trinitymedia.ai' not in m.group(1):
                            item['content_html'] += utils.add_embed(m.group(1))
                    else:
                        logger.warning('unhandled jsembed embed-js {} in {}'.format(embed_js, item['url']))
                elif element['subtype'] == 'tweet':
                    item['content_html'] += utils.add_embed(element['metadata']['tweet-url'])
                else:
                    logger.warning('unhandled story element jsembed subtype {} in {}'.format(element['subtype'], item['url']))
            elif element['type'] == 'data':
                if element['subtype'] == 'table' and element['data']['content-type'] == 'csv':
                    item['content_html'] += '<table style="width:100%; border-collapse:collapse;">'
                    for i, row in enumerate(element['data']['content'].strip().split('\r\n')):
                        if i % 2 == 0:
                            item['content_html'] += '<tr style="line-height:2em; border-bottom:1pt solid black;">'
                        else:
                            item['content_html'] += '<tr style="line-height:2em; border-bottom:1pt solid black; background-color:#ccc;">'
                        for td in row.split(','):
                            if i == 0:
                                item['content_html'] += '<th style="text-align:left;">' + td + '</th>'
                            else:
                                item['content_html'] += '<td>' + td + '</td>'
                        item['content_html'] += '</tr>'
                    item['content_html'] += '</table>'
                else:
                    logger.warning('unhandled story element data subtype {} in {}'.format(element['subtype'], item['url']))
            else:
                logger.warning('unhandled story element type {} in {}'.format(element['type'], item['url']))
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
