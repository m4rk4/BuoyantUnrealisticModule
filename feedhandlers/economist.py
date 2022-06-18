import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import unquote_plus, urlsplit

import utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)


def format_blocks(blocks):
    has_dropcap = False
    block_html = ''
    for block in blocks:
        start_tag = ''
        end_tag = ''
        if block['type'] == 'text':
            block_html += block['data']

        elif block['type'] == 'tag':
            if block['name'] == 'figure':
                if block['attribs'].get('itemtype'):
                    if 'ImageObject' in block['attribs']['itemtype']:
                        image = next((it for it in block['children'] if it['name'] == 'img'), None)
                        if image:
                            caption = ''
                            figcaption = next((it for it in block['children'] if it['name'] == 'figcaption'), None)
                            if figcaption:
                                caption += format_blocks(figcaption['children'])
                            block_html += utils.add_image(image['attribs']['src'], caption)
                        else:
                            logger.warning('unhandled figure ImageObject')

                    elif 'MediaObject' in block['attribs']['itemtype']:
                        iframe = next((it for it in block['children'] if it['name'] == 'iframe'), None)
                        if iframe:
                            src = iframe['attribs']['src']
                            if src.startswith('/'):
                                src = 'https://www.economist.com' + src
                                block_html += '<blockquote><b>Embedded content from <a href="{0}">{0}</a></b></blockquote>'.format(src)
                            elif 'economist.com' in src:
                                block_html += '<blockquote><b>Embedded content from <a href="{0}">{0}</a></b></blockquote>'.format(src)
                            elif src.startswith('https://'):
                                block_html += utils.add_embed(src)
                            else:
                                m = re.search(r'https:[\w\./]+', src)
                                if m:
                                    block_html += utils.add_embed(m.group(0))
                                else:
                                    logger.warning('unhandled iframe src ' + src)
                        else:
                            logger.warning('unhandled figure MediaObject')

                    elif 'WPAdBlock' in block['attribs']['itemtype']:
                        continue
                else:
                    # Check if the figure wraps another figure
                    if block.get('children'):
                        figure = next((it for it in block['children'] if it['name'] == 'figure'), None)
                        if figure:
                            block_html += format_blocks([figure])
                    if not block_html:
                        logger.warning('unhandled figure')

            elif block['name'] == 'a':
                start_tag = '<a href="{}">'.format(block['attribs']['href'])
                end_tag = '</a>'

            elif block['name'] == 'span':
                if block.get('attribs') and block['attribs'].get('data-caps'):
                    start_tag = '<span style="float:left; font-size:4em; line-height:0.8em;">'
                    end_tag = '</span>'
                    has_dropcap = True
                else:
                    start_tag = '<span>'
                    end_tag = '</span>'

            elif block['name'] == 'cite':
                start_tag = utils.open_pullquote()
                end_tag = utils.close_pullquote()

            else:
                start_tag = '<{}>'.format(block['name'])
                end_tag = '</{}>'.format(block['name'])

            if start_tag:
                block_html += start_tag + format_blocks(block['children']) + end_tag
        else:
            logger.warning('unhandled block type ' + block['type'])
    if has_dropcap:
        block_html += '<span style="clear:left;">&nbsp;</span>'
    return block_html


def get_content(url, args, save_debug=False):
    page_html = utils.get_url_html(url)
    soup = BeautifulSoup(page_html, 'html.parser')
    next_data = soup.find('script', id='__NEXT_DATA__')
    if not next_data:
        return None
    next_json = json.loads(next_data.string)
    if save_debug:
        utils.write_file(next_json, './debug/debug.json')

    content_json = next_json['props']['pageProps']['content'][0]
    article_json = content_json['_metadata']

    item = {}
    item['id'] = article_json['articleId']
    item['url'] = article_json['url']
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['datePublished'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['dateModified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(article_json['author']))

    item['tags'] = article_json['keywords'].copy()

    if content_json.get('image'):
        if content_json['image'].get('main'):
            item['_image'] = content_json['image']['main']['url']['canonical']
        elif content_json['image'].get('promo'):
            item['_image'] = content_json['image']['promo']['url']['canonical']
    elif article_json.get('imageUrl'):
        item['_image'] = article_json['imageUrl']

    item['summary'] = article_json['description']

    item['content_html'] = ''
    if item.get('_image') and next_json['props']['pageProps']['content'][0]['text'][0].get('name') and next_json['props']['pageProps']['content'][0]['text'][0]['name'] != 'figure':
        if item['_image'].startswith('/'):
            item['_image'] = 'https://www.economist.com' + item['_image']
        item['content_html'] += utils.add_image(item['_image'])
    item['content_html'] += format_blocks(next_json['props']['pageProps']['content'][0]['text'])
    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
