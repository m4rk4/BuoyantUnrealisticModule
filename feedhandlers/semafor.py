import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_next_data(url):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + url)
        return None
    #utils.write_file(el.string, './debug/debug.txt')
    return json.loads(el.string)


def convert_unicode(matchobj):
    try:
        return matchobj.group(0).encode('latin1').decode('utf-8')
    except:
        return matchobj.group(0)


def resize_image(image, width=1200):
    img_src = re.sub('^image-', r'https://img.semafor.com/', image['asset']['_ref'])
    img_src = re.sub('-(\w+)$', r'.\1', img_src)
    return img_src + '?w={}&q=75&auto=format'.format(width)


def add_image(image, func_resize_image):
    img_src = func_resize_image(image)
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('attribution'):
        captions.append(image['attribution'])
    elif image.get('credit'):
        captions.append(image['credit'])
    elif image.get('rteCredit'):
        credit = ''
        for blk in image['rteCredit']:
            credit += render_block(blk)
        captions.append(re.sub(r'^<p>(.*)</p>$', r'\1', credit, flags=re.S))
    return utils.add_image(img_src, ' | '.join(captions))


def render_block(block):
    content_html = ''
    footnotes = []
    if block['_type'] == 'block':
        if block.get('style'):
            if block['style'] == 'normal':
                if block.get('listItem'):
                    if block['listItem'] == 'bullet':
                        block_start_tag = '<ul><li>'
                        block_end_tag = '</li></ul>'
                    else:
                        block_start_tag = '<ol start="{}"><li>'.format(block['level'])
                        block_end_tag = '</li></ol>'
                else:
                    block_start_tag = '<p>'
                    block_end_tag = '</p>'
            else:
                block_start_tag = '<{}>'.format(block['style'])
                block_end_tag = '</{}>'.format(block['style'])
        else:
            block_start_tag = '<p>'
            block_end_tag = '</p>'
        content_html += block_start_tag

        for child in block['children']:
            start_tag = ''
            end_tag = ''
            if child['_type'] == 'span':
                text = re.sub('[^\x00-\x7F]+', convert_unicode, child['text'])
            elif child['_type'] == 'footnote':
                start_tag = '<small><sup>'
                end_tag = '</sup></small>'
                text = child['number']
                footnotes.append(child.copy())
            else:
                logger.warning('unhandled block child type ' + child['_type'])
            if child.get('marks'):
                for m in child['marks']:
                    #print(m)
                    mark = next((it for it in block['markDefs'] if it['_key'] == m), None)
                    if mark:
                        if mark['_type'] == 'link':
                            if mark.get('href'):
                                start_tag += '<a href="{}">'.format(mark['href'])
                            elif '@' in text:
                                start_tag += '<a href="mailto:{}">'.format(text)
                            else:
                                logger.warning('unhandled mark link')
                            end_tag = '</a>' + end_tag
                        else:
                            logger.warning('unhandled markDef type ' + mark['_type'])
                    else:
                        start_tag += '<{}>'.format(m)
                        end_tag = '</{}>'.format(m) + end_tag
            content_html += '{}{}{}'.format(start_tag, text, end_tag)

        content_html += block_end_tag

    elif block['_type'] == 'imageEmbed' or block['_type'] == 'insetImage':
        if block.get('image'):
            image = block['image']
        elif block.get('imageEmbed'):
            image = block['imageEmbed']
        else:
            image = None
            logger.warning('unhandled ' + block['_type'])
        if image:
            content_html += add_image(image, resize_image)

    elif block['_type'] == 'insetImageSlideshow':
        for image in block['slideshowImages']:
            content_html += add_image(image, resize_image)

    elif block['_type'] == 'pullQuote':
        content_html += utils.add_pullquote(block['text'])

    elif block['_type'] == 'youtube' or block['_type'] == 'twitter':
        content_html += utils.add_embed(block['url'])

    elif block['_type'] == 'embedBlock':
        soup = BeautifulSoup(block['html'], 'html.parser')
        if soup.iframe:
            content_html += utils.add_embed(soup.iframe['src'])
        else:
            logger.warning('unhandled embedBlock content')

    elif block['_type'] == 'divider':
        if block.get('variant') and block['variant'] == 'dotted-rule':
            content_html += '<hr style="border-top:1px dashed black;" />'
        else:
            content_html += '<hr/>'

    elif block['_type'] == 'ad' or block['_type'] == 'relatedStories' or block['_type'] == 'donateButton':
        pass

    else:
        logger.warning('unhandled block type ' + block['_type'])

    if footnotes:
        content_html += '<table style="margin-left:1em; font-size:0.8em;">'
        for footnote in footnotes:
            footnote_html = ''
            for blk in footnote['content']:
                footnote_html += render_block(blk)
            content_html += '<tr><td style="vertical-align:top;">{}</td><td style="vertical-align:top;">{}</td></tr>'.format(footnote['number'], re.sub(r'^<p>(.*)</p>$', r'\1', footnote_html, flags=re.S))
        content_html += '</table><div>&nbsp;</div>'
    return content_html


def get_content(url, args, site_json, save_debug):
    next_data = get_next_data(url)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')
    article_json = next_data['props']['pageProps']['article']

    item = {}
    item['id'] = article_json['_id']
    item['url'] = 'https://www.semafor.com' + article_json['slug']
    item['title'] = re.sub('[^\x00-\x7F]+', convert_unicode, article_json['headline'])

    dt = datetime.fromisoformat(article_json['_createdAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('lastPublished'):
        dt = datetime.fromisoformat(article_json['lastPublished'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()

    if article_json.get('author'):
        item['author'] = {"name": article_json['author']['name']}
    elif article_json.get('authors'):
        authors = []
        for it in article_json['authors']:
            authors.append(it['name'])
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    # TODO: tags
    item['tags'] = []
    if article_json.get('vertical'):
        item['tags'].append(article_json['vertical'])
    if article_json.get('location'):
        item['tags'].append(article_json['location'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''
    if article_json.get('ledePhoto'):
        item['_image'] = article_json['ledePhoto']
        item['content_html'] += add_image(article_json['ledePhoto'], resize_image)

    if article_json.get('seoDescription'):
        item['summary'] = article_json['seoDescription']

    if article_json.get('intro') and article_json['intro'].get('body'):
        for block in article_json['intro']['body']:
            item['content_html'] += render_block(block)

    if article_json.get('semaforms'):
        for i, semaform in enumerate(article_json['semaforms']):
            if i > 0:
                item['content_html'] += '<hr/>'
            if semaform.get('title'):
                item['content_html'] += '<h2>{}</h2>'.format(semaform['title'])
            if semaform['_type'] == 'scoop':
                for block in semaform['scoop']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'generaform':
                for block in semaform['body']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'reportersTake':
                item['content_html'] += '<h2>{}\'s View</h2>'.format(semaform['author']['shortName'])
                for block in semaform['thescoop']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'knowMore':
                item['content_html'] += '<h2>Know More</h2>'
                for block in semaform['knowMore']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'theViewFrom':
                item['content_html'] += '<h2>The View from {}</h2>'.format(semaform['where'])
                for block in semaform['theViewFrom']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'roomForDisagreement':
                item['content_html'] += '<h2>Room For Disagreement</h2>'
                for block in semaform['roomForDisagreement']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'furtherReading':
                item['content_html'] += '<h2>Notable</h2>'
                for block in semaform['furtherReading']:
                    item['content_html'] += render_block(block)
            else:
                logger.warning('unhandled semaform type {} in {}'.format(semaform['_type'], item['url']))

    if article_json.get('signal'):
        for signal in article_json['signal']:
            item['content_html'] += '<hr/>'
            for block in signal['body']:
                item['content_html'] += render_block(block)
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(args['url'])
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    n = 0
    feed_items = []
    for article in next_data['props']['pageProps']['breakingNews'] + next_data['props']['pageProps']['featuredArticles']:
        url = 'https://www.semafor.com' + article['slug']
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['title'] = 'Semafor'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed