import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_img_src(image, width=1200, height=800):
    if image.get('src') and isinstance(image['src'], str) and image['src'].startswith('http'):
        return image['src']
    elif image.get('src') and isinstance(image['src'], dict):
        img_w = image['src']['width']
        img_h = image['src']['height']
        file_name = image['src']['file_name']
    elif image.get('metadata'):
        # Gallery items
        img_w = image['metadata']['width']
        img_h = image['metadata']['height']
        file_name = image['url']
    else:
        logger.warning('unknown image dimensions')
        return ''
    if img_w >= img_h:
        w = width
        h = int(w / img_w * img_h)
    else:
        h = height
        w = int(h / img_h * img_w)
    return 'https://static.wixstatic.com/media/{0}/v1/fill/w_{1},h_{2},al_c,q_85,usm_0.66_1.00_0.01,enc_auto/{0}'.format(file_name, w, h)


def apply_entity_styles(block, entity_map):
    if not block.get('entityRanges') and not block.get('inlineStyleRanges'):
        return block['text']
    indices = []
    ranges = block['entityRanges'].copy() + block['inlineStyleRanges'].copy()
    for range in ranges:
        range['start'] = range['offset']
        indices.append(range['start'])
        range['end'] = range['offset'] + range['length']
        indices.append(range['end'])
        if range.get('key'):
            entity = entity_map[str(range['key'])]
            if entity['type'] == 'LINK':
                range['start_tag'] = '<a href="{}">'.format(entity['data']['url'])
                range['end_tag'] = '</a>'
            elif entity['type'] == 'ANCHOR':
                pass
            else:
                logger.warning('unhandled entity type ' + entity['type'])
        elif range.get('style'):
            if range['style'] == 'UNDERLINE':
                range['start_tag'] = '<u>'
                range['end_tag'] = '</u>'
            elif range['style'] == 'BOLD':
                range['start_tag'] = '<b>'
                range['end_tag'] = '</b>'
            elif range['style'] == 'ITALIC':
                range['start_tag'] = '<i>'
                range['end_tag'] = '</i>'
            elif '"FG":' in range['style']:
                pass
            else:
                logger.warning('unhandled style ' + range['style'])
    # remove duplicates and sort
    indices = sorted(list(set(indices)))
    n = 0
    text = ''
    for i in indices:
        text += block['text'][n:i]
        start_ranges = list(filter(lambda ranges: ranges['start'] == i and ranges.get('start_tag'), ranges))
        start_ranges = sorted(start_ranges, key=lambda x: x['end'])
        for j, rng in enumerate(start_ranges):
            text += rng['start_tag']
            rng['order'] = i + j
        end_ranges = list(filter(lambda ranges: ranges['end'] == i and ranges.get('end_tag'), ranges))
        end_ranges = sorted(end_ranges, key=lambda x: (x['start'], x['order']), reverse=True)
        for rng in end_ranges:
            text += rng['end_tag']
        n = i
    text += block['text'][n:]
    return text


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    api_url = '{}://{}/_api/v2/dynamicmodel'.format(split_url.scheme, split_url.netloc)
    dynamic_model = utils.get_url_json(api_url)
    if not dynamic_model:
        return None
    if not dynamic_model['apps'].get(site_json['blog_app_def_id']):
        logger.warning('unable to determine instance for this blog {}://{}'.format(split_url.scheme, split_url.netloc))
        return None
    instance = dynamic_model['apps'][site_json['blog_app_def_id']]['instance']
    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": instance,
        "instance": instance,
        "locale": "en",
        "x-wix-site-revision": "2",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.31"
    }
    api_url = '{}://{}/_api/communities-blog-node-api/_api/posts/content/{}?fieldsets=categories%2Cowner%2Clikes%2Ccontent%2Csubscriptions%2Ctags%2Cseo%2Ctranslations%2Curls'.format(split_url.scheme, split_url.netloc, paths[-1])
    content_json = utils.get_url_json(api_url, headers=headers)
    if not content_json:
        return None
    if save_debug:
        utils.write_file(content_json, './debug/debug.json')

    item = {}
    item['id'] = content_json['id']
    item['url'] = content_json['url']['base'] + content_json['url']['path']
    item['title'] = content_json['title']

    dt = datetime.fromisoformat(content_json['createdDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(content_json['lastPublishedDate'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": content_json['owner']['name']}

    if content_json.get('tags'):
        item['tags'] = []
        for it in content_json['tags']:
            item['tags'].append(it['label'])

    if content_json.get('heroImage') and content_json['heroImage'].get('src'):
        item['_image'] = get_img_src(content_json['heroImage'])
    elif content_json.get('coverImage') and content_json['coverImage'].get('src'):
        item['_image'] = get_img_src(content_json['coverImage'])

    if content_json.get('seoDescription'):
        item['summary'] = content_json['seoDescription']

    item['content_html'] =  render_content_blocks(content_json['content']['blocks'], content_json['content']['entityMap'])
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def render_content_blocks(blocks, entity_map):
    content_html = ''
    for block in blocks:
        if block['type'] == 'unstyled':
            if block.get('text'):
                content_html += '<p>' + apply_entity_styles(block, entity_map) + '</p>'
        elif block['type'] == 'blockquote':
            content_html += utils.add_blockquote(apply_entity_styles(block, entity_map))
        elif block['type'] == 'unordered-list-item':
            content_html += '<ul><li>' + apply_entity_styles(block, entity_map) + '</li></ul>'
        elif block['type'] == 'ordered-list-item':
            content_html += '<ol><li>' + apply_entity_styles(block, entity_map) + '</li></ol>'
        elif 'header-' in block['type']:
            if block['type'] == 'header-one':
                tag = 'h1'
            elif block['type'] == 'header-two':
                tag = 'h2'
            elif block['type'] == 'header-three':
                tag = 'h3'
            elif block['type'] == 'header-four':
                tag = 'h4'
            elif block['type'] == 'header-five':
                tag = 'h5'
            elif block['type'] == 'header-six':
                tag = 'h6'
            content_html += '<{0}>{1}</{0}>'.format(tag, block['text'])
        elif block['type'] == 'atomic' and block.get('entityRanges'):
            for ent in block['entityRanges']:
                entity = entity_map[str(ent['key'])]
                if entity['type'] == 'wix-draft-plugin-image':
                    if entity['data'].get('metadata'):
                        caption = entity['data']['metadata'].get('caption')
                    else:
                        caption = ''
                    content_html += utils.add_image(get_img_src(entity['data']), caption)
                elif entity['type'] == 'wix-draft-plugin-gallery':
                    for it in entity['data']['items']:
                        content_html += utils.add_image(get_img_src(it), it['metadata'].get('title'))
                elif entity['type'] == 'wix-draft-plugin-video':
                    if entity['data'].get('src'):
                        content_html += utils.add_embed(entity['data']['src'])
                    else:
                        logger.warning('unhandled wix-draft-plugin-video')
                elif entity['type'] == 'wix-draft-plugin-divider':
                    content_html += '<hr/>'
                elif entity['type'] == 'wix-draft-plugin-link-button':
                    content_html += '<div style="text-align:center; padding:1em;"><span style="background-color:{}; padding:0.5em; border-radius:{}px;"><a href="{}" style="color:{};">&nbsp;{}&nbsp;</a></span></div>'.format(entity['data']['button']['design']['background'], entity['data']['button']['design']['borderRadius'], entity['data']['button']['settings']['url'], entity['data']['button']['design']['color'], entity['data']['button']['settings']['buttonText'])
                elif entity['type'] == 'wix-rich-content-plugin-collapsible-list':
                    for it in entity['data']['pairs']:
                        title = render_content_blocks(it['title']['blocks'], it['title']['entityMap'])
                        title = re.sub(r'^<p>(.*)</p>$', r'\1', title)
                        content_html += '<details><summary>{}</summary>{}</details>'.format(title, render_content_blocks(it['content']['blocks'], it['content']['entityMap']))
                elif entity['type'] == 'wix-draft-plugin-html':
                    if 'adsbygoogle' in entity['data']['src']:
                        continue
                    entity_soup = BeautifulSoup(entity['data']['src'], 'html.parser')
                    if entity_soup.blockquote and entity_soup.blockquote.get('class'):
                        if 'twitter-tweet' in entity_soup.blockquote['class']:
                            links = entity_soup.find_all('a')
                            content_html += utils.add_embed(links[-1]['href'])
                        elif 'instagram-media' in entity_soup.blockquote['class']:
                            content_html += utils.add_embed(entity_soup.blockquote['data-instgrm-permalink'])
                        else:
                            logger.warning('unhandled wix-draft-plugin-html blockquote class ' +  entity_soup.blockquote['class'])
                    elif entity_soup.iframe:
                        content_html += utils.add_embed(entity_soup.iframe['src'])
                    else:
                        logger.warning('unhandled wix-draft-plugin-html')
                else:
                    logger.warning('unhandled entity type ' + entity['type'])
        else:
            logger.warning('unhandled block type ' + block['type'])

    # Fix lists
    content_html = re.sub(r'</(ol|ul)><(ol|ul)>', '', content_html)
    return content_html


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
