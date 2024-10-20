import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_window_data(url, save_debug):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    page_soup = BeautifulSoup(page_html, 'lxml')
    el = page_soup.find('script', string=re.compile(r'window\.__data='))
    if not el:
        logger.warning('unable to find window.__data in ' + url)
        return None
    i = el.string.find('{')
    j = el.string.rfind('}') + 1
    data = el.string[i:j].replace('\\\\\\"', '&QUOT;').replace('\\"', '"')
    data_json = json.loads(data)
    if save_debug:
        utils.write_file(data_json, './debug/data.json')
    return data_json


def get_content(url, args, site_json, save_debug=False):
    data_json = get_window_data(url, save_debug)
    key = list(data_json['dal']['getCMSAssetsUrlConfig'].keys())[0]
    article_json = data_json['dal']['getCMSAssetsUrlConfig'][key]['data'][0]
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = 'https://www.weather.com' + article_json['url']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['publishdate']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['lastmodifieddate']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    if article_json.get('author'):
        item['authors'] = [{"name": x} for x in article_json['author'][0].split(', ')]
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    elif article_json.get('providername'):
        item['author'] = {
            "name": article_json['providername']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    item['tags'] = []
    if article_json['tags'].get('keyword'):
        item['tags'] = article_json['tags']['keyword'].copy()
    if article_json['seometa'].get('keywords'):
        item['tags'] += article_json['seometa']['keywords'].split(',')
    if len(item['tags']) == 0:
        del item['tags']

    item['image'] = article_json['seometa']['og:image']
    item['summary'] = article_json['description']

    if article_json['type'] == 'video':
        item['content_html'] = utils.add_video(article_json['format_urls']['m3u8'], 'application/x-mpegURL', article_json['variants']['0'], article_json['teaserTitle'])
        if 'embed' not in args:
            item['content_html'] += '<p>' + article_json['description'] + '</p>'
        return item

    item['content_html'] = ''
    if article_json.get('story_brief'):
        item['content_html'] += '<h3>At a glance</h3><ul>'
        for it in article_json['story_brief']:
            item['content_html'] += '<li>' + it + '</li>'
        item['content_html'] += '</ul>'

    dal = data_json['dal']
    wxnodes = article_json['wxnodes']
    def replace_node(matchobj):
        nonlocal dal
        nonlocal wxnodes
        node = next((it for it in wxnodes if it['id'] == matchobj.group(1)), None)
        if node:
            if node['type'] == 'wxnode_internal_image':
                for key, val in dal['getCMSAssetByIDUrlConfig'].items():
                    if key.startswith('assetId:' + node['assetid']):
                        img_src = val['data']['variants']['0']
                        thumb = utils.clean_url(val['data']['variants']['1']) + '?v=ap&w=1080&h=0'
                        new_html = utils.add_image(thumb, val['data'].get('caption'), link=img_src)
                        break
            elif node['type'] == 'wxnode_slideshow':
                for key, val in dal['getCMSAssetsSlideshowUrlConfig'].items():
                    if key.startswith('assetId:' + node['slideshow']):
                        gallery_images = []
                        new_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                        for asset in val['data']['assets']:
                            if asset['type'] == 'image':
                                img_src = asset['variants']['0']
                                thumb = utils.clean_url(asset['variants']['1']) + '?v=ap&w=720&h=0'
                                if asset.get('caption'):
                                    caption = asset['caption']
                                else:
                                    caption = ''
                                new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src) + '</div>'
                                gallery_images.append({"src": img_src, "caption": caption, "thumb": thumb})
                        gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
                        new_html = '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + new_html
                        break
            elif node['type'] == 'wxnode_video' and node['playlist_type'] == 'playlist':
                for key, val in dal['getCMSOrderedListUrlConfig'].items():
                    if key.startswith('collectionId:' + node['collection_name']):
                        thumb = utils.clean_url(val['data'][0]['variants']['1']) + '?v=ap&w=1080&h=0'
                        new_html = utils.add_video(val['data'][0]['format_urls']['m3u8'], 'application/x-mpegURL', thumb, val['data'][0]['teaserTitle'])
                        break
            elif node['type'] == 'wxnode_map':
                new_html = utils.add_image(node['map']['imageurl'], node.get('help_text'))
            elif node['type'] == 'wxnode_twitter':
                new_html = utils.add_embed(node['twitter_widget']['embed_text'])
            else:
                logger.warning('handled wxnode type ' + node['type'])
                new_html = '<div id="{}"></div>'.format(matchobj.group(1))
        else:
            logger.warning('unknown wxnode id ' + matchobj.group(1))
            new_html = '<div id="{}"></div>'.format(matchobj.group(1))
        return new_html

    body = re.sub(r'<div id="([^"]+)" />', replace_node, article_json['body'].replace('&QUOT;', '"').replace('\\n', ''))
    item['content_html'] += body
    return item


def get_feed(url, args, site_json, save_debug=False):
    data_json = get_window_data(url, save_debug)
    if save_debug:
        utils.write_file(data_json['dal']['getCMSAssetsUrlConfig'], './debug/feed.json')

    n = 0
    feed_items = []
    for key, val in data_json['dal']['getCMSAssetsUrlConfig'].items():
        if val.get('data') and isinstance(val['data'], list):
            for asset in val['data']:
                asset_url = 'https://www.weather.com' + asset['url']
                if save_debug:
                    logger.debug('getting content for ' + asset_url)
                item = get_content(asset_url, args, site_json, save_debug)
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

