import base64, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

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


def get_content_item(content_json, args, save_debug=False):
    if save_debug:
        utils.write_file(content_json, './debug/debug.json')

    item = {}
    if content_json['__typename'] == 'Email':
        item['id'] = content_json['emailId']
    else:
        item['id'] = content_json['postId']

    item['url'] = content_json['link']
    item['title'] = content_json['title']

    dt = datetime.fromisoformat(content_json['dateGmt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if content_json.get('modifiedGmt'):
        dt = datetime.fromisoformat(content_json['modifiedGmt']).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if content_json.get('authors'):
        authors = []
        for author in content_json['authors']['nodes']:
            authors.append(author['name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif content_json.get('emailLists'):
        item['author']['name'] = content_json['emailLists']['nodes'][0]['name']
    else:
        item['author']['name'] = 'Quartz'

    if content_json.get('tags'):
        item['tags'] = []
        for tag in content_json['tags']['nodes']:
            item['tags'].append(tag['name'])

    if content_json.get('excerpt'):
        item['summary'] = content_json['excerpt']

    item['content_html'] = ''

    if content_json.get('featuredImage'):
        item['_image'] = content_json['featuredImage']['sourceUrl']
        item['content_html'] += add_image(content_json['featuredImage'])

    if content_json.get('blocks'):
        for block in content_json['blocks']:
            if block['type'] == 'BLOCKQUOTE':
                item['content_html'] += utils.add_blockquote(block['innerHtml'])

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

            elif block['type'].startswith('EMBED_'):
                embed_url = next((it for it in block['attributes'] if it['name'] == 'url'), None)
                if embed_url:
                    item['content_html'] += utils.add_embed(embed_url['value'])
                else:
                    logger.warning('unhandled block {} in {}'.format(block['type'], item['url']))

            else:
                print(block['type'])
                item['content_html'] += '<{0}>{1}</{0}>'.format(block['tagName'], block['innerHtml'])

    if content_json['__typename'] == 'Email':
        item['content_html'] += format_email_content(content_json['html'])

    return item


def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[0] == 'emails':
        email_id = 'email:{}'.format(paths[-1])
        b64_id = base64.b64encode(email_id.encode('utf-8')).decode()
        api_url = 'https://content.qz.com/graphql?operationName=EmailById&variables=%7B%22id%22%3A%22{}%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%229cce2423332608c4d4f038009db55f520a7ae9d059065cd5d5b90b05fd870f47%22%7D%7D'.format(b64_id)
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        content_json = api_json['data']['email']
    else:
        api_url = 'https://content.qz.com/graphql?operationName=Article&variables=%7B%22id%22%3A{}%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%228701a730ae3da33b54191a893cdfd8e36643ab22de059683d7f74e628ece3575%22%7D%7D'.format(paths[-2])
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        content_json = api_json['data']['posts']['nodes'][0]
    return get_content_item(content_json, args, save_debug)


def get_feed(args, save_debug=False):
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[0] == 'emails':
        if len(paths) == 1 or (len(paths) == 2 and paths[1] == 'latest'):
            api_url = 'https://content.qz.com/graphql?operationName=EmailsByTag&variables=%7B%22after%22%3A%22%22%2C%22perPage%22%3A10%2C%22slug%22%3A%5B%22show-email-in-feeds%22%5D%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%2204cbaf74705634bc4dae7fa30efb8b160dbf163e79b2eb315e2295db9a81ba89%22%7D%7D'
            api_json = utils.get_url_json(api_url)
            if not api_json:
                return None
            email_list = api_json['data']['emails']['nodes']
            email_name = 'Quartz Emails'
        else:
            api_url = 'https://content.qz.com/graphql?operationName=EmailsByList&variables=%7B%22after%22%3A%22%22%2C%22perPage%22%3A10%2C%22slug%22%3A%22{}%22%2C%22tags%22%3A%5B%22daily-brief-americas%22%5D%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%222da62c026df1475fabfe7053f8368af55a372d6d645e6f3bd404360cb1a26a09%22%7D%7D'.format(paths[1])
            api_json = utils.get_url_json(api_url)
            if not api_json:
                return None
            email_list = api_json['data']['emailLists']['nodes'][0]['emails']['nodes']
            email_name = api_json['data']['emailLists']['nodes'][0]['name']

        if save_debug:
            utils.write_file(api_json, './debug/feed.json')

        n = 0
        feed = utils.init_jsonfeed(args)
        feed['title'] = email_name
        feed['items'] = []
        for email in email_list:
            if save_debug:
                logger.debug('getting content for ' + email['link'])
            if email.get('html'):
                item = get_content_item(email, args, save_debug)
            else:
                item = get_content(email['link'], args, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed['items'].append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break
    else:
        feed = rss.get_feed(args, save_debug, get_content)
    return feed
