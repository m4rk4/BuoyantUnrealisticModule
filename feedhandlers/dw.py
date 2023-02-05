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
        gql_url = 'https://www.dw.com/graphql?operationName=getContentDetails&variables=%7B%22id%22%3A{}%2C%22lang%22%3A%22ENGLISH%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%223787aa4feb7dc970820fa508c2611b32be734f69a0d1731833a589fbd2ce390a%22%7D%7D'.format(path[1])
    elif path[0] == 'g':
        gql_url = 'https://www.dw.com/graphql?operationName=getContentDetails&variables=%7B%22id%22%3A{}%2C%22lang%22%3A%22ENGLISH%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22d89d43e9f08cfb66969cfa6ad2fd1d3a6ed8acda3a59626a5f1a9ccc8d4a9d0c%22%7D%7D'.format(path[1])
    elif path[0] == 'video':
        gql_url = 'https://www.dw.com/graphql?operationName=getContentDetails&variables=%7B%22id%22%3A{}%2C%22lang%22%3A%22ENGLISH%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%229e5c396aa4bafff8e3c8112c3494ffdc0b15bc18d9f21f9c2daabf3eb4b214f6%22%7D%7D'.format(path[1])
    elif path[0] == 'audio':
        gql_url = 'https://www.dw.com/graphql?operationName=getContentDetails&variables=%7B%22id%22%3A{}%2C%22lang%22%3A%22ENGLISH%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22cbf18ddb6765ad7e78d3ca7b7d58cd5e2377b986aa3608956075b572132c5050%22%7D%7D'.format(path[1])
    else:
        logger.warning('unhandled url ' + url)
        return None
    gql_json = utils.get_url_json(gql_url)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')

    article_json = gql_json['data']['content']
    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['canonicalUrl']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['firstPublicationDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['lastPublicationDate'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('persons'):
        authors = []
        for it in article_json['persons']:
            authors.append(it['fullName'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif article_json.get('legacyAuthor'):
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', article_json['legacyAuthor'])
    else:
        item['author']['name'] = 'DW.com'

    if article_json.get('relatedAutoTopics'):
        item['tags'] = []
        for it in article_json['relatedAutoTopics']:
            item['tags'].append(it['name'])

    item['content_html'] = ''
    if article_json['__typename'] == 'Article':
        if article_json.get('teaser'):
            item['summary'] = article_json['teaser']
            item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

        if article_json.get('mainContentImageLink'):
            item['_image'] = resize_image(article_json['mainContentImageLink'])
            if not re.search(r'/image/{}'.format(article_json['mainContentImageLink']['target']['id']), article_json['text']):
                item['content_html'] += add_image(article_json['mainContentImageLink'])

    elif article_json['__typename'] == 'ImageGallery':
        if article_json.get('teaser'):
            item['summary'] = article_json['teaser']
            item['content_html'] += '<p>{}</p>'.format(item['summary'])
        if article_json.get('mainContentImageLink'):
            item['_image'] = resize_image(article_json['mainContentImageLink'])
        for it in article_json['extendedGalleryImages']:
            item['content_html'] += add_image(it)

    elif article_json['__typename'] == 'Video':
        if article_json.get('mainContentImageLink'):
            item['_image'] = resize_image(article_json['mainContentImageLink'])
            poster = item['_image']
        else:
            poster = ''
        item['content_html'] += utils.add_video(article_json['hlsVideoSrc'], 'application/x-mpegURL', poster)
        if article_json.get('teaser'):
            item['summary'] = article_json['teaser']
            item['content_html'] += '<p>{}</p>'.format(item['summary'])

    elif article_json['__typename'] == 'Audio':
        if article_json.get('mainContentImageLink'):
            item['_image'] = resize_image(article_json['mainContentImageLink'])
            item['content_html'] += add_image(article_json['mainContentImageLink'])
        item['_audio'] = article_json['mp3Src']
        attachment = {}
        attachment['url'] = item['_audio']
        attachment['mime_type'] = 'audio/mpeg'
        item['attachments'] = []
        item['attachments'].append(attachment)
        item['content_html'] += '<table><tr><td style="width:48px;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a></td><td><a href="{0}"><span style="font-size:1.1em; font-weight:bold;">Listen</span></a> ({2})</td></tr></table>'.format(item['_audio'], config.server, article_json['formattedDuration'])

        if article_json.get('teaser'):
            item['summary'] = article_json['teaser']
            item['content_html'] += '<p>{}</p>'.format(item['summary'])

    if article_json.get('text'):
        soup = BeautifulSoup(article_json['text'], 'html.parser')
        for el in soup.find_all(class_='placeholder-image'):
            image = next((it for it in article_json['contentLinks'] if it['targetId'] == int(el.img['data-id'])), None)
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
                        content = next((it for it in article_json['contentLinks'] if it['targetId'] == int(media['data-id'])), None)
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
                            content = next((it for it in article_json['contentLinks'] if it['targetId'] == int(media['data-id'])), None)
                            if content:
                                new_html = '<table><tr><td><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;"><span style="font-size:1.1em; font-weight:bold"><a href="{}://{}{}">{}</a></span><br/><small>{}&nbsp;&bull;&nbsp;{}</small></td></tr></table>'.format(src['src'], poster, split_url.scheme, split_url.netloc, content['target']['namedUrl'], content['target']['name'], content['target']['localizedContentDateSr'], content['target']['formattedDurationInMinutes'])
            elif 'yt-wrapper' in el['class']:
                it = el.find('iframe')
                if it:
                    new_html = utils.add_embed(it['data-src'])
            elif 'tweet' in el['class']:
                new_html = utils.add_embed(utils.get_twitter_url(el['data-id']))
            elif 'image-gallery' in el['class']:
                content = next((it for it in article_json['contentLinks'] if it['targetId'] == int(el['data-id'])), None)
                if content:
                    content_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, content['target']['namedUrl'])
                    content_url = '{}/content?read&url={}'.format(config.server, quote(content_url))
                    caption = '<a href="{}"><strong>View Gallery</gallery></a> {}'.format(content_url, content['name'])
                    new_html += utils.add_image(resize_image(content['target']['mainContentImageLink']), caption, link=content_url)
            elif 'dw-widget' in el['class']:
                widget = next((it for it in article_json['widgets'] if it['id'] == int(el['data-id'])), None)
                if widget:
                    widget_soup = BeautifulSoup(widget['embedCode'], 'html.parser')
                    if widget_soup.find(id='promio-pym-container'):
                        continue
                    else:
                        it = widget_soup.find(attrs={"ai2html-url": True})
                        if it:
                            new_html = utils.add_image('{}/screenshot?url={}&locator=.ai2html'.format(config.server, quote(it['ai2html-url'])), link=it['ai2html-url'])

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
        gql_url = 'https://www.dw.com/graphql?operationName=getNavigationPage&variables=%7B%22id%22%3A{}%2C%22lang%22%3A%22ENGLISH%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%227dca89fa0d269c097f2bf6a28ef35efbe50531ca62b9b34f4e0904657719d339%22%7D%7D'.format(path[1])
    elif path[0] == 't':
        gql_url = 'https://www.dw.com/graphql?operationName=getAutoTopicPage&variables=%7B%22id%22%3A{}%2C%22lang%22%3A%22ENGLISH%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%229d202eb416716f4d732bc49f9f84ef5673033017eb238458324cc76131006109%22%7D%7D'.format(path[1])
    else:
        logger.warning('unhandled url ' + args['url'])
        return None
    gql_json = utils.get_url_json(gql_url)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/feed.json')

    urls = []
    for space in gql_json['data']['content']['contentComposition']['informationSpaces']:
        for key, val in space.items():
            if val and isinstance(val, list):
                for component in val:
                    if component.get('contents'):
                        for content in component['contents']:
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
    if gql_json['data']['content'].get('pageHeadline'):
        feed['title'] = 'DW | {}'.format(gql_json['data']['content']['pageHeadline'])
    else:
        feed['title'] = 'DW | {}'.format(gql_json['data']['content']['name'])
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed

