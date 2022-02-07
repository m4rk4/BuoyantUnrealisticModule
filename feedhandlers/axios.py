import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

from feedhandlers import rss
import utils

import logging

logger = logging.getLogger(__name__)


def add_image(image):
    caption = format_blocks(image['caption'])
    if caption.startswith('<p>'):
        caption = caption.replace('<p>', '')
        caption = caption.replace('</p>', '<br/><br/>')
        if caption.endswith('<br/><br/>'):
            caption = caption[:-10]
    if image['crops']['16x9'].get('videos'):
        img_src = image['crops']['16x9']['url']
    else:
        img = utils.closest_dict(image['crops']['16x9']['sizes'], 'width', 1000)
        img_src = img['url']
    return utils.add_image(img_src, caption)


def format_styles(block, entities):
    n = 0
    block_html = block['text']
    for style in block['inlineStyleRanges']:
        i = style['offset']
        j = i + style['length']
        style_text = block['text'][i:j]
        style_html = ''
        if style['style'] == 'BOLD':
            style_html = '<b>{}</b>'.format(style_text)
        elif style['style'] == 'ITALIC':
            style_html = '<i>{}</i>'.format(style_text)
        else:
            logger.warning('unhandled style type ' + style['style'])
        if style_html:
            block_html = block_html.replace(style_text, style_html)

    for style in block['entityRanges']:
        i = style['offset']
        j = i + style['length']
        style_text = block['text'][i:j]
        entity = entities[style['key']]
        if entity['type'] == 'LINK':
            if entity['data'].get('href'):
                href = entity['data']['href']
            else:
                href = entity['data']['url']
            if 'link.axios.com' in href:
                href = utils.get_redirect_url(href)
            style_html = '<a href="{}">{}</a>'.format(href, style_text)
            block_html = block_html.replace(style_text, style_html)
        else:
            logger.warning('unhandled entity type ' + entity['type'])
    return block_html

def format_blocks(blocks):
    content_html = ''
    entities = blocks['entityMap']
    for i, block in enumerate(blocks['blocks']):
        if block['type'] == 'unstyled':
            content_html += '<p>{}</p>'.format(format_styles(block, entities))

        elif block['type'] == 'header-two':
            content_html += '<h2>{}</h2>'.format(format_styles(block, entities))

        elif block['type'] == 'blockquote':
            content_html += utils.add_blockquote(format_styles(block, entities))

        elif block['type'] == 'plain-quote':
            quote = format_styles(block, entities)
            author = ''
            try:
                next_block = blocks['blocks'][i+1]
                if next_block['type'] == 'quote-attribution':
                    author = format_styles(next_block, entities)
            except:
                pass
            content_html += utils.add_pullquote(quote, author)

        elif block['type'] == 'quote-attribution':
            pass

        elif re.search(r'ordered-list-item', block['type']):
            if block['type'] == 'unordered-list-item':
                tag = 'ul'
            else:
                tag = 'ol'
            try:
                prev_block = blocks['blocks'][i-1]
                if not re.search(r'ordered-list-item', prev_block['type']):
                    content_html += '<{}>'.format(tag)
            except:
                # must be the first block
                content_html += '<{}>'.format(tag)
            content_html += '<li>{}</li>'.format(format_styles(block, entities))
            try:
                next_block = blocks['blocks'][i+1]
                if not re.search(r'ordered-list-item', next_block['type']):
                    content_html += '</{}>'.format(tag)
            except:
                # must be the last block
                content_html += '</{}>'.format(tag)

        elif block['type'] == 'image':
            caption = format_styles(block, entities)
            content_html += utils.add_image(block['data']['src'], caption)

        elif block['type'] == 'embed':
            if block['data']['type'] == 'twitter' or block['data']['type'] == 'youtube' or block['data']['type'] == 'giphy':
                content_html += utils.add_embed(block['data']['url'])

            elif block['data']['type'] == 'axios-visual' or block['data']['type'] == 'datawrapper':
                content_html += utils.add_image(block['data']['oembed']['apple_fallback'], block['text'], link=block['data']['url'])

            elif block['data']['type'] == 'megaphone':
                content_html += utils.add_embed('https://playlist.megaphone.fm/?e=' + block['data']['oembed']['episode_id'])

            elif block['data']['type'] == 'jwplayer-video':
                content_html += utils.add_embed(block['data']['url'])

            elif block['data']['type'] == 'documentcloud-document':
                content_html += '<blockquote><b>Embedded content from <a href="{0}">{0}</a></b></blockquote>'.format(block['data']['url'])

            else:
                logger.warning('unhandled embed type ' + block['data']['type'])

        elif block['type'] == 'keep-reading':
            pass

        else:
            logger.warning('unhandled block type ' + block['type'])
    return content_html

def get_item(content_json, args, save_debug):
    if save_debug:
        utils.write_file(content_json, './debug/debug.json')

    item = {}
    item['id'] = content_json['id']
    item['url'] = content_json['permalink']

    if content_json.get('headline'):
        item['title'] = content_json['headline']
    elif content_json.get('subject_line'):
        item['title'] = content_json['subject_line']

    dt = datetime.fromisoformat(content_json['published_date'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if content_json.get('last_published'):
        dt = datetime.fromisoformat(content_json['last_published'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()
    elif content_json.get('last_updated'):
        dt = datetime.fromisoformat(content_json['last_updated'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()

    authors = []
    for author in content_json['authors']:
      authors.append(author['display_name'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if content_json.get('primary_tag'):
        item['tags'].append(content_json['primary_tag']['name'])
    if content_json.get('tags'):
        for tag in content_json['tags']:
            item['tags'].append(tag['name'])
    if content_json.get('topics'):
        for tag in content_json['topics']:
            item['tags'].append(tag['name'])
    if content_json.get('subtopics'):
        for tag in content_json['subtopics']:
            item['tags'].append(tag['name'])

    if content_json.get('summary'):
        soup = BeautifulSoup(content_json['summary'], 'html.parser')
        for el in soup.find_all('a'):
            href = el['href']
            if 'link.axios.com' in href:
                href = utils.get_redirect_url(href)
            el.attrs = {}
            el['href'] = href
        item['summary'] = str(soup)
    elif content_json.get('preview_text'):
        item['summary'] = content_json['preview_text']

    item['content_html'] = ''
    if content_json.get('primary_image'):
        item['_image'] = content_json['primary_image']['base_image_url']
        item['content_html'] += add_image(content_json['primary_image'])
    elif content_json.get('social_image'):
        item['_image'] = content_json['social_image']['base_image_url']

    if content_json.get('intro'):
        item['content_html'] += format_blocks(content_json['intro'])
        item['content_html'] += '<hr/>'

    if content_json.get('blocks'):
        item['content_html'] += format_blocks(content_json['blocks'])

    if content_json.get('chunks'):
        for chunk in content_json['chunks']:
            item['content_html'] += '<h3>{}</h3>'.format(chunk['headline'])
            if chunk.get('primary_image'):
                item['content_html'] += add_image(chunk['primary_image'])
            item['content_html'] += format_blocks(chunk['blocks'])
            item['content_html'] += '<hr/>'

    if content_json.get('outro'):
        item['content_html'] += format_blocks(content_json['outro'])
    return item


def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    content_id = ''
    m = re.search(r'([a-f0-9]+-[a-f0-9]+-[a-f0-9]+-[a-f0-9]+-[a-f0-9]+)\.html', split_url.path)
    if m:
        content_id = m.group(1)
    else:
        if '/local/' in split_url.path:
            m = re.search('/local/(.*)', split_url.path)
            content_id = m.group(1)
    if not content_id:
        logger.warning('unable to determine content id for ' + url)
        return None

    if '/newsletters/' in split_url.path:
        api_url = 'https://api.axios.com/api/render/newsletters/{}/'.format(content_id)
    elif 'local' in split_url.path:
        api_url = 'https://api.axios.com/api/render/audience-content/{}'.format(content_id)
    else:
        #api_url = 'https://www.axios.com/api/axios-web/get-story/by-id/{}'.format(content_id)
        api_url = 'https://api.axios.com/api/render/content/{}/'.format(content_id)

    content_json = utils.get_url_json(api_url)
    if not content_json:
        return None
    return get_item(content_json, args, save_debug)


def get_feed(args, save_debug=False):
    # Author feed: https://api.axios.com/api/render/stream/content/?author_username=mikeallen
    # Topic feed: https://api.axios.com/api/render/stream/content/?topic_slug=technology
    # All newsletters for the month: https://api.axios.com/api/render/newsletters/?audience_slug=national&year=2022&month=02
    if 'api.axios.com/feed' in args['url']:
        # https://api.axios.com/feed/
        # https://api.axios.com/feed/technology/
        return rss.get_feed(args, save_debug, get_content)

    newsletter = ''
    render_type = 'content'
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) == 0:
        api_url = 'https://api.axios.com/api/render/stream/content/?audience_slug=national&page_size=10'

    elif paths[0] == 'local':
        # Works for https://www.axios.com/local/columbus but not charlotte
        api_url = 'https://api.axios.com/api/render/stream/content/?audience_slug={}&page_size=10'.format(paths[1])

    elif paths[0] == 'authors':
        api_url = 'https://api.axios.com/api/render/stream/content/?author_username={}&page_size=10'.format(paths[1])

    elif paths[0] == 'newsletters':
        render_type = 'newsletters'
        if len(paths) > 1:
            newsletter = paths[1]
        dt = datetime.utcnow()
        api_url = 'https://api.axios.com/api/render/newsletters/?audience_slug=national&year={}&month={}'.format(dt.year, dt.month)
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        content_ids = []
        for it in api_json:
            # Check age
            if 'age' in args:
                dt = datetime.fromisoformat(it['published_date'].replace('Z', '+00:00'))
                item = {}
                item['_timestamp'] = dt.timestamp()
                if not utils.check_age(item, args):
                    continue
            content_ids.append(it['id'])

    else:
        if len(paths) == 1:
            api_url = 'https://api.axios.com/api/render/stream/content/?topic_slug={}&page_size=10'.format(paths[0])
        elif len(paths) == 2:
            api_url = 'https://api.axios.com/api/render/stream/content/?subtopic_slug={}&page_size=10'.format(paths[1])

    if not render_type == 'newsletters':
        api_json = utils.get_url_json(api_url)
        content_ids = api_json['results']

    n = 0
    items = []
    for id in content_ids:
        content_json = utils.get_url_json('https://api.axios.com/api/render/{}/{}/'.format(render_type, id))
        if not content_json:
            logger.warning('unable to get content for {} in {}'.format(id, args['url']))
            continue
        if newsletter:
            if content_json['subscription']['slug'] != newsletter:
                continue
        if save_debug:
            logger.debug('getting content for ' + content_json['permalink'])
            utils.write_file(content_json, './debug/debug.json')
        item = get_item(content_json, args, save_debug)
        if item:
          if utils.filter_item(item, args) == True:
            items.append(item)
            n += 1
            if 'max' in args:
                if n == int(args['max']):
                    break
    feed = utils.init_jsonfeed(args)
    feed['items'] = items.copy()
    return feed