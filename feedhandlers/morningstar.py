import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from markdown2 import markdown
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def render_body_content(content_elements, children='contentObject'):
    content_html = ''
    for element in content_elements:
        start_tag = ''
        end_tag = ''
        if not element.get('type'):
            if 'text' in element:
                content_html += element['text']
        elif element['type'] == 'text':
            content_html += element['content']
        elif element['type'] == 'a':
            if element.get('href'):
                start_tag = '<a href="{}">'.format(element['href'])
            elif element.get('attrs') and element['attrs'].get('url'):
                start_tag = '<a href="{}">'.format(element['attrs']['url'])
            end_tag = '</a>'
        elif element['type'] == 'h5':
            start_tag = '<h4>'
            end_tag = '</h4>'
        elif element['type'] == 'br':
            start_tag = '<br/>'
        elif element['type'] == 'img':
            if 'https://cts.businesswire.com/ct/CT' not in element['src']:
                content_html += utils.add_image(element['src'])
        elif element['type'] == 'div':
            content_html += render_body_content(element['contentObject'])
        else:
            start_tag = '<{}>'.format(element['type'])
            end_tag = '</{}>'.format(element['type'])
        if start_tag:
            content_html += start_tag
            if element.get(children):
                content_html += render_body_content(element[children], children)
            content_html += end_tag
    return content_html


def render_content(content_elements):
    content_html = ''
    for element in content_elements:
        start_tag = ''
        end_tag = ''
        if element['type'] == 'text':
            content_html += element['text']
        elif element['type'] == 'paragraph':
            start_tag = '<p>'
            end_tag = '</p>'
        elif element['type'] == 'a':
            if element.get('href'):
                start_tag = '<a href="{}">'.format(element['href'])
                end_tag = '</a>'
        elif element['type'] == 'interstitial-link':
            text = render_content(element['title'])
            if re.search(r'read more', text, flags=re.I):
                continue
            start_tag = '<a href="{}">{}'.format(element['href'], text)
            end_tag = '</a>'
        elif element['type'] == 'annotation':
            # https://www.morningstar.com/stocks/xnys/now/quote
            start_tag = '<a href="https://www.morningstar.com/stocks/{}/{}/quote">'.format(element['entity']['exchange'], element['entity']['ticker'])
            end_tag = '</a>'
        elif element['type'] == 'heading':
            if element['level'] == 'section':
                start_tag = '<h2>'
                end_tag = '</h2>'
            else:
                logger.warning('unhandled heading level ' + element['level'])
        elif element['type'] == 'b' or element['type'] == 'i':
            start_tag = '<{}>'.format(element['type'])
            end_tag = '</{}>'.format(element['type'])
        elif element['type'] == 'list':
            if element['listType'] == 'unordered':
                start_tag = '<ul>'
                end_tag = '</ul>'
            else:
                start_tag = '<ol>'
                end_tag = '</ol>'
        elif element['type'] == 'list-item':
            start_tag = '<li>'
            end_tag = '</li>'
        elif element['type'] == 'image':
            captions = []
            if element.get('caption'):
                captions.append(element['caption'])
            if element.get('credits'):
                captions.append(element['credits'])
            if element.get('copyright'):
                captions.append(element['copyright'])
            content_html += utils.add_image(element['src'], ' | '.join(captions))
        elif element['type'] == 'video':
            video = None
            streams = []
            for it in element['video']['streams']:
                if it['streamType'] == 'mp4':
                    it['streamType'] = 'video/mp4'
                    streams.append(it)
            if not streams:
                for it in element['video']['streams']:
                    if it['streamType'] == 'ts':
                        it['streamType'] = 'application/x-mpegURL'
                        streams.append(it)
            if streams:
                video = utils.closest_dict(streams, 'bitrate', 1500)
            if video:
                content_html += utils.add_video(video['url'], video['streamType'], element['video']['promoImage'], element['video']['headline']['title'])
            else:
                logger.warning('unhandled video element')
        elif element['type'] == 'embed':
            if element['providerName'] == 'Playfair':
                captions = []
                if element.get('title'):
                    captions.append(element['title'])
                if element.get('dataSource'):
                    captions.append(element['dataSource'])
                content_html += utils.add_image(element['imageUri'], ' | '.join(captions), link=element['uri'])
            else:
                logger.warning('unhandled embed provider ' + element['providerName'])
        else:
            logger.warning('unhandled element type ' + element['type'])
        if start_tag:
            content_html += start_tag
            if element.get('children'):
                content_html += render_content(element['children'])
            elif element.get('text'):
                content_html += element['text']
            content_html += end_tag
    return content_html


def get_special_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Chromium\";v=\"118\", \"Microsoft Edge\";v=\"118\", \"Not=A?Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-api-key": "Nrc2ElgzRkaTE43D5vA7mrWj2WpSBR35fvmaqfte"
    }
    api_url = 'https://www.morningstar.com/api/v1/dynamic-pages{}?includes=content,content.authors,content.category,content.featured_piece.featured_content.modular_blocks.card_deck.referenced_cards'.format(split_url.path)
    api_json = utils.get_url_json(api_url, headers=headers)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    content_json = api_json['content'][0]

    item = {}
    item['id'] = content_json['uid']
    item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, api_json['url'])
    item['title'] = content_json['title']

    authors = []
    for it in content_json['authors']:
        authors.append(it['title'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if api_json.get('description'):
        item['summary'] = api_json['description']

    item['content_html'] = ''
    if content_json.get('deck'):
        item['content_html'] += '<p><em>{}</em></p>'.format(api_json['deck'])

    if content_json.get('featured_image'):
        item['_image'] = content_json['featured_image']['url']
        item['content_html'] += utils.add_image(item['_image'])

    for piece in content_json['featured_piece']:
        for block in piece['featured_content']['modular_blocks']:
            if block.get('rte'):
                item['content_html'] += block['rte']['rich_text_editor']
            elif block.get('json_rte'):
                # print(block['json_rte']['_metadata']['uid'])
                item['content_html'] += render_body_content(block['json_rte']['rich_text_editor']['children'], 'children')
            elif block.get('image'):
                # TODO: captions?
                item['content_html'] += utils.add_image(block['image']['file']['url'])
            elif block.get('video'):
                item['content_html'] += utils.add_video(block['video']['file']['url'], block['video']['file']['content_type'], block['video']['thumbnail']['url'], block['video']['file'].get('title'))
            elif block.get('iframe'):
                # print(block['iframe']['_metadata']['uid'])
                iframe_html = ''
                soup = BeautifulSoup(block['iframe']['embedded_code'], 'html.parser')
                if soup.iframe and soup.iframe.get('src'):
                    if 'view.ceros.com/morningstar' in soup.iframe['src']:
                        if soup.iframe['src'].startswith('//'):
                            page_html = utils.get_url_html('https:' + soup.iframe['src'])
                        else:
                            page_html = utils.get_url_html(soup.iframe['src'])
                        m = re.search(r'docVersion: (\{.*?}),\n', page_html)
                        if m:
                            doc_json = json.loads(m.group(1))
                            if doc_json.get('editorPagesManifest') and doc_json['editorPagesManifest'][0].get('thumbnail'):
                                iframe_html = utils.add_image(doc_json['editorPagesManifest'][0]['thumbnail'], doc_json.get('seoMetaDescription'), link=soup.iframe['src'])
                    if iframe_html:
                        item['content_html'] += iframe_html
                    else:
                        logger.warning('unhandled iframe {} in {}'.format(block['iframe']['_metadata']['uid'], item['url']))
            elif block.get('card_deck'):
                for card in block['card_deck']['referenced_cards']:
                    if card.get('image') and card['image'].get('file'):
                        item['content_html'] += '<table><tr><td style="width:128px; vertical-align:top;"><img src="{}" style="width:100%;"/></td><td style="vertical-align:top;">'.format(card['image']['file']['url'])
                    else:
                        item['content_html'] += '<blockquote style="border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;">'
                    if card.get('url'):
                        item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;"><a href="{}://{}{}">{}</a></div>'.format(split_url.scheme, split_url.netloc, card['url'], card['title'])
                    elif card.get('button'):
                        item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(card['button']['url'], card['title'])
                    else:
                        item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;">{}</div>'.format(card['title'])
                    if card.get('core_definition'):
                        item['content_html'] += '<p>{}</p>'.format(card['core_definition'])
                    if card.get('long_form_definition'):
                        item['content_html'] += '<p>{}</p>'.format(markdown(card['long_form_definition']))
                    if card.get('description'):
                        item['content_html'] += '<p>{}</p>'.format(card['description'])
                    if card.get('image') and card['image'].get('file'):
                        item['content_html'] += '</td></tr></table>'
                    else:
                        item['content_html'] += '</blockquote>'
            elif block.get('inner_ad'):
                pass
            else:
                logger.warning('unhandled block {} in {}'.format(', '.join(block.keys()), item['url']))
    return item


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    if split_url.path.startswith('/news/'):
        api_url = 'https://www.morningstar.com/api/v2/' + '/'.join(paths[:3])
        key = 'article'
    elif split_url.path.startswith('/specials/'):
        return get_special_content(url, args, site_json, save_debug)
    else:
        api_url = 'https://www.morningstar.com/api/v2/stories?section=%2F{}&slug={}'.format(paths[0], paths[1])
        key = 'story'
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    story_json = api_json[key]['payload']
    item = {}
    item['id'] = story_json['id']
    if story_json.get('canonicalURL'):
        item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, story_json['canonicalURL'])
    else:
        item['url'] = url

    if story_json.get('headline'):
        item['title'] = story_json['headline']['title']
    elif story_json.get('title'):
        item['title'] = story_json['title']

    date = ''
    if story_json.get('firstPublishDate'):
        date = story_json['firstPublishDate']
    elif story_json.get('publishedDate'):
        date = story_json['publishedDate']
    if date:
        if date.endswith('Z'):
            dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
        else:
            dt = datetime.fromisoformat(date).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    if story_json.get('updatedOn'):
        date = story_json['updatedOn']
        if date.endswith('Z'):
            dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
        else:
            dt = datetime.fromisoformat(date).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    authors = []
    if story_json.get('credits') and story_json['credits'].get('by'):
        for it in story_json['credits']['by']:
            authors.append(it['name'])
    elif story_json.get('providerName'):
        authors.append(story_json['providerName'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if story_json.get('relatedSecurities'):
        item['tags'] = []
        for it in story_json['relatedSecurities']:
            item['tags'].append(it['name'])
            if it.get('ticker'):
                item['tags'].append(it['ticker'])

    item['content_html'] = ''
    if story_json.get('headline') and story_json['headline'].get('subtitle'):
        item['summary'] = story_json['headline']['subtitle']
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    if story_json.get('promoItems'):
        if story_json['promoItems'].get('image'):
            item['_image'] = story_json['promoItems']['image']['src']
            item['content_html'] += render_content([story_json['promoItems']['image']])
        elif story_json['promoItems'].get('video'):
            item['_image'] = story_json['promoItems']['video']['video']['promoImage']
            item['content_html'] += render_content([story_json['promoItems']['video']])

    if story_json.get('contentElements'):
        item['content_html'] += render_content(story_json['contentElements'])

    if story_json.get('body'):
        item['content_html'] += render_body_content(story_json['body'])

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    if len(paths) == 0:
        api_url = 'https://www.morningstar.com/api/v2/home'
    elif len(paths) == 1:
        api_url = 'https://www.morningstar.com/api/v2/sections/' + paths[0]

    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    stories = []
    if api_json.get('news'):
        stories += api_json['news']['items']
    if api_json.get('stories'):
        stories += api_json['stories']['payload']['results']

    n = 0
    feed_items = []
    for story in stories:
        if story.get('url'):
            story_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, story['url'])
        elif story.get('canonicalURL'):
            story_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, story['canonicalURL'])
        if save_debug:
            logger.debug('getting content for ' + story_url)
        item = get_content(story_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    #feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed