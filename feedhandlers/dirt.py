import re
from datetime import datetime
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index.json'
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
        path += '.json'
        if 'category' in paths:
            path += '?name={}'.format(paths[-1])
        else:
            path += '?year={}&month={}&slug={}'.format(paths[1], paths[2], paths[3])

    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        m = re.search(r'"buildId":"([^"]+)"', page_html)
        if m and m.group(1) != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = m.group(1)
            utils.update_sites(url, site_json)
            next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
            next_data = utils.get_url_json(next_url)
            if not next_data:
                return None
    return next_data


def resize_image(img_src, width=1000):
    return '{}?w={}&q=60&fm=webp'.format(utils.clean_url(img_src), width)


def render_content(node, links):
    content_html = ''
    if node['nodeType'] == 'paragraph':
        content_html += '<p>'
        for content in node['content']:
            content_html += render_content(content, links)
        content_html += '</p>'

    elif node['nodeType'] == 'text':
        if node['value'].startswith('<iframe'):
            m = re.search(r'src="([^"]+)"', node['value'])
            if m:
                content_html += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled iframe content: ' + node['value'])
        else:
            if not node.get('marks') and node['value'].startswith('https://'):
                content_html += utils.add_embed(node['value'])
            else:
                start_tags = ''
                end_tags = ''
                if node.get('marks'):
                    for mark in node['marks']:
                        if mark['type'] == 'underline':
                            start_tags += '<u>'
                            end_tags = '</u>' + end_tags
                        elif mark['type'] == 'bold':
                            start_tags += '<b>'
                            end_tags = '</b>' + end_tags
                        elif mark['type'] == 'italic':
                            start_tags += '<i>'
                            end_tags = '</i>' + end_tags
                        else:
                            logger.warning('unhandle mark type ' + mark['type'])
                content_html += start_tags + node['value'] + end_tags

    elif node['nodeType'].startswith('heading'):
        m = re.search(r'heading-(\d)', node['nodeType'])
        n = int(m.group(1))
        heading = ''
        for content in node['content']:
            heading += render_content(content, links)
        if n == 5 and heading.startswith('“') and heading.endswith('”'):
            content_html += utils.add_pullquote(heading)
        elif n == 6 and (heading.startswith('<figure') or heading.startswith('<div')):
            content_html += heading
        else:
            content_html += '<h{0}>{1}</h{0}>'.format(min(3, n), heading)

    elif node['nodeType'] == 'hyperlink':
        content_html += '<a href="{}">'.format(node['data']['uri'])
        for content in node['content']:
            content_html += render_content(content, links)
        content_html += '</a>'

    elif node['nodeType'] == 'hr':
        content_html += '<hr/>'

    elif node['nodeType'] == 'blockquote':
        quote = ''
        for content in node['content']:
            quote += render_content(content, links)
        content_html += utils.add_blockquote(quote)

    elif node['nodeType'] == 'unordered-list':
        content_html += '<ul>'
        for content in node['content']:
            content_html += render_content(content, links)
        content_html += '</ul>'

    elif node['nodeType'] == 'ordered-list':
        content_html += '<ol>'
        for content in node['content']:
            content_html += render_content(content, links)
        content_html += '</ol>'

    elif node['nodeType'] == 'list-item':
        content_html += '<li>'
        for content in node['content']:
            content_html += render_content(content, links)
        content_html += '</li>'

    elif node['nodeType'] == 'embedded-asset-block':
        if node['data']['target']['fields'].get('file') and node['data']['target']['fields']['file']['contentType'].startswith('image/'):
            if node['data']['target']['fields'].get('description'):
                caption = node['data']['target']['fields']['description']
            elif node['data']['target']['fields'].get('title') and node['data']['target']['fields']['title'] not in node['data']['target']['fields']['file']['fileName']:
                caption = node['data']['target']['fields']['title']
            else:
                caption = ''
            content_html += utils.add_image(resize_image('https:' + node['data']['target']['fields']['file']['url']), caption)
        else:
            logger.warning('unhandled embedded-asset-block')

    elif node['nodeType'] == 'embedded-entry-inline' and node['data'].get('target'):
        if node['data']['target']['fields'].get('url'):
            content_html += '<a href="{}">{}</a>'.format(node['data']['target']['fields']['url'], node['data']['target']['fields']['name'])
        elif node['data']['target']['fields'].get('shortCode'):
            content_html += '<a href="https://robinhood.com/us/en/stocks/{}/">{}</a>'.format(node['data']['target']['fields']['shortCode'], node['data']['target']['fields']['name'])
        else:
            content_html += node['data']['target']['fields']['name']
        if node['data']['target']['fields'].get('showLiveData') and node['data']['target']['fields']['showLiveData'] == True and node['data']['target']['fields'].get('shortCode'):
            data_json = utils.get_url_json('https://sherwood.news/api/public/fetch_instrument/?symbol=' + node['data']['target']['fields']['shortCode'])
            if data_json:
                data_json = utils.get_url_json('https://sherwood.news/api/public/fetch_instrument_quote/?instrumentUrl=' + data_json['instrument']['url'])
                if data_json:
                    diff = 100 * (float(data_json['quote']['last_trade_price']) - float(data_json['quote']['previous_close'])) / float(data_json['quote']['previous_close'])
                    content_html += ' <span style="font-size:0.8em; line-height:inherit; padding:3px 5px 1px; border:1px solid rgb(6,187,0); color:green;">{} ${:.2f} ({:.2f}%)</span>'.format(data_json['quote']['symbol'], float(data_json['quote']['last_trade_price']), diff)

    elif node['nodeType'] == 'embedded-entry-block':
        if not (node['data']['target']['fields'].get('name') and re.search(r'newsletter signup', node['data']['target']['fields']['name'], flags=re.I)):
            logger.warning('unhandled embedded-entry-block')

    else:
        logger.warning('unhandled nodeType ' + node['nodeType'])

    return content_html


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    #utils.write_file(next_data, './debug/next.json')

    post_json = next_data['pageProps']['post']
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = next_data['pageProps']['id']
    item['url'] = url
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['metadata']['sys']['createdAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['metadata']['sys']['updatedAt'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": post_json['author']['fields']['name']}

    item['tags'] = []
    if post_json.get('category'):
        item['tags'].append(post_json['category']['fields']['name'])
    if post_json['metadata']['fields'].get('seoKeywords'):
        item['tags'] += post_json['metadata']['fields']['seoKeywords'].copy()
    if not item.get('tags'):
        del item['tags']

    if post_json['metadata']['fields'].get('seoDescription'):
        item['summary'] = post_json['metadata']['fields']['seoDescription']

    item['content_html'] = ''
    if post_json.get('subject'):
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['subject'])
        if not item.get('summary'):
            item['summary'] = post_json['subject']

    if post_json.get('image'):
        item['_image'] = 'https:' + post_json['image']['fields']['file']['url']
        item['content_html'] += utils.add_image(resize_image(item['_image']), post_json['image']['fields'].get('description'))

    if post_json.get('text'):
        for content in post_json['text']['content']:
            item['content_html'] += render_content(content, None)
    else:
        item['content_html'] = '<h2>A subscription is required to read this article.</h2>' + item['content_html']
        for content in post_json['excerpt']['content']:
            item['content_html'] += render_content(content, None)
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) > 0:
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        if save_debug:
            utils.write_file(next_data, './debug/feed.json')
        posts = next_data['pageProps']['posts']
        feed_title = 'Dirt | ' + paths[-1].title()
    else:
        api_json = utils.get_url_json('https://dirt.fyi/api/static/posts')
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')
        posts = api_json['posts']
        feed_title = 'Dirt'

    n = 0
    feed_items = []
    feed = utils.init_jsonfeed(args)
    feed['title'] = feed_title
    for post in posts:
        d = post['fields']['publishedOn'].split('-')
        url = 'https://dirt.fyi/article/{}/{}/{}'.format(d[0], d[1], post['fields']['slug'])
        if save_debug:
            logger.debug('getting content from ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
