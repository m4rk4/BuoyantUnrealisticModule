from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import brightcove

import logging

logger = logging.getLogger(__name__)


def render_content(blocks):
    content_html = ''
    for block in blocks:
        if block['type'] == 'text':
            content_html += block['text']
        elif block['type'] == 'paragraph':
            content_html += '<p>' + render_content(block['children']) + '</p>'
        elif block['type'] == 'subHeading':
            content_html += '<h{0}>{1}</h{0}>'.format(block['size'], render_content(block['children']))
        elif block['type'] == 'link':
            content_html += '<a href="{}">'.format(block['props']['href']) + render_content(block['children']) + '</a>'
        elif block['type'] == 'italic':
            content_html += '<em>' + render_content(block['children']) + '</em>'
        elif block['type'] == 'bold':
            content_html += '<strong>' + render_content(block['children']) + '</strong>'
        elif block['type'] == 'quote':
            content_html += utils.add_pullquote(render_content(block['children']))
        elif block['type'] == 'captionedImage':
            captions = []
            if block.get('caption'):
                captions.append(block['caption'])
            if block.get('credit'):
                captions.append(block['credit'])
            img_src = block['src'] + '?width=1200&type=webp'
            content_html += utils.add_image(img_src, ' | '.join(captions))
        elif block['type'] == 'tweet':
            content_html += utils.add_embed('https://twitter.com/__/status/{}'.format(block['id']))
        elif block['type'] == 'youtubeVideo':
            content_html += utils.add_embed(block['src'])
        elif block['type'] == 'brightcoveVideo':
            # https://edge.api.brightcove.com/playback/v1/accounts/5377161796001/videos/6338738703112
            bc_args = {
                "data-key": "BCpkADawqM1UIU4favtR1Jj4rqM0ZAkYwMEbgN9bsEpJ2150CdxJmRIG8jK-Up_9w4w37x3tP1AsoO_MZhD_XoAGkdKWxymaaw4OHuhPn_lEJczODTm3AO7S08gLFPnLnb-FcKJwXhbxCQ10",
                "data-account": 5377161796001,
                "data-video-id": block['id'],
                "embed": True
            }
            bc_item = brightcove.get_content('', bc_args, {"module": "brightcove"}, False)
            if bc_item:
                content_html += bc_item['content_html']
        elif block['type'] == 'unsupported' and block['html'].strip() == '':
            continue
        else:
            logger.warning('unhandled content type ' + block['type'])
    return content_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    api_url = 'https://api.i24news.tv/v2/{}/contents/{}'.format(paths[0], paths[-1])
    content_json = utils.get_url_json(api_url)
    if not content_json:
        return None
    if save_debug:
        utils.write_file(content_json, './debug/debug.json')

    item = {}
    item['id'] = content_json['id']
    item['url'] = content_json['frontendUrl']
    item['title'] = content_json['title']

    dt = datetime.fromisoformat(content_json['publishedAt']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(content_json['updatedAt']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": content_json['author']['name']}

    item['tags'] = []
    item['tags'].append(content_json['category']['name'])
    for it in content_json['tags']:
        item['tags'].append(it['name'])

    item['content_html'] = ''
    if content_json.get('excerpt'):
        item['summary'] = content_json['excerpt']
        item['content_html'] += '<p><em>{}</em></p>'.format(content_json['excerpt'])

    if content_json.get('image'):
        item['_image'] = content_json['image']['href']
        captions = []
        if content_json.get('coverCaption'):
            captions.append(content_json['coverCaption'])
        if content_json['image'].get('credit'):
            captions.append(content_json['image']['credit'])
        img_src = content_json['image']['href'] + '?width=1200&type=webp'
        item['content_html'] += utils.add_image(img_src, ' | '.join(captions))

    item['content_html'] += render_content(content_json['parsedBody'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 1:
        api_url = 'https://api.i24news.tv/v2/{}/contents?home=1&sort=-publishedAt&inSlider=0&page=1&limit=10&countable=1'.format(paths[0])
    if 'tags' in paths:
        api_url = 'https://api.i24news.tv/v2/en/contents/search?tags={}&page=1&limit=10&countable=1'.format(paths[-1])
    else:
        contents_json = utils.get_url_json('https://api.i24news.tv/v2/en/categories/featured')
        if contents_json:
            if save_debug:
                utils.write_file(contents_json, './debug/categories.json')
            for feature in contents_json:
                category = None
                if feature['slug'] == paths[-1]:
                    category = feature
                else:
                    content = next((it for it in feature['contents'] if it['category']['slug'] == paths[-1]), None)
                    if content:
                        category = content['category']
                if category:
                    if paths[-2] == 'news':
                        break
                    elif category.get('parent') and category['parent']['slug'] == paths[-2]:
                        break
        else:
            category = None
        if not category:
            logger.warning('unable to determine category for ' + url)
            return None
        api_url = 'https://api.i24news.tv/v2/en/contents?category={}&page=1&limit=10&countable=1&inSlider=0'.format(category['id'])
    print(api_url)
    contents_json = utils.get_url_json(api_url)
    if not contents_json:
        return None
    if save_debug:
        utils.write_file(contents_json, './debug/feed.json')

    n = 0
    feed_items = []
    for content in contents_json:
        if save_debug:
            logger.debug('getting content for ' + content['frontendUrl'])
        item = get_content(content['frontendUrl'], args, site_json, save_debug)
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