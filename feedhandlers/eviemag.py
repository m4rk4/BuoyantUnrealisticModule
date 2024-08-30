import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    return 'https://www.eviemagazine.com/_next/image?url={}&w={}&q=75'.format(quote_plus(img_src), width)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
        params = ''
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
        params = '?slug=' + paths[-1]
    path += '.json'
    next_url = '{}://{}/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, params)
    # print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        if page_html:
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
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')
    post_json = next_data['pageProps']['post']

    item = {}
    item['id'] = post_json['id']
    item['url'] = url
    item['title'] = post_json['title']

    if post_json.get('_firstPublishedAt'):
        dt = datetime.fromisoformat(post_json['_firstPublishedAt']).astimezone(timezone.utc)
    else:
        dt = datetime.fromisoformat(post_json['publishDate']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if post_json.get('_updatedAt'):
        dt = datetime.fromisoformat(post_json['_updatedAt']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['author'] = {
        "name": post_json['author']['name']
    }

    item['tags'] = []
    if post_json.get('section'):
        item['tags'].append(post_json['section']['title'])
    if post_json.get('topic'):
        item['tags'].append(post_json['topic']['name'])

    item['content_html'] = ''
    if post_json.get('intro'):
        item['summary'] = post_json['intro']
        item['content_html'] += '<p><em>' + post_json['intro'] + '</em></p>'

    if post_json.get('featuredImage'):
        item['_image'] = post_json['featuredImage']['url']
        item['content_html'] += utils.add_image(resize_image(post_json['featuredImage']['url']), post_json['featuredImage'].get('title'), link=post_json['featuredImage']['url'])

    def format_content(content, blocks, dropcap=False):
        content_html = ''
        start_tag = ''
        end_tag = ''
        if content['type'] == 'root' or content['type'] == 'span':
            pass
        elif content['type'] == 'paragraph':
            start_tag = '<p>'
            end_tag = '</p>'
        elif content['type'] == 'heading':
            start_tag = '<h{}>'.format(content['level'])
            end_tag = '</h{}>'.format(content['level'])
        elif content['type'] == 'link':
            start_tag = '<a href="{}">'.format(content['url'])
            end_tag = '</a>'
        elif content['type'] == 'list':
            if content['style'] == 'bulleted':
                start_tag = '<ul>'
                end_tag = '</ul>'
            else:
                start_tag = '<ol>'
                end_tag = '</ol>'
        elif content['type'] == 'listItem':
            start_tag = '<li>'
            end_tag = '</li>'
        elif content['type'] == 'blockquote':
            quote = ''
            for child in content['children']:
                quote += format_content(child, blocks)
            content_html += utils.add_pullquote(quote)
            return content_html
        elif content['type'] == 'block':
            block = next((it for it in blocks if it['id'] == content['item']), None)
            if block['__typename'] == 'ImageRecord':
                content_html += utils.add_image(resize_image(block['image']['url']), block['image'].get('title'), link=block['image']['url'])
            elif block['__typename'] == 'InstagramRecord' or block['__typename'] == 'TiktokRecord' or block['__typename'] == 'TwitterRecord':
                m = re.search(r'^(http.*?)(http|$)', block['url'])
                content_html += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled block type ' + block['__typename'])
            return content_html
        else:
            logger.warning('unhandled content type ' + content['type'])

        if 'marks' in content:
            for mark in content['marks']:
                if mark == 'emphasis':
                    start_tag += '<em>'
                    end_tag = '</em>' + end_tag
                elif mark == 'strong':
                    start_tag += '<strong>'
                    end_tag = '</strong>' + end_tag
                else:
                    logger.warning('unhandled mark ' + mark)

        content_html += start_tag
        if 'children' in content:
            for child in content['children']:
                content_html += format_content(child, blocks)
        elif 'value' in content:
            content_html += content['value']
        content_html += end_tag
        return content_html

    item['content_html'] += format_content(post_json['body']['value']['document'], post_json['body']['blocks'])

    if post_json.get('slides'):
        for slide in post_json['slides']:
            item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:1em; align-items:center; justify-content:center; padding:8px; border:1px solid black; border-radius:10px;">'
            item['content_html'] += '<div style="flex:1; min-width:128px; max-width:256px;"><img src="{}" style="width:100%;"/></div>'.format(slide['image']['url4x5'])
            item['content_html'] += '<div style="flex:2; min-width:256px;"><div style="font-size:1.05em; font-weight:bold">{}</div>'.format(slide['heading'])
            if slide.get('ctaText'):
                if slide.get('ctaLink'):
                    item['content_html'] += '<div><a href="{}" target="_blank">{}</a></div>'.format(slide['ctaLink'], slide['ctaText'])
                else:
                    item['content_html'] += '<div>{}</div>'.format(slide['ctaText'])
            item['content_html'] += '</div></div><div>&nbsp;</div>'

    return item


def get_feed(url, args, site_json, save_debug=False):
    if 'rss.xml' in url:
        # https://www.eviemagazine.com/rss.xml
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    try:
        posts = next_data['pageProps']['trpcState']['json']['queries'][0]['state']['data']['pages'][0]['posts']
    except:
        logger.warning('unable to find next_data posts for' + url)
        return None

    n = 0
    feed_items = []
    for post in posts:
        post_url = 'https://www.eviemagazine.com/post/' + post['slug']
        if save_debug:
            logger.debug('getting content for ' + post_url)
        item = get_content(post_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    if 'topic' in next_data['pageProps']:
        feed['title'] = next_data['pageProps']['topic']['name'] + ' | Evie Magazine'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
