import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_img_src(image, width=1200, height=800):
    if image['src'].get('id'):
        src = image['src']['id']
    elif image['src'].get('url'):
        src = image['src']['url']
    else:
        logger.warning('unknown image src')
        return ''
    w = image['width']
    h = image['height']
    if w > h and w > width:
        h = int(h * width / w)
        w = width
    elif h > w and h > height:
        w = int(w * height / h)
        h = height
    return 'https://static.wixstatic.com/media/' + src + '/v1/fill/w_' + str(w) + ',h_' + str(h) + ',al_c,q_85,enc_avif,quality_auto/' + src


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


def format_content(node):
    node_html = ''
    if node['type'] == 'TEXT':
        style = ''
        link = ''
        for dec in node['textData']['decorations']:
            if dec['type'] == 'LINK':
                link = dec['linkData']['link']['url']
            elif dec['type'] == 'ITALIC':
                style += 'text-decoration:italic; '
            elif dec['type'] == 'UNDERLINE':
                style += 'text-decoration:underline; '
            elif dec['type'] == 'BOLD':
                style += 'font-weight:bold; '
            elif dec['type'] == 'FONT_SIZE':
                style += 'font-size:{}{}; '.format(dec['fontSizeData']['value'], dec['fontSizeData']['unit'].lower())
            elif dec['type'] == 'COLOR':
                if dec['colorData'].get('foreground'):
                    style += 'color:' + dec['colorData']['foreground'] + '; '
                if dec['colorData'].get('background'):
                    style += 'background-color:' + dec['colorData']['background'] + '; '
            else:
                logger.warning('unhandled text decoration ' + dec['type'])
        if style:
            node_html = '<span style="' + style.strip() + '">' + node['textData']['text'] + '</span>'
        else:
            node_html = node['textData']['text']
        if link:
            node_html = '<a href="' + link + '" target="_blank">' + node_html + '</a>'
    elif node['type'] == 'PARAGRAPH':
        node_html += '<p'
        if 'textStyle' in node['paragraphData'] and 'textAlignment' in node['paragraphData']['textStyle'] and node['paragraphData']['textStyle']['textAlignment'] == 'CENTER':
            node_html += ' style="text-align:center;"'
        node_html += '>'
        for nd in node['nodes']:
            node_html += format_content(nd)
        node_html += '</p>'
    elif node['type'] == 'HEADING':
        node_html += '<h' + str(node['headingData']['level'])
        if 'textStyle' in node['headingData'] and 'textAlignment' in node['headingData']['textStyle'] and node['headingData']['textStyle']['textAlignment'] == 'CENTER':
            node_html += ' style="text-align:center;"'
        node_html += '>'
        for nd in node['nodes']:
            node_html += format_content(nd)
        node_html += '</h{}>'.format(node['headingData']['level'])
    elif node['type'] == 'IMAGE':
        node_html += utils.add_image(get_img_src(node['imageData']['image']))
    elif node['type'] == 'GALLERY':
        n = len(node['galleryData']['items'])
        gallery_images = []
        new_html = ''
        for i, it in enumerate(node['galleryData']['items']):
            img_src = get_img_src(it['image']['media'], 1800)
            thumb = get_img_src(it['image']['media'], 600)
            gallery_images.append({"src": img_src, "caption": "", "thumb": thumb})
            if i == 0:
                if n % 2 == 1:
                    # start with full width image if odd number of images
                    new_html += utils.add_image(get_img_src(it['image']['media']), link=img_src, fig_style='margin:1em 0 8px 0; padding:0;')
                else:
                    new_html += '<div style="display:flex; flex-wrap:wrap; gap:8px;"><div style="flex:1; min-width:360px;">' + utils.add_image(thumb, link=img_src, fig_style='margin:0; padding:0;') + '</div>'
            elif i == 1:
                if n % 2 == 1:
                    new_html += '<div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:8px;">'
                new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, link=img_src, fig_style='margin:0; padding:0;') + '</div>'
            else:
                new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, link=img_src, fig_style='margin:0; padding:0;') + '</div>'
        new_html += '</div>'
        if n > 2:
            gallery_url = config.server + '/gallery?images=' + quote_plus(json.dumps(gallery_images, separators=(',', ':')))
            node_html = '<h3><a href="' + gallery_url + '" target="_blank">View photo gallery</a></h3>'
        node_html += new_html
    elif node['type'] == 'VIDEO':
        if re.search(r'youtube\.com|youtu\.be', node['videoData']['video']['src']['url']):
            node_html += utils.add_embed(node['videoData']['video']['src']['url'])
        else:
            logger.warning('unhandled VIDEO node')
    elif node['type'] == 'HTML':
        if node['htmlData'].get('html'):
            soup = BeautifulSoup(node['htmlData']['html'], 'html.parser')
            if soup.blockquote and soup.blockquote.get('class'):
                if 'twitter-tweet' in soup.blockquote['class']:
                    links = soup.find_all('a')
                    node_html += utils.add_embed(links[-1]['href'])
                elif 'instagram-media' in soup.blockquote['class']:
                    node_html += utils.add_embed(soup.blockquote['data-instgrm-permalink'])
            elif soup.find(class_='adsbygoogle'):
                return node_html
        elif node['htmlData'].get('url'):
            node_html += utils.add_embed(node['htmlData']['url'])
        if not node_html:
            logger.warning('unhandled HTML node ' + node['htmlData']['html'])
    elif node['type'] == 'BLOCKQUOTE':
        node_html += '<blockquote style="' + config.blockquote_style + '">'
        for nd in node['nodes']:
            node_html += format_content(nd)
        node_html += '</blockquote>'
    elif node['type'] == 'BULLETED_LIST':
        node_html += '<ul>'
        for nd in node['nodes']:
            node_html += format_content(nd)
        node_html += '</ul>'
    elif node['type'] == 'ORDERED_LIST':
        node_html += '<ol>'
        for nd in node['nodes']:
            node_html += format_content(nd)
        node_html += '</ol>'
    elif node['type'] == 'LIST_ITEM':
        node_html += '<li>'
        for nd in node['nodes']:
            node_html += format_content(nd)
        node_html += '</li>'
    elif node['type'] == 'COLLAPSIBLE_LIST':
        for nd in node['nodes']:
            node_html += format_content(nd)
    elif node['type'] == 'COLLAPSIBLE_ITEM':
        node_html += '<details style="margin:1em 0;">'
        for nd in node['nodes']:
            node_html += format_content(nd)
        node_html += '</details>'
    elif node['type'] == 'COLLAPSIBLE_ITEM_TITLE':
        node_html += '<summary>'
        for nd in node['nodes']:
            node_html += format_content(nd)
        node_html += '</summary>'
        node_html = node_html.replace('<summary><p>', '<summary>').replace('</p></summary>', '</summary>')
    elif node['type'] == 'COLLAPSIBLE_ITEM_BODY':
        node_html += '<div style="margin-left:1em;">'
        for nd in node['nodes']:
            node_html += format_content(nd)
        node_html += '</div>'
    elif node['type'] == 'BUTTON':
        node_html += utils.add_button(node['buttonData']['link']['url'], node['buttonData']['text'], button_color=node['buttonData']['styles']['colors']['background'])
    elif node['type'] == 'DIVIDER':
        node_html += '<hr style="margin:1em 0;">'
    else:
        logger.warning('unhandled node type ' + node['type'])
    return node_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    api_url = split_url.scheme + '://' + split_url.netloc + '/_api/v1/access-tokens'
    access_tokens = utils.get_url_json(api_url)
    if not access_tokens:
        return None
    instance = ''
    for key, val in access_tokens['apps'].items():
        if val['intId'] == -666:
            instance = val['instance']
    if not instance:
        logger.warning('unknown access token instance from ' + api_url)
        return None

    api_url = split_url.scheme + '://' + split_url.netloc + '/_api/blog-frontend-adapter-public/v2/post-page/' + paths[-1] + '?postId=' + paths[-1] + '&translationsName=main&languageCode=en'
    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": instance,
        "commonconfig": quote_plus(json.dumps(site_json['commonconfig'], separators=(',', ':'))),
        "x-wix-brand": "wix"
    }
    api_json = utils.get_url_json(api_url, headers=headers)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    post_json = api_json['postPage']['post']
    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['url']['base'] + post_json['url']['path']
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['firstPublishedDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['lastPublishedDate'])
    item['date_modified'] = dt.isoformat()

    item['author'] = {
        "name": post_json['owner']['name']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['tags'] = []
    if api_json['postPage'].get('categories'):
        item['tags'] += [x['label'] for x in api_json['postPage']['categories']]
    if api_json['postPage'].get('tags'):
        item['tags'] += [x['label'] for x in api_json['postPage']['tags']]
    if post_json.get('hashtags'):
        item['tags'] += post_json['hashtags'].copy()

    if post_json.get('media'):
        if post_json['media'].get('wixMedia'):
            item['image'] = post_json['media']['wixMedia']['image']['url']
        elif post_json['media'].get('embedMedia'):
            item['image'] = post_json['media']['embedMedia']['thumbnail']['url']

    if post_json.get('excerpt'):
        item['summary'] = post_json['excerpt']

    item['content_html'] = ''
    for node in post_json['richContent']['nodes']:
        item['content_html'] += format_content(node)

    # api_url = split_url.scheme + '://' + split_url.netloc + '/_api/v2/dynamicmodel'
    # dynamic_model = utils.get_url_json(api_url)
    # if not dynamic_model:
    #     return None
    # if not dynamic_model['apps'].get(site_json['blog_app_def_id']):
    #     logger.warning('unable to determine instance for this blog {}://{}'.format(split_url.scheme, split_url.netloc))
    #     return None
    # instance = dynamic_model['apps'][site_json['blog_app_def_id']]['instance']
    # headers = {
    #     "accept": "application/json, text/plain, */*",
    #     "authorization": instance,
    #     "instance": instance,
    #     "locale": "en",
    #     "x-wix-site-revision": "2",
    #     "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.31"
    # }
    # api_url = '{}://{}/_api/communities-blog-node-api/_api/posts/content/{}?fieldsets=categories%2Cowner%2Clikes%2Ccontent%2Csubscriptions%2Ctags%2Cseo%2Ctranslations%2Curls'.format(split_url.scheme, split_url.netloc, paths[-1])
    # content_json = utils.get_url_json(api_url, headers=headers)
    # if not content_json:
    #     return None
    # if save_debug:
    #     utils.write_file(content_json, './debug/debug.json')

    # item = {}
    # item['id'] = content_json['id']
    # item['url'] = content_json['url']['base'] + content_json['url']['path']
    # item['title'] = content_json['title']

    # dt = datetime.fromisoformat(content_json['createdDate'].replace('Z', '+00:00'))
    # item['date_published'] = dt.isoformat()
    # item['_timestamp'] = dt.timestamp()
    # item['_display_date'] = utils.format_display_date(dt)
    # dt = datetime.fromisoformat(content_json['lastPublishedDate'].replace('Z', '+00:00'))
    # item['date_modified'] = dt.isoformat()

    # item['author'] = {"name": content_json['owner']['name']}

    # if content_json.get('tags'):
    #     item['tags'] = []
    #     for it in content_json['tags']:
    #         item['tags'].append(it['label'])

    # if content_json.get('heroImage') and content_json['heroImage'].get('src'):
    #     item['_image'] = get_img_src(content_json['heroImage'])
    # elif content_json.get('coverImage') and content_json['coverImage'].get('src'):
    #     item['_image'] = get_img_src(content_json['coverImage'])

    # if content_json.get('seoDescription'):
    #     item['summary'] = content_json['seoDescription']

    # item['content_html'] =  render_content_blocks(content_json['content']['blocks'], content_json['content']['entityMap'])
    # item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
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
