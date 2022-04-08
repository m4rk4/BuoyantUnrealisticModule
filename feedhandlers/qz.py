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
        if tr.table:
            content_html += format_email_table(tr.table)

        elif tr.get('class') and 'subheadline' in tr['class']:
            content_html += '<h3>{}</h3>'.format(tr.get_text())

        elif tr.div:
            caption = ''
            if img_src:
                if re.search(r'4c4c4c', tr.div['style']):
                    caption = tr.div.decode_contents()
                content_html += utils.add_image(img_src, caption)
                img_src = ''
            if not caption:
                start_tag = '<p>'
                end_tag = '</p>'
                if re.search(r'text-transform:uppercase;', tr.div['style']):
                    start_tag = '<p style="text-transform:uppercase;">'
                if re.search(r'font-weight:bold;', tr.div['style']):
                    start_tag += '<strong>'
                    end_tag = '</strong>' + end_tag
                content_html += '{}{}{}'.format(start_tag, tr.div.decode_contents(), end_tag)

        elif tr.p:
            if re.search(r'border-top:solid', tr.p['style']):
                content_html += '<hr/>'
            else:
                logger.warning('unhandled <p> section')

        elif tr.img:
            img_src = tr.img['src']
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


def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[0] == 'emails':
        is_email = True
        email_id = 'email:{}'.format(paths[-1])
        b64_id = base64.b64encode(email_id.encode('utf-8')).decode()
        api_url = 'https://content.qz.com/graphql?operationName=EmailById&variables=%7B%22id%22%3A%22{}%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%229cce2423332608c4d4f038009db55f520a7ae9d059065cd5d5b90b05fd870f47%22%7D%7D'.format(b64_id)
    else:
        is_email = False
        api_url = 'https://content.qz.com/graphql?operationName=Article&variables=%7B%22id%22%3A{}%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%228701a730ae3da33b54191a893cdfd8e36643ab22de059683d7f74e628ece3575%22%7D%7D'.format(paths[-2])
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    item = {}

    if is_email:
        article_json = api_json['data']['email']
        item['id'] = article_json['emailId']
    else:
        article_json = api_json['data']['posts']['nodes'][0]
        item['id'] = article_json['postId']

    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item['url'] = article_json['link']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['dateGmt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('modifiedGmt'):
        dt = datetime.fromisoformat(article_json['modifiedGmt']).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('authors'):
        authors = []
        for author in article_json['authors']['nodes']:
            authors.append(author['name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif article_json.get('emailLists'):
        item['author']['name'] = article_json['emailLists']['nodes'][0]['name']
    else:
        item['author']['name'] = 'Quartz'

    if article_json.get('tags'):
        item['tags'] = []
        for tag in article_json['tags']['nodes']:
            item['tags'].append(tag['name'])

    if article_json.get('excerpt'):
        item['summary'] = article_json['excerpt']

    item['content_html'] = ''

    if article_json.get('featuredImage'):
        item['_image'] = article_json['featuredImage']['sourceUrl']
        item['content_html'] += add_image(article_json['featuredImage'])

    if article_json.get('blocks'):
        for block in article_json['blocks']:
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
                    logger.warning('unhandled SHORTCODE_CAPTION block in ' + url)

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
                    logger.warning('unhandled block {} in {}'.format(block['type'], url))

            else:
                print(block['type'])
                item['content_html'] += '<{0}>{1}</{0}>'.format(block['tagName'], block['innerHtml'])

    if is_email:
        item['content_html'] += format_email_content(article_json['html'])

    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
