import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    return '{}://{}{}?quality=80&strip=all&w={}'.format(split_url.scheme, split_url.netloc, split_url.path, width)


def add_image(image):
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('credit'):
        captions.append(image['credit'])
    return utils.add_image(image['sourceUrl'], ' | '.join(captions))


def format_obsession_email(email_html):
    soup = BeautifulSoup(email_html)
    email_body = soup.body
    for el in email_body.find_all('span', class_='preheader'):
        el.name = 'h2'

    return None

def format_email_table(table):
    content_html = ''
    img_src = ''
    for tr in table.find_all('tr'):
        if table == tr.find_parent('table'):
            if tr.table:
                content_html += format_email_table(tr.table)

            elif tr.get('class') and 'subheadline' in tr['class']:
                content_html += '<h3>{}</h3>'.format(tr.get_text())

            elif tr.div:
                if tr.div.get('style'):
                    styles = tr.div['style'].split(';')
                else:
                    styles = []
                if 'color:#4c4c4c' in styles and content_html.endswith('</figure>'):
                    content_html = content_html[:-9] + '<figcaption><small>{}</small></figcaption></figure>'.format(tr.div.decode_contents())
                else:
                    content = tr.div.decode_contents()
                    if 'text-transform:uppercase' in styles:
                        content = content.upper()
                    if 'font-size:30px' in styles:
                        start_tag = '<h2>'
                        end_tag = '</h2>'
                    else:
                        start_tag = '<p>'
                        end_tag = '</p>'
                    if 'font-weight:bold' in styles:
                        start_tag += '<strong>'
                        end_tag = '</strong>' + end_tag
                    content_html += '{}{}{}'.format(start_tag, content, end_tag)

            elif tr.p:
                if re.search(r'border-top:solid', tr.p['style']):
                    content_html += '<hr/>'
                else:
                    logger.warning('unhandled <p> section')

            elif tr.img:
                content_html += utils.add_image(tr.img['src'])
    return content_html


def format_email_content(email_html):
    content_html = ''
    soup = BeautifulSoup(email_html, 'html.parser')
    table = None
    for td in soup.find_all('td', class_='subheadline'):
        parent = td.find_parent('table')
        if parent == table:
            continue
        table = parent
        content_html += format_email_table(table)
    return content_html


def get_apollo_state(url):
    page_html = utils.get_url_html(url)
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', string=re.compile(r'__APOLLO_STATE__'))
    if not el:
        logger.warning('unable to find APOLLO_STATE in ' + url)
        return None
    m = re.search(r'window.__APOLLO_STATE__ = (.*);$', el.string)
    if not m:
        logger.warning('unable to parse APOLLO_STATE in ' + url)
        return None
    return json.loads(m.group(1))


def get_content(url, args, save_debug=False):
    apollo_state = get_apollo_state(url)
    if not apollo_state:
        return None
    if save_debug:
        utils.write_file(apollo_state, './debug/debug.json')

    post_id = ''
    for key, val in apollo_state['ROOT_QUERY'].items():
        if '/emails/' in url and key.startswith('email'):
            post_id = val['__ref']
            break
        elif key.startswith('posts'):
            post_id = val['nodes'][0]['__ref']
            break
    if not post_id:
        logger.warning('unhandled ROOT_QUERY in ' + url)
    post_json = apollo_state[post_id]

    item = {}
    if post_json['__typename'] == 'Email':
        item['id'] = post_json['emailId']
    else:
        item['id'] = post_json['postId']

    item['url'] = post_json['link']
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['dateGmt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if post_json.get('modifiedGmt'):
        dt = datetime.fromisoformat(post_json['modifiedGmt']).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    authors = []
    if post_json.get('coAuthors'):
        for node in post_json['coAuthors']['nodes']:
            author = apollo_state[node['__ref']]
            authors.append(author['name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif post_json.get('emailLists'):
        for node in post_json['emailLists']['nodes']:
            author = apollo_state[node['__ref']]
            authors.append(author['name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = 'Quartz'

    item['tags'] = []
    for key, val in post_json.items():
        if key.startswith('tags'):
            for node in val['nodes']:
                tag = apollo_state[node['__ref']]
                item['tags'].append(tag['name'])
    if not item.get('tags'):
        del item['tags']

    if post_json.get('excerpt'):
        item['summary'] = post_json['excerpt']

    item['content_html'] = ''

    if post_json.get('featuredImage'):
        image = apollo_state[post_json['featuredImage']['__ref']]
        item['_image'] = image['sourceUrl']
        captions = []
        if image.get('caption'):
            captions.append(image['caption'])
        if image.get('credit'):
            captions.append(image['credit'])
        item['content_html'] += utils.add_image(resize_image(item['_image']), ' | '.join(captions))

    if post_json.get('blocks'):
        for blk in post_json['blocks']:
            if blk.get('__ref'):
                block = apollo_state[blk['__ref']]
            elif blk.get('type'):
                block = blk
            else:
                logger.warning('unhandled block in ' + item['url'])
                continue

            if re.search(r'^(P|H\d|OL|UL|TABLE)$', block['type']):
                item['content_html'] += '<{0}>{1}</{0}>'.format(block['tagName'], block['innerHtml'])

            elif block['type'] == 'HR':
                item['content_html'] += '<hr/>'

            elif block['type'] == 'PRE':
                item['content_html'] += '<pre style="white-space: pre-wrap;">{}</pre>'.format(block['innerHtml'])

            elif block['type'] == 'EL':
                bullet = next((it for it in block['attributes'] if it['name'] == 'emojiBullets'), None)
                if bullet:
                    inner_html = re.sub(r'<li\b\s?[^>]*>', '<li>{} '.format(bullet['value']), block['innerHtml'])
                    item['content_html'] += '<ul style="list-style-type: none;">{}</ul>'.format(inner_html)
                else:
                    logger.warning('unhandled EL list in ' + item['url'])
                    item['content_html'] += '<ul>{}</ul>'.format(block['innerHtml'])

            elif block['type'] == 'BLOCKQUOTE':
                item['content_html'] += utils.add_blockquote(block['innerHtml'])

            elif block['type'] == 'SHORTCODE_PULLQUOTE':
                item['content_html'] += utils.add_pullquote(block['innerHtml'])

            elif block['type'] == 'SHORTCODE_CAPTION':
                img_src = next((it for it in block['attributes'] if it['name'] == 'url'), None)
                captions = []
                caption = next((it for it in block['attributes'] if it['name'] == 'caption'), None)
                if caption:
                    captions.append(caption['value'])
                caption = next((it for it in block['attributes'] if it['name'] == 'credit'), None)
                if caption:
                    captions.append(caption['value'])
                if img_src:
                    item['content_html'] += utils.add_image(resize_image(img_src['value']), ' | '.join(captions))
                else:
                    logger.warning('unhandled SHORTCODE_CAPTION block in ' + item['url'])

            elif block['type'] == 'IMG':
                img_src = next((it for it in block['attributes'] if it['name'] == 'src'), None)
                # If it's a 1x1 img, skip it
                width = next((it for it in block['attributes'] if it['name'] == 'width'), None)
                height = next((it for it in block['attributes'] if it['name'] == 'height'), None)
                if (width and height) and (int(width['value']) > 1 and int(height['value']) > 1):
                    item['content_html'] += utils.add_image(resize_image(img_src['value']))

            elif block['type'] == 'SHORTCODE_VIDEO':
                video = next((it for it in block['attributes'] if it['name'] == 'mp4'), None)
                if video:
                    poster = '{}/image?url={}&width=1000'.format(config.server, quote_plus(video['value']))
                    item['content_html'] += utils.add_video(video['value'], 'video/mp4', poster)

            elif block['type'].startswith('EMBED_'):
                embed_url = next((it for it in block['attributes'] if it['name'] == 'url'), None)
                if embed_url:
                    item['content_html'] += utils.add_embed(embed_url['value'])
                else:
                    logger.warning('unhandled block {} in {}'.format(block['type'], item['url']))

            elif block['type'] == 'SHORTCODE_BUTTON':
                href = next((it for it in block['attributes'] if it['name'] == 'href'), None)
                if not (href and href['value'] == 'https://qz.com/become-a-member'):
                    logger.warning('unhandled SHORTCODE_BUTTON in ' + item['url'])

            elif re.search(r'_PARTNER|_REFERRAL|_SPONSOR', block['type']):
                continue

            else:
                logger.warning('unhandled block type {} in {}'.format(block['type'], item['url']))

    item['content_html'] = item['content_html'].replace('<hr/><hr/>', '<hr/>')
    item['content_html'] = item['content_html'].replace('</figure><figure', '</figure><br/><figure')
    return item


def get_feed(args, save_debug=False):
    if args['url'].startswith('https://cms.qz.com/feed'):
        return rss.get_feed(args, save_debug, get_content)

    apollo_state = get_apollo_state(args['url'])
    if save_debug:
        utils.write_file(apollo_state, './debug/feed.json')

    urls = []
    if '/emails' in args['url']:
        typename = 'Email'
    else:
        typename = 'Post'
    for key, val in apollo_state.items():
        block_type = val.get('__typename')
        if block_type and block_type == typename:
            urls.append(val['link'])

    n = 0
    feed = utils.init_jsonfeed(args)
    #feed['title'] = feed_title
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
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True).copy()
    return feed