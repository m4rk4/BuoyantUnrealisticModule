import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200, height=800):
    split_url = urlsplit(img_src)
    paths = list(filter(None, split_url.path.split('/')))
    if split_url.netloc == 'media.graphassets.com':
        return 'https://media.graphassets.com/resize=width:{},height:{}/{}'.format(width, height, paths[-1])
    return img_src


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    path += '.json'
    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    if 'articles' in paths:
        next_url += '?id=' + paths[-1]
    #print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if not el:
            logger.warning('unable to find __NEXT_DATA__ in ' + url)
            return None
        next_data = json.loads(el.string)
        if next_data['buildId'] != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = next_data['buildId']
            utils.update_sites(url, site_json)
        return next_data['props']
    return next_data


def render_content(content, assets):
    content_html = ''
    for i, child in enumerate(content['children']):
        if not child.get('type'):
            if 'text' in child:
                text = child['text'].encode('utf-8').decode().strip()
                if child.get('bold'):
                    content_html += '<b>' + text + '</b>'
                elif text.startswith('---') and text.endswith('---'):
                    content_html += '<div style="text-align:center; font-size:1.1em; font-weight:bold;">{}</div>'.format(re.sub(r'^---(.*)---$', r'\1', text))
                else:
                    content_html += text
            else:
                logger.warning('unknown child type')
        elif child['type'] == 'paragraph':
            content_html += '<p>' + render_content(child, assets) + '</p>'
        elif child['type'] == 'link':
            content_html = '<a href="{}">'.format(child['href']) + render_content(child, assets) + '</a>'
        elif 'heading-' in child['type']:
            if child['type'] == 'heading-one':
                content_html += '<h1>' + render_content(child, assets) + '</h1>'
            elif child['type'] == 'heading-two':
                content_html += '<h2>' + render_content(child, assets) + '</h2>'
            elif child['type'] == 'heading-three':
                content_html += '<h3>' + render_content(child, assets) + '</h3>'
            elif child['type'] == 'heading-four':
                content_html += '<h4>' + render_content(child, assets) + '</h4>'
            elif child['type'] == 'heading-five':
                content_html += '<h5>' + render_content(child, assets) + '</h5>'
        elif child['type'] == 'block-quote':
            content_html += utils.add_blockquote(render_content(child, assets))
        elif child['type'] == 'bulleted-list':
            content_html += '<ul>' + render_content(child, assets) + '</ul>'
        elif child['type'] == 'numbered-list':
            content_html += '<ol>' + render_content(child, assets) + '</ol>'
        elif child['type'] == 'list-item':
            content_html += '<li>' + render_content(child, assets) + '</li>'
        elif child['type'] == 'list-item-child':
            content_html += render_content(child, assets)
        elif child['type'] == 'image':
            img_src = 'https://media.graphassets.com/resize=width:1200,height:800/' + child['handle']
            caption = ''
            if i + 1 < len(content['children']):
                if content['children'][i + 1].get('type') and content['children'][i + 1]['type'] == 'class':
                    if content['children'][i + 1]['className'] == 'caption':
                        caption += render_content(content['children'][i + 1], assets)
                        caption = re.sub(r'^<p>(.*?)</p>$', r'\1', caption)
                    elif content['children'][i + 1]['className'] == 'wrap-right':
                        content_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                        content_html += '<div style="flex:1; min-width:256px;">{}</div>'.format(utils.add_image(img_src, caption))
                        content_html += '<div style="flex:1; min-width:256px;">{}</div>'.format(render_content(content['children'][i + 1], assets))
                        content_html += '</div>'
                        img_src = ''
                    elif content['children'][i + 1]['className'] == 'wrap-left':
                        content_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                        content_html += '<div style="flex:1; min-width:256px;">{}</div>'.format(render_content(content['children'][i + 1], assets))
                        content_html += '<div style="flex:1; min-width:256px;">{}</div>'.format(utils.add_image(img_src, caption))
                        content_html += '</div>'
                        img_src = ''
            if img_src:
                content_html += utils.add_image(img_src, caption)
        elif child['type'] == 'video':
            caption = ''
            if i + 1 <len(content['children']):
                if content['children'][i + 1].get('type') and content['children'][i + 1]['type'] == 'class' and content['children'][i + 1]['className'] == 'caption':
                    caption += render_content(content['children'][i + 1], assets)
                caption = re.sub(r'^<p>(.*?)</p>$', r'\1', caption)
            if child['handle'] in assets['videos']:
                asset = assets['videos'][child['handle']]
                content_html += utils.add_video(asset['url'], asset['mimeType'], '', caption)
            else:
                content_html += utils.add_video(child['src'], child['mimeType'], '', caption)
        elif child['type'] == 'class':
            if child['className'] == 'caption' or child['className'] == 'wrap-left' or child['className'] == 'wrap-right':
                pass
            elif child['className'] == 'carousel':
                carousel_html = render_content(child, assets)
                content_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                for m in re.findall(r'<figure.+?</figure>', carousel_html):
                    content_html += '<div style="flex:1; min-width:256px;">{}</div>'.format(m)
                content_html += '</div>'
            else:
                logger.warning('unhandled class ' + child['className'])
        else:
            logger.warning('unhandled content type ' + child['type'])
    return content_html


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    article_json = next_data['pageProps']['article']

    item = {}
    item['id'] = article_json['id']
    item['url'] = url
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['publishedAt']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['updatedAt']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in article_json['author']:
        authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json.get('keywords'):
        item['tags'] = [tag.strip() for tag in article_json['keywords'].split(',')]

    item['content_html'] = ''
    if article_json.get('hero'):
        if article_json['hero'].get('excerpt'):
            item['content_html'] += '<p><em>{}</em></p>'.format(article_json['hero']['excerpt'])
        if article_json['hero'].get('thumbnails'):
            item['_image'] = resize_image(article_json['hero']['thumbnails'][0]['url'])
        for it in article_json['hero']['thumbnails']:
            item['content_html'] += utils.add_image(resize_image(it['url']))

    for body in article_json['body']:
        if body['__typename'] == 'ParagraphV2':
            item['content_html'] += render_content(body['content']['raw'], article_json['assets'])

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        api_json = utils.get_url_json('https://www.thenewsmovement.com/api/get-landing-page')
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')
        articles = api_json['keepUpToDate']
    else:
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        if save_debug:
            utils.write_file(next_data, './debug/feed.json')
        articles = next_data['pageProps']['data']['articles']

    n = 0
    feed_items = []
    for article in articles:
        article_url = '{}://{}/articles/{}'.format(split_url.scheme, split_url.netloc, article['slug'])
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_content(article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
