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
                            figcaption = next((it for it in block['children'] if it['name'] == 'figcaption'), None)
                            if figcaption:
                                caption += format_blocks(figcaption['children'])
                            elif image['attribs'].get('alt'):
                                caption = image['attribs']['alt']
                            else:
                                caption = ''
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


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    soup = BeautifulSoup(page_html, 'html.parser')
    next_data = soup.find('script', id='__NEXT_DATA__')
    if not next_data:
        return None
    next_json = json.loads(next_data.string)
    if save_debug:
        utils.write_file(next_json, './debug/debug.json')

    item = {}

    if isinstance(next_json['props']['pageProps']['content'], list):
        content_parts = None
        content_json = next_json['props']['pageProps']['content'][0]
        item['id'] = content_json['id']
        item['url'] = content_json['url']['canonical']
    else:
        if 'CollectionPage' in next_json['props']['pageProps']['content']['type']:
            content_parts = next_json['props']['pageProps']['content']['hasPart']['parts'][0]['hasPart']['parts']
            content_json = content_parts[0]
            item['id'] = next_json['props']['pageProps']['content']['id']
            item['url'] = next_json['props']['pageProps']['pageUrl']
        else:
            logger.warning('unhandled content type {} in {}'.format(next_json['props']['pageProps']['content']['type'], url))

    item['title'] = content_json['headline']

    dt = datetime.fromisoformat(content_json['datePublished'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if '/the-world-this-week/' in item['url']:
        item['title'] = 'The World this Week: {} ({})'.format(content_json['headline'], utils.format_display_date(dt, False))

    dt = datetime.fromisoformat(content_json['dateModified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if content_json.get('_metadata'):
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(content_json['_metadata']['author']))
        item['tags'] = content_json['_metadata']['keywords'].copy()
        if content_json['_metadata'].get('imageUrl'):
            item['_image'] = content_json['_metadata']['imageUrl']
    elif content_json.get('byline'):
        item['author']['name'] = content_json['byline']
    else:
        item['author']['name'] = 'The Economist'

    caption = ''
    if content_json.get('image'):
        if content_json['image'].get('main'):
            item['_image'] = content_json['image']['main']['url']['canonical']
            if content_json['image']['main'].get('description'):
                caption = content_json['image']['main']['description']
        elif content_json['image'].get('promo'):
            item['_image'] = content_json['image']['promo']['url']['canonical']
            if content_json['image']['promo'].get('description'):
                caption = content_json['image']['promo']['description']

    if content_json.get('description'):
        item['summary'] = content_json['description']

    item['content_html'] = ''
    if not content_json.get('text') or (item.get('_image') and content_json['text'][0].get('name') and content_json['text'][0]['name'] != 'figure'):
        if item['_image'].startswith('/'):
            item['_image'] = 'https://www.economist.com' + item['_image']
        item['content_html'] += utils.add_image(item['_image'], caption)

    if content_parts:
        for i, content_json in enumerate(content_parts):
            if 'Article' in content_json['type']:
                if i > 0:
                    item['content_html'] += '<hr/><h2>{}</h2>'.format(content_json['headline'])
                    if content_json.get('image') and content_json['image'].get('main'):
                        if content_json['image']['main'].get('description'):
                            caption = content_json['image']['main']['description']
                        else:
                            caption = ''
                        item['content_html'] += utils.add_image(content_json['image']['main']['url']['canonical'], caption)
                item['content_html'] += format_blocks(content_json['text'])
                if content_json.get('image') and content_json['image'].get('inline'):
                    for image in content_json['image']['inline']:
                        if image.get('description'):
                            caption = image['description']
                        else:
                            caption = ''
                        item['content_html'] += utils.add_image(image['url']['canonical'], caption)
            elif 'Quotation' in content_json['type']:
                item['content_html'] += '<hr/>' + utils.add_pullquote(content_json['headline'], content_json['byline'])
            else:
                logger.warning('unhandled content type {} in {}'.format(content_json['type'], item['url']))
    elif content_json.get('text'):
        item['content_html'] += format_blocks(content_json['text'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.economist.com/rss
    return rss.get_feed(url, args, site_json, save_debug, get_content)


def test_handler():
    feeds = ['https://www.economist.com/the-world-this-week/rss.xml',
             'https://www.economist.com/briefing/rss.xml',
             'https://www.economist.com/special-report/rss.xml']
    for url in feeds:
        get_feed({"url": url}, True)
