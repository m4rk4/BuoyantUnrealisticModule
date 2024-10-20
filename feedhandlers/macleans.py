import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


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
    # print(next_url)
    next_data = utils.get_url_json(next_url, use_proxy=True, use_curl_cffi=True)
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
    next_data = get_next_data(url, site_json)
    if next_data:
        utils.write_file(next_data, './debug/debug.json')
    article_json = next_data['pageProps']['articles'][0]

    split_url = urlsplit(url)

    item = {}
    item['id'] = article_json['id']
    item['url'] = 'https://' + split_url.netloc + article_json['url']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['date']['created']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['date']['modified']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['authors'] = [{"name": re.sub(r'^by ', '', x['name'], flags=re.I)} for x in article_json['authors']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    if article_json.get('term'):
        item['tags'] = []
        for it in article_json['term'].values():
            item['tags'] += [x['name'] for x in it]

    item['content_html'] = ''
    if article_json.get('excerpt'):
        item['summary'] = article_json['excerpt']
        item['content_html'] += '<p><em>' + article_json['excerpt'] + '</em></p>'

    if article_json.get('img'):
        item['image'] = article_json['img']['src']
        captions = []
        if article_json['img'].get('caption'):
            captions.append(article_json['img']['caption'])
        if article_json['img'].get('credit'):
            captions.append(article_json['img']['credit'])
        item['content_html'] += utils.add_image(article_json['img']['src'], ' | '.join(captions))

    def format_blocks(blocks):
        content_html = ''
        for block in blocks:
            if block['name'] == 'core/paragraph':
                if block.get('html'):
                    if block.get('attr') and block['attr'].get('align'):
                        content_html += '<p style="text-align:{}">'.format(block['attr']['align'])
                    else:
                        content_html += '<p>'
                    block_html = block['html']
                    if block.get('attr') and block['attr'].get('dropCap'):
                        if block_html.startswith('<'):
                            i = block_html.find('>')
                        else:
                            i = 0
                        if block['html'][i + 2] == ' ' or block['html'][i + 2].isalnum():
                            n = 1
                        else:
                            n = 2
                        content_html += block['html'][:i+1] + '<span style="float:left; font-size:4em; line-height:0.8em;">' + block['html'][i+1:i+1+n] + '</span>' + block['html'][i+1+n:] + '</p><span style="clear:left;"></span>'
                    else:
                        content_html += block['html'] + '</p>'
            elif block['name'] == 'core/heading':
                if block.get('attr') and block['attr'].get('textAlign'):
                    content_html += '<h2 style="text-align:{}">'.format(block['attr']['textAlign'])
                else:
                    content_html += '<h2>'
                content_html += block['html'] + '</h2>'
            elif block['name'] == 'core/image':
                captions = []
                if block['attr']['img'].get('caption'):
                    captions.append(block['attr']['img']['caption'])
                elif block['attr'].get('caption'):
                    captions.append(block['attr']['caption'])
                if block['attr']['img'].get('credit'):
                    captions.append(block['attr']['img']['credit'])
                if block['attr'].get('credit'):
                    captions.append(block['attr']['credit'])
                content_html += utils.add_image(block['attr']['img']['src'], ' | '.join(captions), link=block.get('href'))
            elif block['name'] == 'core/embed':
                if block['attr'].get('url'):
                    content_html += utils.add_embed(block['attr']['url'])
                else:
                    logger.warning('unhandled core/embed block')
            elif block['name'] == 'core/pullquote':
                quote = re.sub(r'^<p>|</p>$', '', block['html'])
                quote = re.sub(r'\s*<br>\s*', ' ', quote)
                content_html += utils.add_pullquote(quote)
            elif block['name'] == 'core/separator':
                content_html += '<div>&nbsp;</div><hr><div>&nbsp;</div>'
            elif block['name'] == 'core/group':
                content_html += format_blocks(block['blocks'])
            elif block['name'] == 'macleans/module-5050':
                content_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                content_html += '<div style="flex:1; min-width:360px;"><a href="https://{}{}" target="_blank"><img src="{}" style="width:100%;"/></a></div>'.format(split_url.netloc, block['attr']['article']['url'], block['attr']['article']['img']['src'])
                content_html += '<div style="flex:1; min-width:360px; text-align:center;"><h3><a href="https://{}{}" target="_blank">{}</a></h3>{}</div>'.format(split_url.netloc, block['attr']['article']['url'], block['attr']['article']['title'], block['attr']['article']['excerpt'])
                content_html += '</div><div>&nbsp;</div>'
            elif block['name'] == 'core/spacer' or block['name'] == 'macleans/related' or block['name'] == 'macleans/inline-magazine' or block['name'] == 'macleans/newsletter-signup':
                continue
            else:
                logger.warning('unhandled block ' + block['name'])
        return content_html

    item['content_html'] += format_blocks(article_json['body']['blocks'])

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    if len(next_data['pageProps']['articles']) > 1:
        articles = next_data['pageProps']['articles']
    else:
        if next_data['pageProps']['articles'][0]['type'] == 'page' and next_data['pageProps']['articles'][0]['body']['blocks'][0]['name'] == 'core/query':
            articles = next_data['pageProps']['articles'][0]['body']['blocks'][0]['attr']['articles']
        else:
            logger.warning('unknown articles for ' + url)
            return None

    split_url = urlsplit(url)

    n = 0
    feed_items = []
    for article in articles:
        article_url = 'https://' + split_url.netloc + article['url']
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
    # if article_json.get('title'):
    #     feed['title'] = article_json['title'] + ' | ' + split_url.netloc
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
