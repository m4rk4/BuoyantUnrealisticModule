import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote, urlsplit

import config, utils
from feedhandlers import brightcove, rss

import logging

logger = logging.getLogger(__name__)


def resize_image(image, width=1000):
    # https://www.dw.com/static/js/utils/imgUtils.js
    landscape_formats = [
        {
            "id": 600,
            "width": 78,
        }, {
            "id": 601,
            "width": 201,
        }, {
            "id": 602,
            "width": 379,
        }, {
            "id": 603,
            "width": 545,
        }, {
            "id": 604,
            "width": 767,
        }, {
            "id": 605,
            "width": 1199,
        }, {
            "id": 606,
            "width": 1568,
        }, {
            "id": 607,
            "width": 1920,
        }
    ]
    fmt = utils.closest_dict(landscape_formats, 'width', width)
    if image['__typename'] == 'GalleryImage':
        return image['assignedImage']['staticUrl'].replace('${formatId}', str(fmt['id']))
    return image['target']['staticUrl'].replace('${formatId}', str(fmt['id']))


def add_image(image, width=1000):
    captions = []
    if image.get('description'):
        captions.append(image['description'])
    if image['__typename'] == 'GalleryImage':
        if image['assignedImage'].get('licenserSupplement'):
            captions.append(image['assignedImage']['licenserSupplement'])
    else:
        if image['target'].get('licenserSupplement'):
            captions.append(image['target']['licenserSupplement'])
    return utils.add_image(resize_image(image), ' | '.join(captions))


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    path = paths[-1].split('-')
    if path[0] == 'a':
        api_url = 'https://www.dw.com/graph-api/en/content/article/' + path[1]
    elif path[0] == 'g':
        api_url = 'https://www.dw.com/graph-api/en/content/image-gallery/' + path[1]
    elif path[0] == 'video':
        api_url = 'https://www.dw.com/graph-api/en/content/video/' + path[1]
    elif path[0] == 'audio':
        api_url = 'https://www.dw.com/graph-api/en/content/audio/' + path[1]
    else:
        logger.warning('unhandled url ' + url)
        return None

    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')
    content_json = api_json['data']['content']

    item = {}
    item['id'] = content_json['id']
    item['url'] = content_json['canonicalUrl']
    item['title'] = content_json['title']

    dt = datetime.fromisoformat(content_json['firstPublicationDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if content_json.get('lastPublicationDate'):
        dt = datetime.fromisoformat(content_json['lastPublicationDate'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if content_json.get('persons'):
        item['authors'] = [{"name": x['fullName']} for x in content_json['persons']]
    elif content_json.get('legacyAuthor'):
        item['authors'] = [{"name": content_json['legacyAuthor']}]
    else:
        item['authors'] = [{"name": "DW.com"}]    
    item['author'] = {
        "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
    }

    if content_json.get('relatedAutoTopics'):
        item['tags'] = []
        for it in content_json['relatedAutoTopics']:
            item['tags'].append(it['name'])

    item['content_html'] = ''
    if content_json['__typename'] == 'Article':
        if content_json.get('teaser'):
            item['summary'] = content_json['teaser']
            item['content_html'] += '<p><em>' + item['summary'] + '</em></p>'
        if content_json.get('mainContentImageLink'):
            item['image'] = resize_image(content_json['mainContentImageLink'])
            if not re.search(r'/image/{}'.format(content_json['mainContentImageLink']['target']['id']), content_json['text']):
                item['content_html'] += add_image(content_json['mainContentImageLink'])

    elif content_json['__typename'] == 'ImageGallery':
        if content_json.get('teaser'):
            item['summary'] = content_json['teaser']
            item['content_html'] += '<p>' + item['summary'] + '</p>'
        if content_json.get('mainContentImageLink'):
            item['image'] = resize_image(content_json['mainContentImageLink'])
        item['_gallery'] = []
        item['content_html'] += '<h3><a href="{}/gallery?url={}" target="_blank">View slideshow</a></h3>'.format(config.server, quote(item['url']))
        item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
        for i, image in enumerate(content_json['extendedGalleryImages']):
            img_src = resize_image(image, 2000)
            thumb = resize_image(image, 640)
            if image['assignedImage'].get('licenserSupplement'):
                caption = image['assignedImage']['licenserSupplement']
            else:
                caption = ''
            desc = ''
            if image.get('name'):
                desc += '<h3>' + image['name'] + '</h3>'
            if image.get('description'):
                desc += '<p>' + image['description'] + '</p>'
            item['content_html'] += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src, desc=desc) + '</div>'
            item['_gallery'].append({"src": img_src, "caption": caption, "thumb": thumb, "desc": desc})
        if i % 2 == 0:
            item['content_html'] += '<div style="flex:1; min-width:360px;"></div>'
        item['content_html'] += '</div>'

    elif content_json['__typename'] == 'Video':
        if content_json.get('posterImageUrl'):
            item['image'] = content_json['posterImageUrl']
            poster = item['image']
        else:
            poster = ''
        item['content_html'] += utils.add_video(content_json['hlsVideoSrc'], 'application/x-mpegURL', poster)
        if content_json.get('teaser'):
            item['summary'] = content_json['teaser']
            item['content_html'] += '<p>' + item['summary'] + '</p>'

    elif content_json['__typename'] == 'Audio':
        if content_json.get('mainContentImageLink'):
            item['image'] = resize_image(content_json['mainContentImageLink'])
            item['content_html'] += add_image(content_json['mainContentImageLink'])
        item['_audio'] = content_json['mp3Src']
        attachment = {}
        attachment['url'] = item['_audio']
        attachment['mime_type'] = 'audio/mpeg'
        item['attachments'] = []
        item['attachments'].append(attachment)
        item['content_html'] += '<table><tr><td style="width:48px;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a></td><td><a href="{0}"><span style="font-size:1.1em; font-weight:bold;">Listen</span></a> ({2})</td></tr></table>'.format(item['_audio'], config.server, content_json['formattedDuration'])
        if content_json.get('teaser'):
            item['summary'] = content_json['teaser']
            item['content_html'] += '<p>' + item['summary'] + '</p>'

    if content_json.get('text'):
        soup = BeautifulSoup(content_json['text'], 'html.parser')
        for el in soup.find_all(class_='placeholder-image'):
            image = next((it for it in content_json['contentLinks'] if it['targetId'] == int(el.img['data-id'])), None)
            if image:
                img = image.copy()
                img['target']['staticUrl'] = el.img['data-url']
                new_html = add_image(img)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled placeholder-image in ' + item['url'])

        for el in soup.find_all(class_='embed'):
            new_html = ''
            if 'vjs-wrapper' in el['class']:
                media = el.find('video')
                if media:
                    src = el.find('source', attrs={"type": "video/mp4"})
                    if not src:
                        src = el.find('source', attrs={"type": "application/x-mpegURL"})
                    if src:
                        poster = media['data-posterurl']
                        content = next((it for it in content_json['contentLinks'] if it['targetId'] == int(media['data-id'])), None)
                        if content and content.get('name'):
                            caption = '<a href="{}://{}{}">{}</a>'.format(split_url.scheme, split_url.netloc, content['target']['namedUrl'], content['name'])
                        else:
                            caption = ''
                        new_html = utils.add_video(src['src'], src['type'], poster, caption)
                else:
                    media = el.find('audio')
                    if media:
                        src = el.find('source', attrs={"type": "audio/mp3"})
                        if src:
                            poster = '{}/image?url={}&width=128&overlay=audio'.format(config.server, quote(media['data-posterurl']))
                            content = next((it for it in content_json['contentLinks'] if it['targetId'] == int(media['data-id'])), None)
                            if content:
                                new_html = '<table><tr><td><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;"><span style="font-size:1.1em; font-weight:bold"><a href="{}://{}{}">{}</a></span><br/><small>{}&nbsp;&bull;&nbsp;{}</small></td></tr></table>'.format(src['src'], poster, split_url.scheme, split_url.netloc, content['target']['namedUrl'], content['target']['name'], content['target']['localizedContentDateSr'], content['target']['formattedDurationInMinutes'])
            elif 'yt-wrapper' in el['class']:
                it = el.find('iframe')
                if it:
                    new_html = utils.add_embed(it['data-src'])
            elif 'tweet' in el['class']:
                new_html = utils.add_embed('https://twitter.com/__/status/' + el['data-id'])
            elif 'image-gallery' in el['class']:
                content = next((it for it in content_json['contentLinks'] if it['targetId'] == int(el['data-id'])), None)
                if content:
                    content_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, content['target']['namedUrl'])
                    content_url = '{}/content?read&url={}'.format(config.server, quote(content_url))
                    caption = '<a href="{}"><strong>View Gallery</gallery></a> {}'.format(content_url, content['name'])
                    new_html += utils.add_image(resize_image(content['target']['mainContentImageLink']), caption, link=content_url)
            elif 'dw-widget' in el['class']:
                widget = next((it for it in content_json['widgets'] if it['id'] == int(el['data-id'])), None)
                if widget:
                    if widget.get('embedCode'):
                        widget_soup = BeautifulSoup(widget['embedCode'], 'html.parser')
                        if widget_soup.find(id='promio-pym-container'):
                            continue
                        else:
                            it = widget_soup.find(attrs={"ai2html-url": True})
                            if it:
                                new_html = utils.add_image('{}/screenshot?url={}&locator=.ai2html'.format(config.server, quote(it['ai2html-url'])), link=it['ai2html-url'])
                    elif content_json.get('contentLinks'):
                        widget = next((it for it in content_json['contentLinks'] if it['targetId'] == int(el['data-id'])), None)
                        if widget:
                            if 'newsletter' in widget['name'].lower():
                                continue
                            elif widget.get('target') and widget['target']['__typename'] == 'Widget':
                                api_url = 'https://www.dw.com/webapi/iframes/widget/en/' + str(widget['target']['id'])
                                new_html = utils.add_image('{}/screenshot?url={}&cropbbox=1'.format(config.server, quote(api_url)), widget['target'].get('title'), link=api_url)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled embed {} in {}'.format(el['class'], item['url']))

        for el in soup.find_all('a', class_='external-link'):
            it = el.find('svg')
            if it:
                it.decompose()

        item['content_html'] += str(soup)

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path.split('/')))
    path = paths[-1].split('-')
    if path[0] == 's':
        api_url = 'https://www.dw.com/graph-api/en/content/navigation/' + path[1]
    elif path[0] == 't':
        api_url = 'https://www.dw.com/graph-api/en/content/auto-topic/' + path[1]
    else:
        logger.warning('unhandled url ' + args['url'])
        return None
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    urls = []
    for space in api_json['data']['content']['contentComposition']['informationSpaces']:
        for key, val in space.items():
            if val and isinstance(val, list):
                for component in val:
                    if component.get('contents'):
                        for content in component['contents']:
                            if content['namedUrl'].startswith('http'):
                                urls.append(content['namedUrl'])
                            else:
                                urls.append('{}://{}{}'.format(split_url.scheme, split_url.netloc, content['namedUrl']))

    n = 0
    feed_items = []
    for url in urls:
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    if api_json['data']['content'].get('pageHeadline'):
        feed['title'] = 'DW | {}'.format(api_json['data']['content']['pageHeadline'])
    else:
        feed['title'] = 'DW | {}'.format(api_json['data']['content']['name'])
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
