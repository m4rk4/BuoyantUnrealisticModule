import re
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1280):
    if 'mblycdn.com/uploads/' in img_src:
        split_url = urlsplit(img_src)
        paths = list(filter(None, split_url.path[1:].split('/')))
        return 'https://' + split_url.netloc + '/' + paths[1] + '/resized/' + '/'.join(paths[2:-1]) + '/w{}/'.format(width) + paths[-1]
    return img_src


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    api_url = 'https://{}/api/post/{}?post_type=post&blocks=true'.format(split_url.netloc, paths[-1])
    post_json = utils.get_url_json(api_url, use_proxy=True, use_curl_cffi=True)
    if not post_json:
        return None
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['ID']
    item['url'] = 'https://' + split_url.netloc + post_json['path']
    item['title'] = post_json['seo']['title']

    dt = datetime.fromisoformat(post_json['created_at'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['updated_at'])
    item['date_modified'] = dt.isoformat()

    item['authors'] = []
    if post_json['acf'].get('feature_byline_override'):
        for it in post_json['acf']['feature_byline_override'].split(' | '):
            title = ''
            for x in re.split(', | and ', it):
                m = re.search(r'^(\w+)\sby\s(.*)', x, flags=re.I)
                if m:
                    title = m.group(1).strip()
                    author = m.group(2)
                else:
                    m = re.search(r'^By (.*)', x, flags=re.I)
                    if m:
                        author = m.group(1)
                    else:
                        author = x
                if title:
                    author += ' (' + title + ')'
                item['authors'].append({"name": author})
        # item['authors'] = [{"name": x.title()} for x in re.split(r',\s|\sand\s', post_json['acf']['feature_byline_override'])]
        # item['authors'][0]['name'] = re.sub(r'^(\w+\s)?By\s', '', item['authors'][0]['name'])
    elif post_json['acf'].get('AuthorDisplayText'):
        item['authors'] = [{"name": post_json['acf']['AuthorDisplayText']}]
    else:
        item['authors'] = [{"name": x['display_name']} for x in post_json['authors']]
    if post_json['acf'].get('PhotographerDisplayText'):
        item['authors'].append({"name": post_json['acf']['PhotographerDisplayText'] + ' (Photography)'})
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    if post_json.get('taxonomies'):
        for it in post_json['taxonomies']:
            item['tags'].append(it['term']['name'])
    if post_json.get('tags'):
        for it in post_json['tags']:
            item['tags'].append(it['name'])

    if post_json.get('featured_image_id'):
        block = next((it for it in post_json['attachments'] if it['ID'] == post_json['featured_image_id']), None)
        if block:
            item['image'] = block['url']

    attachments = post_json['attachments']
    def add_attachment(id=0, title='', url=''):
        nonlocal attachments
        attachment = None
        if id > 0:
            attachment = next((it for it in attachments if it['ID'] == id), None)
        if not attachment and title:
            attachment = next((it for it in attachments if it['title'] == title), None)
        if not attachment and url:
            attachment = next((it for it in attachments if it['url'] == url), None)
        if attachment:
            img_src = resize_image(attachment['url'])
            captions = []
            if attachment.get('caption_blocks'):
                captions.append(re.sub(r'\s*<br>\s*', ' ', format_blocks(attachment['caption_blocks'])))
            if attachment.get('credit_blocks'):
                captions.append(re.sub(r'\s*<br>\s*', ' ', format_blocks(attachment['credit_blocks'])))
            return utils.add_image(img_src, ' | '.join(captions))
        logger.warning('unknown attachment id {}'.format(id))
        return ''

    def format_blocks(content_blocks):
        content_html = ''
        dropcap = False
        for block in content_blocks:
            if isinstance(block, str):
                if dropcap and '\n' in block:
                    content_html += re.sub(r'\n', '<br style="clear:both">', block, count=1).replace('\n', '<br>')
                    dropcap = False
                else:
                    content_html += block.replace('\n', '<br>')
            elif isinstance(block, list):
                if block[0] == 'a':
                    content_html += '<a href="{}">{}</a>'.format(block[1]['href'], format_blocks(block[2]))
                elif block[0] == 'span':
                    if block[1].get('id') and block[1]['id'].startswith('attachment'):
                        id = int(block[1]['id'].split('_')[-1])
                        content_html += add_attachment(id)
                    elif block[1].get('data-shortcode') and block[1]['data-shortcode'] == 'attachment-row':
                        block_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                        for id in block[1]['ids'].split(','):
                            block_html += '<div style="flex:1; min-width:360px;">' + add_attachment(int(id)) + '</div>'
                        block_html += '</div>'
                        m = re.findall(r'<figcaption>(.*?)</figcaption>', block_html)
                        if len(m) == 1:
                            block_html = block_html.replace('<figcaption>' + m[0] + '</figcaption>', '')
                            block_html += '<div>' + m[0] + '</div>'
                        content_html += block_html
                    elif block[1].get('data-shortcode') and block[1]['data-shortcode'] == 'cta':
                        content_html += utils.add_button(block[1]['url'], format_blocks(block[2]))
                    elif block[1].get('class') and 'drop-cap' in block[1]['class']:
                        content_html += '<span style="float:left; font-size:4em; line-height:0.8em; color:red;">' + format_blocks(block[2]) + '</span>'
                        dropcap = True
                    else:
                        content_html += '<span'
                        for key, val in block[1].items():
                            content_html += ' {}="{}"'.format(key, val)
                        content_html += '>' + format_blocks(block[2]) + '</span>'
                elif block[0] == 'figure':
                    block_html = format_blocks(block[2])
                    if block_html.startswith('<figure') and block_html.endswith('</figure>'):
                        content_html += block_html
                    else:
                        logger.warning('unhandled figure block')
                elif block[0] == 'img':
                    id = 0
                    if block[1].get('class'):
                        m = re.search(r'wp-image-(\d+)', block[1]['class'])
                        if m:
                            id = int(m.group(1))
                    img_paths = list(filter(None, urlsplit(url).path[1:].split('/')))
                    img_title = img_paths[-1].split('.')[0]
                    content_html += add_attachment(id=id, title=img_title, url=block[1]['src'])
                elif block[0] == 'iframe':
                    content_html += utils.add_embed(block[1]['src'])
                elif block[0] == 'blockquote':
                    quote = format_blocks(block[2])
                    quote = re.sub(r'<h5[^>]+>|</h5>', '', quote)
                    content_html += '<blockquote style="margin:2em 0; padding:8px; border-top:1px solid #ccc; border-bottom:1px solid #ccc;"><span style="font-size:1.5em; font-weight:bold; color:red;">' + quote + '</span></blockquote>'
                elif block[0] == 'hr':
                    content_html += '<hr>'
                elif block[0] == 'h5':
                    block_html = format_blocks(block[2])
                    if not block_html.startswith('<figure>'):
                        content_html += '<h5 style="font-size:2em; margin:8px 0;">' + block_html + '</h5>'
                elif block[0] == 'p' and 'class' in block[1] and 'wp-block-pub-wordpress-gutenberg-plugin-cta' in block[1]['class']:
                    content_html += format_blocks(block[2])
                elif block[0] in ['b', 'em', 'h1', 'h2', 'h3', 'h4', 'i', 'p', 'strong', 'sup']:
                    content_html += '<{0}>{1}</{0}>'.format(block[0], format_blocks(block[2]))
                elif block[0] == 'div':
                    if block[1].get('id') and '-ad-' in block[1]['id']:
                        pass
                    else:
                        block_html = format_blocks(block[2])
                        if block[1].get('class') and 'feature-article' in block[1]['class']:
                            content_html += block_html
                        elif re.search(r'(<br>)*<figure', block_html):
                            content_html += block_html
                        else:
                            logger.warning('unhandled div block: ' + block_html)
                elif block[0] == 'nextpage':
                    pass
                else:
                    logger.warning('unhandled block ' + block[0])
        return content_html

    item['content_html'] = format_blocks(post_json['content_blocks'])

    if post_json.get('featured_image_id'):
        attachment = next((it for it in attachments if it['ID'] == post_json['featured_image_id']), None)
        if attachment:
            if attachment['title'] not in item['content_html']:
                img_src = resize_image(attachment['url'])
                captions = []
                if attachment.get('caption_blocks'):
                    captions.append(format_blocks(attachment['caption_blocks']))
                if attachment.get('credit_blocks'):
                    captions.append(format_blocks(attachment['credit_blocks']))
                item['content_html'] = utils.add_image(img_src, ' | '.join(captions)) + '<br><br>' + item['content_html']

    if post_json.get('excerpt_blocks'):
        item['content_html'] = '<p><em>' + re.sub(r'\s*<br>\s*', ' ', format_blocks(post_json['excerpt_blocks'])) + '</em></p>' + item['content_html']

    item['content_html'] = re.sub(r'(<br>){3,}', '<br><br>', item['content_html'])
    item['content_html'] = re.sub(r'(</(h\d|p)>)(<br>){1,}', r'\1', item['content_html'])
    item['content_html'] = re.sub(r'</figure>(<br>){2,}', r'</figure><br>', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if 'category' in paths:
        api_url = 'https://{}/api/categories/{}/related?all_post_types=true&bypass_denylist=true&order=desc&format=simple&limit=24&offset=0&blocks=true'.format(split_url.netloc, paths[-1])
        feed_title = paths[-1].title() + ' | ' + split_url.netloc
    elif 'tag' in paths:
        api_url = 'https://{}/api/posts?all_post_types=true&bypass_denylist=true&order=desc&format=simple&tag={}&limit=24&offset=0&blocks=true'.format(split_url.netloc, paths[-1])
        feed_title = paths[-1].title() + ' | ' + split_url.netloc
    else:
        api_url = 'https://{}/api/posts?all_post_types=true&bypass_denylist=true&order=desc&format=simple&limit=24&offset=0&blocks=true'.format(split_url.netloc)
        feed_title = split_url.netloc
    api_json = utils.get_url_json(api_url, use_proxy=True, use_curl_cffi=True)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    for article in api_json['results']:
        article_url = 'https://' + split_url.netloc + article['path']
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
    if feed_title:
        feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
