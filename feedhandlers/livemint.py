import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_img_src(image):
    if image['width'] > 0:
        w = image['width']
    elif image['images'].get('width'):
        w = int(image['images']['width'])
    else:
        w = 0
    if image['height'] > 0:
        h = image['height']
    elif image['images'].get('width'):
        h = int(image['images']['height'])
    else:
        h = 0
    if w >= h:
        img_src = image['images']['1600x900']
    else:
        img_src = image['images']['900x1600']
    return img_src


def add_image(image):
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('imageCredit'):
        captions.append(image['imageCredit'])
    img_src = get_img_src(image)
    return utils.add_image(img_src, ' | '.join(captions))


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    m = re.search(r'(\d+)\.html', paths[-1])
    if not m:
        logger.warning('unhandled url ' + url)
        return None
    api_url = 'https://' + split_url.netloc + '/api/cms/story/v2/' + m.group(1)
    story_json = utils.get_url_json(api_url)
    if not story_json:
        return None
    if save_debug:
        utils.write_file(story_json, './debug/debug.json')
    story_url = 'https://' + split_url.netloc + story_json['metadata']['url']
    return get_story(story_json, story_url, args, site_json, save_debug)


def get_story(story_json, url, args, site_json, save_debug):
    item = {}
    item['id'] = story_json['id']
    item['url'] = url
    item['title'] = story_json['title']

    dt = datetime.fromisoformat(story_json['firstPublishedDate']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if story_json.get('lastModifiedDate'):
        dt = datetime.fromisoformat(story_json['lastModifiedDate']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['authors'] = []
    if story_json['metadata'].get('authors'):
        item['authors'] = [{"name": x} for x in story_json['metadata']['authors']]
    elif story_json['metadata'].get('agencyByLine'):
        for it in story_json['metadata']['agencyByLine']:
            if it == story_json['metadata']['agency']:
                item['authors'].append({"name": it})
            else:
                item['authors'].append({"name": it + ' (' + story_json['metadata']['agency'] + ')'})
    elif story_json['metadata'].get('agency'):
        item['authors'].append({"name": story_json['metadata']['agency']})
    elif story_json['metadata'].get('writtenBy'):
        item['authors'] = [{"name": x} for x in story_json['metadata']['writtenBy']]
    if 'authors' in item and len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    else:
        logger.warning('unknown authors in ' + item['url'])
        del item['authors']

    item['tags'] = []
    item['tags'].append(story_json['metadata']['section'])
    if story_json['metadata'].get('topic'):
        item['tags'] += [x for x in story_json['metadata']['topic'] if x not in item['tags']]
    if story_json['metadata'].get('tags'):
        item['tags'] += [x for x in story_json['metadata']['tags'] if x not in item['tags']]
    if story_json['metadata'].get('keywords'):
        item['tags'] += [x for x in story_json['metadata']['keywords'] if x not in item['tags']]

    if story_json.get('summary'):
        item['summary'] = story_json['summary']
    elif story_json['metadata'].get('metaDescription'):
        item['summary'] = story_json['metadata']['metaDescription']

    item['content_html'] = ''
    if 'summary' in item:
        item['content_html'] += '<p><em>' + item['summary'] + '</em></p>'

    if story_json.get('leadMedia') and story_json['leadMedia'].get('image'):
        item['image'] = get_img_src(story_json['leadMedia']['image'])
        item['content_html'] += add_image(story_json['leadMedia']['image'])

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    for element in story_json['listElement']:
        if element['type'] == 'paragraph':
            item['content_html'] += element['paragraph']['body']
        elif element['type'] == 'image':
            item['content_html'] += add_image(element['image'])
        elif element['type'] == 'table':
            m = re.search(r'<table>.*</table>', element['paragraph']['body'])
            if m:
                el_html = m.group(0)
            else:
                logger.warning('non-standard table in ' + item['html'])
                el_html = element['paragraph']['body']
            el_html = re.sub(r'<table>', '<table style="width:100%; border-collapse:collapse; border-top:1px solid light-dark(#333,#ccc);">', el_html)
            el_html = re.sub(r'<tr>', '<tr style="border-bottom:1px solid light-dark(#333,#ccc);">', el_html)
            el_html = re.sub(r'<td>', '<td style="padding:4px;">', el_html)
            el_html = re.sub(r'<th>(?!<p)', '<th style="padding:4px; background-color:#aaa">', el_html)
            el_html = re.sub(r'<th>', '<th style="background-color:#aaa">', el_html)
            item['content_html'] += el_html
        elif element['type'] == 'review':
            if element['review'].get('pros'):
                item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                item['content_html'] += '<div style="flex:1; min-width:360px;"><div style="font-size:1.1em; font-weight:bold;">Pros</div><ul>'
                for it in element['review']['pros']:
                    item['content_html'] += '<li>' + it + '</li>'
                item['content_html'] += '</ul></div><div style="flex:1; min-width:360px;"><div style="font-size:1.1em; font-weight:bold;">Cons</div><ul>'
                for it in element['review']['cons']:
                    item['content_html'] += '<li>' + it + '</li>'
                item['content_html'] += '</ul></div></div>'
            if element['review']['rating'] > 0 or element['review'].get('productName') or element['review'].get('specification'):
                logger.warning('unhandled review items in ' + item['url'])
        elif element['type'] == 'faq':
            item['content_html'] += '<h2>FAQ: ' + element['faqSectionHeading'] + '</h2>'
            for it in element['faqs']:
                item['content_html'] += '<h3 style="margin-bottom:0;">' + it['key'] + '</h3>'
                item['content_html'] += '<p style="margin-left:2em;">' + it['value'] + '</p>'
        elif element['type'] == 'embed':
            if element.get('amazonAds'):
                continue
            el_html = ''
            if element['embed']['body'].startswith('<iframe'):
                m = re.search(r'src="([^"]+)', element['embed']['body'])
                if m:
                    el_html = utils.add_embed(m.group(1))
            elif 'instagram-media' in element['embed']['body']:
                m = re.search(r'data-instgrm-permalink="([^"]+)', element['embed']['body'])
                if m:
                    el_html = utils.add_embed(m.group(1))
            if el_html:
                item['content_html'] += el_html
            else:
                logger.warning('unhandled embed in ' + item['url'])
        elif element['type'] == 'alsoread' or element['type'] == 'relatedstory' or element['type'] == 'market':
            pass
        else:
            logger.warning('unhandled element type {} in {}'.format(element['type'], item['url']))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(div|figure|table|/li)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    if path == '/latest-news':
        path = '/'
    api_url = 'https://www.livemint.com/api/cms/page?url=' + path
    page_json = utils.get_url_json(api_url)
    if not page_json:
        return None
    if save_debug:
        utils.write_file(page_json, './debug/feed.json')

    n = 0
    feed_items = []
    for content in page_json['content']:
        story_url = 'https://' + split_url.netloc + content['metadata']['url']
        if save_debug:
            logger.debug('getting content for ' + story_url)
        if content.get('listElement'):
            item = get_story(content, story_url, args, site_json, save_debug)
        else:
            item = get_content(story_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    if page_json.get('title'):
        feed['title'] = page_json['title']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed