import json, pytz, re, requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import rss, wp_posts

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
    return matchobj.group(0).encode('latin1').decode('utf-8')


def render_block(block):
    content_html = ''
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
            else:
                logger.warning('unhandled block child type ' + child['_type'])
            if child.get('marks'):
                for m in child['marks']:
                    print(m)
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
            content_html += start_tag + text + end_tag

        content_html += block_end_tag

    elif block['_type'] == 'imageEmbed':
        img_src = re.sub('^image-', r'https://img.semafor.com/', block['imageEmbed']['asset']['_ref'])
        img_src = re.sub('-(\w+)$', r'.\1', img_src)
        captions = []
        if block['imageEmbed'].get('caption'):
            captions.append(block['imageEmbed']['caption'])
        if block['imageEmbed'].get('attribution'):
            captions.append(block['imageEmbed']['attribution'])
        content_html += utils.add_image(img_src, ' | '.join(captions))

    elif block['_type'] == 'youtube' or block['_type'] == 'twitter':
        content_html += utils.add_embed(block['url'])

    elif block['_type'] == 'ad':
        pass

    else:
        logger.warning('unhandled intro block type ' + block['_type'])

    return content_html


def get_content(url, args, save_debug):
    next_data = get_next_data(url)
    if not next_data:
        return None

    article_json = next_data['props']['pageProps']['article']
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

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

    item['author'] = {"name": article_json['author']['name']}

    # TODO: tags
    item['tags'] = []
    if article_json.get('vertical'):
        item['tags'].append(article_json['vertical'])
    if article_json.get('location'):
        item['tags'].append(article_json['location'])
    if not item.get('tags'):
        del item['tags']

    if article_json.get('ledePhoto'):
        item['_image'] = article_json['ledePhoto']

    if article_json.get('seoDescription'):
        item['summary'] = article_json['seoDescription']

    item['content_html'] = ''
    if article_json.get('intro'):
        for block in article_json['intro']['body']:
            item['content_html'] += render_block(block)

    if article_json.get('semaforms'):
        for semaform in article_json['semaforms']:
            if semaform.get('title'):
                item['content_html'] += '<hr/><h2>{}</h2>'.format(semaform['title'])
            if semaform['_type'] == 'scoop':
                for block in semaform['scoop']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'generaform':
                for block in semaform['body']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'reportersTake':
                item['content_html'] += '<hr/><h2>{}\'s View</h2>'.format(semaform['author']['shortName'])
                for block in semaform['thescoop']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'theViewFrom':
                item['content_html'] += '<hr/><h2>The View from {}</h2>'.format(semaform['where'])
                for block in semaform['theViewFrom']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'roomForDisagreement':
                item['content_html'] += '<hr/><h2>Room For Disagreement</h2>'
                for block in semaform['roomForDisagreement']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'furtherReading':
                item['content_html'] += '<hr/><h2>Notable</h2>'
                for block in semaform['furtherReading']:
                    item['content_html'] += render_block(block)
            else:
                logger.warning('unhandled semaform type {} in {}'.format(semaform['_type'], item['url']))

    return item


def get_feed(args, save_debug=False):
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
        item = get_content(url, args, save_debug)
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