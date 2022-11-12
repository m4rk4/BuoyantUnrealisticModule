import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_next_data(url):
    page_html = utils.get_url_html(url)
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + url)
        return None
    return json.loads(el.string)


def resize_image(image, width=1000):
    if image.get('hips_url'):
        img_src = image['hips_url']
    elif image.get('aws_url'):
        img_src = 'https://hips.hearstapps.com/' + image['aws_url'].replace('https://', '')
    else:
        img_src = 'https://hips.hearstapps.com/hmg-prod{}'.format(image['pathname'])
    return '{}?resize={}:*'.format(img_src, width)


def add_image(image, attribs=None):
    captions = []
    if attribs and attribs.get('caption'):
        captions.append(attribs['caption'])
    if image.get('metadata') and image['metadata'].get('caption'):
        captions.append(image['metadata']['caption'])
    if image['image_metadata'].get('photo_credit'):
        captions.append(image['image_metadata']['photo_credit'])
    if image.get('source'):
        captions.append(image['source']['title'])
    if image.get('metadata') and image['metadata'].get('custom_tag'):
        heading = image['metadata']['custom_tag']
    else:
        heading = ''
    return utils.add_image(resize_image(image), ' | '.join(captions), heading=heading)


def format_block(block, media, netloc):
    block_html = ''
    start_tag = ''
    end_tag = ''
    dropcap = False
    if block['type'] == 'text':
        return block['data']
    elif block['type'] == 'tag':
        if block['name'] == 'a':
            start_tag = '<a href="{}">'.format(block['attribs']['href'])
            end_tag = '</a>'
        elif block['name'] == 'p':
            if block.get('attribs') and block['attribs'].get('class') and block['attribs']['class'] == 'body-dropcap':
                dropcap = True
                start_tag = '<p>'
                end_tag = '</p><span style="clear:left;"></span>'
            else:
                start_tag = '<p>'
                end_tag = '</p>'
        elif block['name'] == 'image':
            image = next((it for it in media if it['id'] == block['attribs']['mediaid']), None)
            return add_image(image, block['attribs'])
        elif block['name'] == 'gallery':
            for slide in block['response']['parsedSlides']:
                if slide['__typename'] == 'Product':
                    block_html += '<table style="width:100%"><tr><td style="width:128px;"><img src="{}" style="width:128px;"/></td><td><b>{}</b><br/><a href="{}">${} at {}</a></td></tr></table>'.format(resize_image(slide['image'], 128), slide['name'], slide['retailer']['url'], slide['retailer']['price'], slide['retailer']['display_name'])
                elif slide['__typename'] == 'Image':
                    block_html += add_image(slide)
                else:
                    logger.warning('unhandled slide type ' + slide['__typename'])
        elif block['name'] == 'composite':
            for image in block['response']['media']:
                block_html += add_image(image)
        elif block['name'] == 'loop':
            return utils.add_video(block['attribs']['src'], 'video/mp4', '', block['attribs']['caption'])
        elif block['name'] == 'youtube' or block['name'] == 'twitter' or block['name'] == 'instagram':
            for blk in block['children']:
                block_html += format_block(blk, media, netloc)
            return utils.add_embed(block_html)
        elif block['name'] == 'blockquote':
            for blk in block['children']:
                block_html += format_block(blk, media, netloc)
            return utils.add_blockquote(block_html, False)
        elif block['name'] == 'pullquote':
            for blk in block['children']:
                block_html += format_block(blk, media, netloc)
            return utils.add_pullquote(block_html)
        elif block['name'] == 'br' or block['name'] == 'hr':
            return '<{}/>'.format(block['name'])
        elif block['name'] == 'editoriallinks':
            block_html += '<h3>{}</h3><ul>'.format(block['response']['bonsaiLinkset']['title'])
            for it in block['response']['bonsaiLinkset']['links']:
                url = 'https://{}/{}'.format(netloc, it['content']['section']['slug'])
                if it['content'].get('subsection'):
                    url += '/{}'.format(it['content']['subsection']['slug'])
                url += '/a{}/{}'.format(it['content']['display_id'], it['content']['slug'])
                block_html += '<li><a href="{}">{}</a></li>'.format(url, it['content']['title'])
            block_html += '</ul>'
            return block_html
        elif block['name'] == 'watch-next':
            return ''
        else:
            print(block['name'])
            start_tag = '<{}>'.format(block['name'])
            end_tag = '</{}>'.format(block['name'])

    children_html = ''
    if block.get('children'):
        for blk in block['children']:
            children_html += format_block(blk, media, netloc)

    block_html += start_tag
    if dropcap:
        if children_html.startswith('<'):
            block_html += re.sub(r'^(<[^>]+>)(.)', r'\1<span style="float:left; font-size:4em; line-height:0.8em;">\2</span>', children_html)
        elif children_html.startswith('“'):
            block_html += '<span style="float:left; font-size:4em; line-height:0.8em;">{}</span>{}'.format(children_html[:2], children_html[2:])
        else:
            block_html += '<span style="float:left; font-size:4em; line-height:0.8em;">{}</span>{}'.format(children_html[0], children_html[1:])
    else:
        block_html += children_html
    block_html += end_tag
    return block_html


def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    next_data = get_next_data(url)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    content_json = next_data['props']['pageProps']['data']['content'][0]

    item = {}
    item['id'] = content_json['id']
    item['url'] = next_data['HRST']['article']['canonicalUrl']

    if '</' in content_json['metadata']['index_title']:
        item['title'] = BeautifulSoup(content_json['metadata']['index_title'], 'html.parser').get_text()
    else:
        item['title'] = content_json['metadata']['index_title']

    dt = datetime.fromisoformat(content_json['originally_published_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(content_json['updated_at'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in content_json['authors']:
        authors.append(it['profile']['display_name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    # Media roles:
    # SLIDE: 1,
    # SOCIAL: 2,
    # LEDE: 3,
    # BODY_MEDIA: 4,
    # MARQUEE: 5,
    # SPONSORED_MARQUEE: 6,
    # PREVIEW: 7,
    # ASSOCIATED_IMAGE: 8,
    # ASSOCIATED_VIDEO: 9,
    # CUSTOM_PREVIEW_IMAGE: 10,
    # CONTENT_TESTING: 11,
    # INDEX: 12,
    # SECTION_VIDEO: 13,
    # VIDEO_HUB: 14,
    # MEDIA_ROLE_PINTEREST: 16,
    # OFF_PLATFORM: 16,
    # CUSTOM_PROMO: 17,
    # FEED: 18,
    # GHOST_SLIDE: 19,
    # SPOTLIGHT_MARQUEE: 20,
    # EMBEDDED_CONTENT: 21
    if content_json.get('media'):
        image = next((it for it in content_json['media'] if it['role'] == 2), None)
        if image:
            item['_image'] = resize_image(image)
        else:
            item['_image'] = resize_image(content_json['media'][0])

    item['summary'] = content_json['metadata']['seo_meta_description']

    item['content_html'] = ''
    if content_json['metadata'].get('dek'):
        item['content_html'] = content_json['metadata']['dek']
        item['content_html'] = re.sub(r'^<p>', '<p><em>', item['content_html'])
        item['content_html'] = re.sub(r'</p>$', '</em></p>', item['content_html'])

    media = next((it for it in content_json['media'] if it['role'] == 3), None)
    if media:
        if media['media_type'] == 'image':
            item['content_html'] += add_image(image)
        elif media['media_type'] == 'file':
            # loop video
            image = next((it for it in content_json['media'] if (it['media_type'] == 'image' and it['role'] == 3)), None)
            if image:
                poster = resize_image(image)
            else:
                poster = ''
            item['content_html'] += utils.add_video('https://media.hearstapps.com/loop/video/{}'.format(media['filename']), 'video/mp4', poster)
        elif media['media_type'] == 'video':
            captions = []
            if media.get('title'):
                captions.append(media['title'])
            if media.get('credit'):
                captions.append(media['credit'])
            source = utils.closest_dict(media['transcodings'], 'height', 480)
            item['content_html'] += utils.add_video(source['full_url'], 'video/mp4', media['croppedPreviewImage'])

    for block in next_data['props']['pageProps']['bodyDom']['children']:
        item['content_html'] += format_block(block, content_json['media'], split_url.netloc)

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(args, save_debug=False):
    split_url = urlsplit(args['url'])
    next_data = get_next_data(args['url'])
    if not next_data:
        return None

    urls = []
    for feedinfo in next_data['props']['pageProps']['data']['feedInfo']:
        for block in feedinfo['blocks']:
            for feed in block['feeds']:
                for res in feed['resources']:
                    url = 'https://{}/{}'.format(split_url.netloc, res['section']['slug'])
                    if res.get('subsection'):
                        url += '/{}'.format(res['subsection']['slug'])
                    url += '/a{}/{}'.format(res['display_id'], res['slug'])
                    urls.append(url)

    n = 0
    feed_items = []
    for url in urls:
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    # if feed_title:
    #     feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed