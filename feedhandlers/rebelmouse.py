import json, re
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    query = parse_qs(split_url.query)
    if query.get('id'):
        return '{}://{}{}?id={}&width={}'.format(split_url.scheme, split_url.netloc, split_url.path, query['id'][0], width)
    else:
        return '{}://{}{}?width={}'.format(split_url.scheme, split_url.netloc, split_url.path, width)


def render_content(content):
    content_html = ''
    end_tag = ''
    if content['type'] == 'text':
        content_html += content['text']

    elif content['type'] == 'tag':
        if content['name'] == 'hr' or content['name'] == 'br':
            content_html += '<{}/>'.format(content['name'])

        elif content['name'] == 'a':
            content_html += '<a href="{}">'.format(content['attributes']['href'])
            end_tag = 'a'

        elif content['name'] == 'img':
            content_html += '<img src="{}" style="width:100%;"/>'.format(content['attributes']['src'])

        elif content['name'] == 'div':
            skip_div = False
            if content.get('attributes') and content['attributes'].get('class'):
                if 'newsroomBlockQuoteContainer' in content['attributes']['class']:
                    quote = ''
                    cite = ''
                    for child in content['children']:
                        if 'newsroomBlockQuote' in child['attributes']['class']:
                            for nino in child['children']:
                                quote += render_content(nino)
                        elif 'newsroomBlockQuoteAuthorContainer' in child['attributes']['class']:
                            for nino in child['children']:
                                cite += render_content(nino)
                    content_html += utils.add_pullquote(quote, cite)
                    return content_html
                elif content['attributes']['class'] == 'redactor-editor':
                    skip_div = True
            if content.get('children'):
                for child in content['children']:
                    if child.get('attributes') and child['attributes'].get('data-card') and child['attributes']['data-card'] == 'facebook':
                        for nino in child['children']:
                            if nino.get('attributes') and nino['attributes'].get('data-href'):
                                content_html += utils.add_embed(nino['attributes']['data-href'])
                                return content_html
            if not skip_div:
                logger.warning('unhandled div')
                content_html += '<div>'
                end_tag = 'div'

        elif content['name'] == 'blockquote':
            if content.get('attributes') and content['attributes'].get('class'):
                if 'twitter' in content['attributes']['class']:
                    for child in reversed(content['children']):
                        if child['type'] == 'tag' and child['name'] == 'a':
                            return utils.add_embed(child['attributes']['href'])
                    logger.warning('unable to find twitter-tweet url')
                elif 'tiktok' in content['attributes']['class']:
                    return utils.add_embed(content['attributes']['cite'])
                else:
                    logger.warning('unhandled blockquote class ' + content['attributes']['class'])
            else:
                content_html += '<blockquote style="border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px;">'
                end_tag = 'blockquote'

        elif content['name'] == 'iframe':
            content_html += utils.add_embed(content['attributes']['src'])

        elif re.search(r'embed|facebook|instagram|tiktok|twitter|youtube', content['name']):
            content_html += utils.add_embed(content['attributes']['iden'])

        elif content['name'] == 'particle':
            is_slideshow = False
            if content.get('attributes'):
                # Check if it's an ad
                if content['attributes'].get('href') and re.search(r'a-message-from', content['attributes']['href']):
                    return content_html
                elif content['attributes'].get('layout') and content['attributes']['layout'] == 'slideshow':
                    is_slideshow = True
            if content.get('children'):
                headline = ''
                body = ''
                img_src = ''
                img_link = ''
                embed_src = ''
                caption = ''
                credit = ''
                for child in content['children']:
                    if child['name'] == 'particle-headline':
                        if child.get('children'):
                            for nino in child['children']:
                                headline += render_content(nino)

                    elif child['name'] == 'particle-body':
                        if child.get('children'):
                            for nino in child['children']:
                                body += render_content(nino)

                    elif child['name'] == 'particle-media':
                        if child.get('children'):
                            for nino in child['children']:
                                if nino['name'] == 'rebelmouse-image':
                                    image_info = json.loads(unquote_plus(nino['attributes']['crop_info']))
                                    for key, val in image_info['thumbnails'].items():
                                        if key == 'origin':
                                            continue
                                        break
                                    img_src = resize_image(val)
                                    img_link = nino['attributes'].get('link_url')
                                elif re.search(r'embed|facebook|instagram|tiktok|twitter|youtube',nino['name']):
                                    embed_src = nino['attributes']['iden']
                                elif nino['name'] == 'blockquote':
                                    if nino.get('attributes') and nino['attributes'].get('class'):
                                        if nino['attributes']['class'] == 'twitter-tweet':
                                            for it in reversed(nino['children']):
                                                if it['type'] == 'tag' and it['name'] == 'a':
                                                    embed_src = it['attributes']['href']
                                                    break
                                        elif nino['attributes']['class'] == 'tiktok-embed':
                                            embed_src = nino['attributes']['cite']
                                        else:
                                            logger.warning('unhandled particle-media blockquote class ' + nino['attributes']['class'])
                                elif nino['name'] == 'iframe':
                                    embed_src = nino['attributes']['src']
                                elif nino['name'] == 'script' or nino['name'] == 'p':
                                    pass
                                else:
                                    logger.warning('unhandled particle-media child ' + nino['name'])

                    elif child['name'] == 'particle-caption':
                        if child.get('children'):
                            for nino in child['children']:
                                caption += render_content(nino)
                            m = re.search(r'^<p>(.*?)</p>$', caption)
                            if m:
                                caption = m.group(1)

                    elif child['name'] == 'particle-credit':
                        if child.get('children'):
                            for nino in child['children']:
                                credit += render_content(nino)
                            m = re.search(r'^<p>(.*?)</p>$', credit)
                            if m:
                                credit = m.group(1)

                    elif child['name'] == 'assembler':
                        if child.get('children'):
                            for nino in child['children']:
                                content_html += render_content(nino)

                    else:
                        logger.warning('unhandled particle child ' + child['name'])

                if headline:
                    content_html += '<hr/><h3>{}</h3>'.format(headline)
                if img_src:
                    if caption and credit:
                        caption += ' | ' + credit
                    elif credit and not caption:
                        caption = credit
                    content_html += utils.add_image(img_src, caption, link=img_link)
                    if is_slideshow:
                        content_html += '<br/>'
                if embed_src:
                    content_html += utils.add_embed(embed_src)
                if body:
                    content_html += body
                return content_html

        elif content['name'] == 'assembler' or content['name'] == 'script':
            pass

        else:
            # Filter out captions/credits for some embeds
            if content.get('attributes') and content['attributes'].get('class'):
                if re.search(r'-caption|-credit', content['attributes']['class']):
                    return content_html
            content_html += '<{}>'.format(content['name'])
            end_tag = content['name']

    if content.get('children'):
        for child in content['children']:
            content_html += render_content(child)
    if end_tag:
        content_html += '</{}>'.format(end_tag)
    return content_html


def get_content(url, args, save_debug=False):
    article_html = utils.get_url_html(url)
    m = re.search(r'"fullBootstrapUrl": "([^"]+)"', article_html)
    if not m:
        logger.warning('unable to determine bootstrap url in ' + url)
        return None

    bootstrap_path = m.group(1).replace('\\u0026', '&')
    split_url = urlsplit(url)
    bootstrap_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, bootstrap_path)
    bootstrap_json = utils.get_url_json(bootstrap_url)

    post_json = bootstrap_json['post']
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['post_url']
    item['title'] = post_json['headline']

    dt = datetime.fromtimestamp(post_json['created_ts']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromtimestamp(post_json['updated_ts']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for author in post_json['roar_authors']:
        authors.append(author['title'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = post_json['public_tags'].copy()

    item['summary'] = post_json['description']

    content_json = json.loads(post_json['structurized_content'])
    if save_debug:
        utils.write_file(content_json, './debug/content.json')

    item['content_html'] = ''

    if post_json.get('subheadline'):
        item['content_html'] += post_json['subheadline']

    if post_json.get('image_info'):
        for key, val in post_json['image_info'].items():
            if key == 'origin':
                continue
            break
        item['_image'] = resize_image(val)

    captions = []
    if post_json.get('photo_caption'):
        m = re.search('^<p>(.+?)</p>$', post_json['photo_caption'])
        if m:
            captions.append(m.group(1))
        else:
            captions.append(post_json['photo_caption'])
    if post_json.get('photo_credit'):
        m = re.search('^<p>(.+?)</p>$', post_json['photo_credit'])
        if m:
            captions.append(m.group(1))
        else:
            captions.append(post_json['photo_credit'])

    if item.get('_image'):
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    for child in content_json['children']:
        item['content_html'] += render_content(child)

    if post_json.get('original_url'):
        item['content_html'] += '<p><a href="{}">Read more at {}</a></p>'.format(post_json['original_url'], post_json['original_domain'])
    #item['content_html'] = post_json['body']
    return item

def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
