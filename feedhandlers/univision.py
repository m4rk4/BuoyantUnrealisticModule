import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlencode, urlsplit

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)


def resize_image(image, width=1200):
    img_src = image['renditions']['original']['href']
    if image['renditions']['original']['width'] <= 1200:
        return image['renditions']['original']['href']
    return 'https://www.univision.com/proxy/api/cached/picture?href={}&width={}&height={}&ratio_width={}&ratio_height={}&resize_option=Only%20Shrink%20Larger'.format(quote_plus(image['renditions']['original']['href']), image['renditions']['original']['width'], image['renditions']['original']['height'], width, image['renditions']['original']['height'])


def add_image(image, width=1200):
    img_src = resize_image(image, width)
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('credit'):
        captions.append(image['credit'])
    return utils.add_image(img_src, ' | '.join(captions))


def add_video(video):
    video_src = 'https://usprauth.univision.com/api/v3/video-auth/url-signature-token-by-id?mcpid={0}&isLivestream=false&daiToken=BE921757186A0B331740FB8B7C7687B46CBFE8F1DE23B218E3DC0C9C18C62C75&videoId={0}&cmsId=2554571'.format(video['mcpid'])
    return utils.add_video(video_src, 'application/x-mpegURL', video['thumbnailImage'], video['title'])


def get_content(url, args, site_json, save_debug=False):
    # app_state = utils.get_url_json('https://www.univision.com/proxy/api/cached/web-app-state?url=' + quote_plus(url) + '&from=nextjs&userLocation=US&device=desktop')
    # if not app_state:
    #     return None
    # content_data = app_state['data']['page']['data']
    # if save_debug:
    #     utils.write_file(content_data, './debug/debug.json')
    content_json = utils.get_url_json('https://syndicator.univision.com/web-api/content?url=' + quote_plus(url))
    if not content_json:
        return None
    content_data = content_json['data']
    if save_debug:
        utils.write_file(content_data, './debug/debug.json')

    item = {}
    item['id'] = content_data['uid']
    item['url'] = content_data['seo']['canonicalUrl']
    item['title'] = content_data['title']

    dt = datetime.fromisoformat(content_data['publishDate']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if content_data.get('updateDate'):
        dt = datetime.fromisoformat(content_data['updateDate']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['authors'] = [{"name": x['fullName']} for x in content_data['authors']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    else:
        if content_data.get('source'):
            item['author'] = {
                "name": content_data['source']
            }
        else:
            item['author'] = {
                "name": "Univision"
            }
        item['authors'].append(item['author'])

    item['tags'] = []
    if content_data.get('tagHeirachy'):
        item['tags'] = [x['title'] for x in content_data['tagHierarchy']]
    if content_data.get('primaryTag') and content_data['primaryTag']['title'] not in item['tags']:
        item['tags'].append(content_data['primaryTag']['title'])
    if content_data.get('secondaryTags'):
        item['tags'] += [x['name'] for x in content_data['secondaryTags'] if x['name'] not in item['tags']]
    if content_data.get('featuredTags'):
        item['tags'] += [x['title'] for x in content_data['featuredTags'] if x['title'] not in item['tags']]
    if content_data.get('tags'):
        item['tags'] += [x['title'] for x in content_data['tags'] if x['title'] not in item['tags']]
    if content_data.get('keywords'):
        item['tags'] += [x for x in content_data['keywords'] if x not in item['tags']]
    if content_data['seo'].get('keywords'):
        item['tags'] += [x for x in content_data['seo']['keywords'] if x not in item['tags']]

    if content_data.get('image'):
        item['image'] = content_data['image']['renditions']['original']['href']

    item['content_html'] = ''
    if content_data.get('description'):
        item['summary'] = content_data['description']
        item['content_html'] += '<p><em>' + content_data['description'] + '</em></p>'

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if content_data['type'] == 'article':
        if content_data.get('lead'):
            if content_data['lead']['type'] == 'video':
                item['content_html'] += add_video(content_data['lead'])
            elif content_data['lead']['type'] == 'image':
                # TODO: verify
                item['content_html'] += add_image(content_data['lead'])
        elif content_data.get('image'):
            item['content_html'] += add_image(content_data['image'])

        for block in content_data['body']:
            if block['type'] == 'text':
                item['content_html'] += block['value']
            elif block['type'] == 'enhancement':
                if block['objectData']['type'] == "video":
                    item['content_html'] += add_video(block['objectData'])
                elif block['objectData']['type'] == "image":
                    item['content_html'] += add_image(block['objectData'])
                elif block['objectData']['type'] == "slideshow":
                    img_src = block['objectData']['image']['renditions']['original']['href']
                    gallery_url = '{}/gallery?url={}'.format(config.server, quote_plus(block['objectData']['uri']))
                    caption = '<a href="{}" target="_blank">View slideshow</a>'.format(gallery_url)
                    if block['objectData'].get('description'):
                        caption += ': ' + block['objectData']['description']
                    item['content_html'] += utils.add_image(img_src, caption, link=gallery_url)
                elif block['objectData']['type'] == "externalcontent":
                    if block['objectData']['responseData']['provider_name'] == 'YouTube':
                        item['content_html'] += utils.add_embed(block['objectData']['responseData']['_url'])
                    else:
                        logger.warning('unhandled externalcontent provider {} in {}'.format(block['objectData']['responseData']['provider_name'], item['url']))
                elif block['objectData']['type'] == "article":
                    continue
                else:
                    logger.warning('unhandled body enhancement type {} in {}'.format(block['objectData']['type'], item['url']))
            else:
                logger.warning('unhandled body block type {} in {}'.format(block['type'], item['url']))

    elif content_data['type'] == 'slideshow':
        item['_gallery'] = []
        for i, slide in enumerate(content_data['slides']):
            img_src = slide['image']['renditions']['original']['href']
            thumb = resize_image(slide['image'], 800)
            captions = []
            if slide.get('caption'):
                captions.append(slide['caption'])
            if slide.get('credit'):
                captions.append(slide['credit'])
            caption = ' | '.join(captions)
            item['_gallery'].append({"src": img_src, "caption": caption, "thumb": thumb})
            if i == 0:
                item['content_html'] += utils.add_image(thumb, caption, link=img_src)
                item['content_html'] += '<h3><a href="{}/gallery?url={}" target="_blank">View slideshow</a></h3>'.format(config.server, quote_plus(item['url']))
                item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
            else:
                item['content_html'] += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src) + '</div>'
        if i % 2 != 0:
            item['content_html'] += '<div style="flex:1; min-width:360px;">&nbsp;</div>'
        item['content_html'] += '</div>'

    elif content_data['type'] == 'video':
        item['content_html'] = add_video(content_data)
        if 'embed' not in args and 'summary' in item:
            item['content_html'] += '<p>' + item['summary'] + '</p>'

    return item


def get_feed(url, args, site_json, save_debug=False):
    content_json = utils.get_url_json('https://syndicator.univision.com/web-api/content?url=' + quote_plus(url))
    if not content_json:
        return None
    content_data = content_json['data']
    if save_debug:
        utils.write_file(content_data, './debug/feed.json')

    n = 0
    feed_items = []
    for widget in content_data['widgets']:
        for content in widget['contents']:
            if content['type'] == 'vixplayer':
                continue
            if save_debug:
                logger.debug('getting content from ' + content['uri'])
            item = get_content(content['uri'], args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

    feed = utils.init_jsonfeed(args)
    feed['title'] = content_data['seo']['title']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
