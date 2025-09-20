import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    split_url = urlsplit(img_src)
    paths = list(filter(None, split_url.path.split('/')))
    return 'https://images.deadspin.com/tr:w-{}/{}'.format(width, paths[-1])


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    else:
        path = split_url.path
        if path.endswith('/'):
            path = path[:-1]
    next_url = '{}://{}/_next/data/{}{}.json'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    if len(paths) > 1:
        if paths[0] in ['artikel', 'l', 'video']:
            next_url += '?slug=' + paths[1]
        else:
            next_url += '?category=' + paths[1]
    print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if el:
            next_data = json.loads(el.string)
            if next_data['buildId'] != site_json['buildId']:
                logger.debug('updating {} buildId'.format(split_url.netloc))
                site_json['buildId'] = next_data['buildId']
                utils.update_sites(url, site_json)
            return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False):
    # split_url = urlsplit(url)
    # paths = list(filter(None, split_url.path.split('/')))
    # if not paths[-1].isnumeric():
    #     logger.warning('unhandled url ' + url)
    #     return None
    # api_json = utils.get_url_json('https://nos.nl/api/item/' + paths[-1])
    # if not api_json:
    #     return None
    # item_json = api_json['item']
    # if save_debug:
    #     utils.write_file(next_data, './debug/debug.json')

    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')
    page_json = next_data['pageProps']['data']

    item = {}
    item['id'] = page_json['id']
    item['url'] = page_json['url']
    item['title'] = page_json['title']

    dt = datetime.fromisoformat(page_json['publishedAt']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, date_only=True)
    if page_json.get('modifiedAt'):
        dt = datetime.fromisoformat(page_json['modifiedAt']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    if page_json.get('bios'):
        item['authors'] = [{"name": x['name']} for x in page_json['bios']]
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    else:
        item['author'] = {
            "name": page_json['supplyChannelName']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    item['tags'] = []
    if page_json.get('categories'):
        item['tags'] += [x['label'] for x in page_json['categories']]
    if page_json.get('keywords'):
        item['tags'] += page_json['keywords']

    if page_json.get('description'):
        item['summary'] = page_json['description']

    item['content_html'] = ''
    if page_json.get('image') and page_json['image'].get('image'):
        image = utils.closest_dict(page_json['image']['image']['imagesByRatio']['16:9'], 'width', 1200)
        item['image'] = image['url']['jpg']
        captions = []
        if page_json['image']['image'].get('description'):
            captions.append(page_json['image']['image']['description'])
        if page_json['image']['image'].get('copyright'):
            captions.append(page_json['image']['image']['copyright'])
        item['content_html'] += utils.add_image(item['image'], ' | '.join(captions))
    elif page_json.get('shareImageSrc'):
        item['image'] = page_json['shareImageSrc']

    def format_block(block):
        block_html = ''
        if block['type'] == 'text':
            block_html += '<p>' + block['text'] + '</p>'
        elif block['type'] == 'title':
            block_html += '<h3>' + block['title'] + '</h3>'
        elif block['type'] == 'image':
            if block['image']['imagesByRatio'].get('3:4') and not block['image']['imagesByRatio'].get('4:3'):
                image = utils.closest_dict(block['image']['imagesByRatio']['3:4'], 'width', 720)
            else:
                image = utils.closest_dict(block['image']['imagesByRatio']['16:9'], 'width', 1280)
            captions = []
            if block['image'].get('description'):
                captions.append(block['image']['description'])
            if block['image'].get('copyright'):
                captions.append(block['image']['copyright'])
            caption = ' | '.join(captions)
            block_html += utils.add_image(image['url']['jpg'], caption)
        elif block['type'] == 'video':
            image = utils.closest_dict(block['imagesByRatio']['16:9'], 'width', 1280)
            block_html += utils.add_video(block['source']['url'], block['source']['mimetype'], image['url']['jpg'], block['title'])
        elif block['type'] == 'carousel':
            n = len(block['items'])
            if n == 1:
                block_html += format_block(block['items'][0])
            else:
                gallery_items = []
                gallery_html = ''
                for i, it in enumerate(block['items']):
                    if it['type'] == 'image':
                        if it['image']['imagesByRatio'].get('3:4') and not it['image']['imagesByRatio'].get('4:3'):
                            image = utils.closest_dict(it['image']['imagesByRatio']['3:4'], 'width', 1440)
                            src = image['url']['jpg']
                            image = utils.closest_dict(it['image']['imagesByRatio']['3:4'], 'width', 720)
                            thumb = image['url']['jpg']
                        else:
                            image = utils.closest_dict(it['image']['imagesByRatio']['16:9'], 'width', 1920)
                            src = image['url']['jpg']
                            image = utils.closest_dict(it['image']['imagesByRatio']['16:9'], 'width', 768)
                            thumb = image['url']['jpg']
                        captions = []
                        if it['image'].get('description'):
                            captions.append(it['image']['description'])
                        if it['image'].get('copyright'):
                            captions.append(it['image']['copyright'])
                        caption = ' | '.join(captions)
                        gallery_items.append({"src": src, "caption": caption, "thumb": thumb})
                        item_html = utils.add_image(thumb, caption, link=src)
                    elif it['type'] == 'video':
                        image = utils.closest_dict(it['imagesByRatio']['16:9'], 'width', 1280)
                        item_html = utils.add_video(it['source']['url'], it['source']['mimetype'], image['url']['jpg'], it['title'])
                    else:
                        item_html = ''
                        logger.warning('unhandled carousel item type ' + it['type'])
                    if i == 0:
                        if n % 2 == 1:
                            gallery_html += item_html
                        else:
                            gallery_html += '<div style="display:flex; flex-wrap:wrap; gap:8px;">'
                            gallery_html += '<div style="flex:1; min-width:360px;">' + item_html + '</div>'
                    elif i == 1:
                        if n % 2 == 1:
                            gallery_html += '<div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:8px;">'
                        gallery_html += '<div style="flex:1; min-width:360px;">' + item_html + '</div>'
                    else:
                        gallery_html += '<div style="flex:1; min-width:360px;">' + item_html + '</div>'
                gallery_html += '</div>'
                if n > 2:
                    gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_items)))
                    block_html += '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url)
                block_html += gallery_html
        elif block['type'] == 'externalContent':
            if 'nos.nl/widget-embed' in block['url']:
                block_html += utils.add_image(config.server + '/screenshot?waitfortime=5000&url=' + quote_plus(block['url']), block.get('title'), link=block['url'])
            else:
                block_html += utils.add_embed(block['url'])
        elif block['type'] == 'quote':
            block_html += utils.add_pullquote(block['text'], block['author'])
        elif block['type'] == 'textList':
            block_html += block['text']
        elif block['type'] == 'textbox':
            block_html += '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:1em; margin:1em 0;">'
            for it in block['children']:
                block_html += format_block(it)
            block_html += '</div>'
        elif block['type'] == 'link_container':
            pass
        else:
            logger.warning('unhandled block type ' + block['type'])
        return block_html

    if page_json['type'] == 'video':
        item['content_html'] += format_block(page_json['video'])
        if not 'embed' in args and 'summary' in item:
            item['content_html'] += '<p>' + item['summary'] + '</p>'
    elif 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
    else:
        for it in page_json['items']:
            item['content_html'] += format_block(it)
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    if 'latestNews' in next_data['pageProps']:
        articles = next_data['pageProps']['latestNews']['items']
    elif 'items' in next_data['pageProps']:
        articles = next_data['pageProps']['items']
    else:
        logger.warning('unknown page items in ' + url)
        return None

    n = 0
    feed_items = []
    for it in articles:
        if it['type'] == 'article':
            article_url = 'https://nos.nl/artikel/' + it['id']
        elif it['type'] == 'video':
            article_url = 'https://nos.nl/video/' + it['id']
        elif it['type'] == 'liveblog':
            # TODO:
            article_url = 'https://nos.nl/liveblog/' + it['id']
            logger.debug('skipping  content for ' + article_url)
            continue
        else:
            logger.warning('unhandled content type {} in {}'.format(it['type'], url))
            continue
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
