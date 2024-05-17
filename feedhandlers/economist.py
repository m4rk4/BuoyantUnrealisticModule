import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus

import config, utils
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
    if '/infographics.economist.com/' in url:
        item = {}
        item['_image'] = '{}/screenshot?url={}&locator=%23g-index-box'.format(config.server, quote_plus(url))
        item['content_html'] = utils.add_image(item['_image'], link=url)
        return item

    page_html = utils.get_url_html(url)
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    soup = BeautifulSoup(page_html, 'html.parser')
    next_data = soup.find('script', id='__NEXT_DATA__')
    if not next_data:
        return None
    next_json = json.loads(next_data.string)
    if save_debug:
        utils.write_file(next_json, './debug/debug.json')

    if next_json['props']['pageProps'].get('walled') and next_json['props']['pageProps']['walled'] == True:
        logger.debug('article is paywalled, trying to find bing cached version')
        bing_html = utils.get_bing_cache(url, '', save_debug)
        if bing_html:
            if save_debug:
                utils.write_file(bing_html, './debug/bing.html')
            soup = BeautifulSoup(bing_html, 'html.parser')
            next_data = soup.find('script', id='__NEXT_DATA__')
            if next_data:
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
        elif 'Article' in next_json['props']['pageProps']['content']['type']:
            content_parts = None
            content_json = next_json['props']['pageProps']['content']
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

    item['tags'] = []
    item['author'] = {}
    if content_json.get('_metadata'):
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(content_json['_metadata']['author']))
        item['tags'] += content_json['_metadata']['keywords'].copy()
        if content_json['_metadata'].get('imageUrl'):
            item['_image'] = content_json['_metadata']['imageUrl']
    elif content_json.get('byline'):
        item['author']['name'] = content_json['byline']
    else:
        item['author']['name'] = 'The Economist'

    if content_json.get('articleSection') and content_json['articleSection']['__typename'] == 'Taxonomies' and content_json['articleSection'].get('internal'):
        for it in content_json['articleSection']['internal']:
            if it['headline'] not in item['tags']:
                item['tags'].append(it['headline'])
    if not item.get('tags'):
        del item['tags']

    caption = ''
    if content_json.get('leadComponent') and content_json['leadComponent']['type'] == 'IMAGE':
        item['_image'] = content_json['leadComponent']['url']
        captions = []
        if content_json['leadComponent'].get('caption') and content_json['leadComponent']['caption'].get('textHtml'):
            caption.append(content_json['leadComponent']['caption']['textHtml'])
        if content_json['leadComponent'].get('credit'):
            caption.append(content_json['leadComponent']['credit'])
        caption = ' | '.join(captions)
    elif content_json.get('image'):
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
    if content_json.get('description'):
        item['content_html'] += '<p><em>{}</em></p>'.format(content_json['description'])

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
        if next_json['props']['pageProps'].get('walled') and next_json['props']['pageProps']['walled'] == True and bing_html:
            item['content_html'] += content_from_html(bing_html)
        else:
            item['content_html'] += format_blocks(content_json['text'])
    return item


def content_from_html(content_html):
    soup = BeautifulSoup(content_html, 'lxml')
    body = soup.find('section', attrs={"data-body-id": True})
    if not body :
        return None

    for el in body.find_all('div', class_=re.compile(r'css-'), recursive=False):
        el.unwrap()

    for el in body.find_all('style'):
        el.decompose()

    for el in body.find_all(class_=re.compile(r'adComponent')):
        el.decompose()

    for el in body.find_all('p', attrs={"data-component": "paragraph"}):
        el.attrs = {}

    for el in body.find_all('figure'):
        new_html = ''
        if el.find('audio'):
            if el.figcaption:
                caption = el.figcaption.get_text()
            else:
                caption = 'Listen to this story.'
            new_html = '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">{2}</a></span></div><div>&nbsp;</div>'.format(el.audio['src'], config.server, caption)
        elif el.find('img'):
            if el.img.get('srcset'):
                img_src = utils.image_from_srcset(el.img['srcset'], 1000)
            else:
                img_src = el.img['src']
            if el.figcaption:
                caption = el.figcaption.get_text()
            else:
                caption = ''
            new_html = utils.add_image(img_src, caption)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el.parent and el.parent.name == 'div':
                el.parent.replace_with(new_el)
            else:
                el.replace_with(new_el)
    return body.decode_contents()


def get_feed(url, args, site_json, save_debug=False):
    # https://www.economist.com/rss
    return rss.get_feed(url, args, site_json, save_debug, get_content)
