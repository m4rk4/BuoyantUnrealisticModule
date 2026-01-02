import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, unquote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    params = parse_qs(split_url.query)
    if params.get('id'):
        return split_url.scheme + '://' + split_url.netloc + split_url.path + 'id=' + params['id'][0] + '&width=' + str(width)
    else:
        return split_url.scheme + '://' + split_url.netloc + split_url.path + '?width=' + str(width)


def render_content(content):
    content_html = ''
    end_tag = ''
    has_dropcap = False
    if content['type'] == 'text':
        def rebelmouse_proxy_image(matchobj):
            return utils.add_image(matchobj.group(1))
        text = re.sub(r'\[rebelmouse-proxy-image (https://[^\s]+) [^\]]+]', rebelmouse_proxy_image, content['text'])
        content_html += text

    elif content['type'] == 'tag':
        if content['name'] == 'p':
            if content.get('attributes') and content['attributes'].get('class'):
                # classes = content['attributes']['class'].split(' ')
                if re.search(r'shortcode-media-rebelmouse-image', content['attributes']['class']):
                    img_src = ''
                    img_link = ''
                    captions = []
                    for child in content['children']:
                        if not child.get('name'):
                            content_html += render_content(child)
                        elif child['name'] == 'rebelmouse-image':
                            if child['attributes'].get('crop_info'):
                                crop_info = json.loads(unquote_plus(child['attributes']['crop_info']))
                                images = []
                                for key, val in crop_info['thumbnails'].items():
                                    m = re.search(r'^(\d+)x$', key)
                                    if m:
                                        image = {}
                                        image['width'] = int(m.group(1))
                                        image['src'] = val
                                        images.append(image)
                                if images:
                                    image = utils.closest_dict(images, 'width', 1000)
                                    img_src = image['src']
                            if not img_src:
                                img_src = 'https://assets.rbl.ms/{}/origin.jpg'.format(child['attributes']['iden'])
                        elif child['name'] == 'a':
                            img_link = child['attributes']['href']
                            for nino in child['children']:
                                if nino['name'] == 'rebelmouse-image':
                                    if nino['attributes'].get('crop_info'):
                                        crop_info = json.loads(unquote_plus(nino['attributes']['crop_info']))
                                        images = []
                                        for key, val in crop_info['thumbnails'].items():
                                            m = re.search(r'(\d+)x$', key)
                                            if m:
                                                image = {}
                                                image['width'] = int(m.group(1))
                                                image['src'] = val
                                                images.append(image)
                                        if images:
                                            image = utils.closest_dict(images, 'width', 1000)
                                            img_src = image['src']
                                    if not img_src:
                                        img_src = 'https://assets.rbl.ms/{}/origin.jpg'.format(nino['attributes']['iden'])
                        elif child.get('attributes') and child['attributes'].get('class'):
                            child_classes = child['attributes']['class'].split(' ')
                            caption = ''
                            if 'media-caption' in child_classes:
                                for nino in child['children']:
                                    caption += render_content(nino)
                                if caption:
                                    captions.append(caption)
                            elif 'media-photo-credit' in child_classes:
                                for nino in child['children']:
                                    caption += render_content(nino)
                                if caption:
                                    captions.append(caption)
                    return utils.add_image(img_src, ' | '.join(captions), link=img_link)

                elif re.search(r'pull-quote', content['attributes']['class']):
                    quote = ''
                    author = ''
                    for child in content['children']:
                        quote += render_content(child)
                    m = re.search(r'“([^”]+)”\s?—(.+)$', quote)
                    if m:
                        quote = m.group(1)
                        author = m.group(2)
                    return utils.add_pullquote(quote, author)

                elif re.search(r'drop-caps', content['attributes']['class']):
                    has_dropcap = True

            content_html += '<p>'
            end_tag = 'p'

        elif content['name'] == 'span':
            if content.get('children'):
                logger.warning('unhandled span tag')

        elif content['name'] == 'hr' or content['name'] == 'br':
            content_html += '<{}/>'.format(content['name'])

        elif content['name'] == 'a':
            if content['attributes'].get('href'):
                content_html += '<a href="{}">'.format(content['attributes']['href'])
                end_tag = 'a'

        elif content['name'] == 'img':
            content_html += '<img src="{}" style="width:100%;"/>'.format(content['attributes']['src'])

        elif content['name'] == 'div':
            skip_div = False
            if content.get('attributes') and content['attributes'].get('class'):
                if re.search(r'newsroomBlockQuoteContainer', content['attributes']['class']):
                    quote = ''
                    cite = ''
                    for child in content['children']:
                        if re.search(r'newsroomBlockQuote', child['attributes']['class']):
                            for nino in child['children']:
                                quote += render_content(nino)
                        elif re.search(r'newsroomBlockQuoteAuthorContainer', child['attributes']['class']):
                            for nino in child['children']:
                                cite += render_content(nino)
                    return utils.add_pullquote(quote, cite)

                elif re.search(r'horizontal-rule', content['attributes']['class']):
                    content_html += '<hr/>'
                    skip_div = True

                elif re.search(r'embed-media|redactor-editor', content['attributes']['class']):
                    skip_div = True

                elif re.search(r'ieee-editors-note', content['attributes']['class']):
                    content_html += '<h4><em>Editor\'s note</em></h4>'
                    skip_div = True

                elif re.search(r'ieee-(factbox|sidebar)-', content['attributes']['class']):
                    sidebar = ''
                    for child in content['children']:
                         sidebar += render_content(child)
                    return utils.add_blockquote(sidebar)

                elif re.search(r'flourish-embed', content['attributes']['class']):
                    embed_src = utils.clean_url('https://flo.uri.sh/' + content['attributes']['data-src']) + '/embed?auto=1'
                    content_html += utils.add_embed(embed_src)
                    skip_div = True

            elif content.get('attributes') and content['attributes'].get('style') and re.search(r'page-break-after', content['attributes']['style']):
                skip_div = True

            if content.get('children'):
                for child in content['children']:
                    if child.get('attributes') and child['attributes'].get('data-card') and child['attributes']['data-card'] == 'facebook':
                        for nino in child['children']:
                            if nino.get('attributes') and nino['attributes'].get('data-href'):
                                return utils.add_embed(nino['attributes']['data-href'])

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
                                if nino.get('text') and re.search(r'shortcode-Ad|embed-dontmiss|embed-latest|embed-mostread', nino['text'], flags=re.I):
                                    continue
                                # print(nino)
                                if nino['name'] == 'rebelmouse-image':
                                    crop_info = json.loads(unquote_plus(nino['attributes']['crop_info']))
                                    images = []
                                    for key, val in crop_info['thumbnails'].items():
                                        m = re.search(r'^(\d+)x$', key)
                                        if m:
                                            image = {}
                                            image['width'] = int(m.group(1))
                                            image['src'] = val
                                            images.append(image)
                                    if images:
                                        image = utils.closest_dict(images, 'width', 1000)
                                        img_src = image['src']
                                    if not img_src:
                                        img_src = 'https://assets.rbl.ms/{}/origin.jpg'.format(nino['attributes']['iden'])
                                        #img_src = resize_image(crop_info['thumbnails']['origin'])
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
                                elif nino['name'] == 'div' and nino['attributes'].get('class') and re.search(r'flourish-embed', nino['attributes']['class']):
                                    embed_src = utils.clean_url('https://flo.uri.sh/' + nino['attributes']['data-src']) + '/embed?auto=1'
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
                        if child['attributes'].get('layout') == 'slideshow':
                            content_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                        elif child['attributes'].get('use_pagination') == True:
                            content_html += '<hr/>'
                        if child.get('children'):
                            for nino in child['children']:
                                content_html += render_content(nino)
                                if child['attributes'].get('use_pagination'):
                                    content_html += '<hr/>'
                        if child['attributes'].get('layout') == 'slideshow':
                            content_html += '</div>'
                            gallery_images = []
                            for el in BeautifulSoup(content_html, 'html.parser').select('div:has(> figure)'):
                                if el.figure.img:
                                    img_src = resize_image(el.figure.img['src'], 1200)
                                    thumb = resize_image(el.figure.img['src'], 640)
                                    if el.figure.figcaption:
                                        caption = el.figure.figcaption.small.decode_contents()
                                    else:
                                        caption = ''
                                    # TODO: extract desc
                                    gallery_images.append({"src": img_src, "caption": caption, "thumb": thumb})
                                    img_src = ''
                            if len(gallery_images) > 0:
                                gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
                                content_html = '<h3><a href="{}" target="_blank">View slideshow</a></h3>'.format(gallery_url) + content_html

                    else:
                        logger.warning('unhandled particle child ' + child['name'])

                particle_html = ''
                desc = ''
                if is_slideshow:
                    particle_html += '<div style="flex:1; min-width:360px;">'
                if headline:
                    if is_slideshow:
                        desc += '<h3>' + headline + '</h3>'
                    else:
                        particle_html += '<h3>' + headline + '</h3>'
                if img_src:
                    captions = []
                    if caption:
                        captions.append(caption)
                    if credit:
                        captions.append(credit)
                    if is_slideshow:
                        if body:
                            desc += body
                        particle_html += utils.add_image(img_src, ' | '.join(captions), link=img_link, desc=desc)
                    else:
                        particle_html += utils.add_image(img_src, ' | '.join(captions), link=img_link)
                if embed_src:
                    particle_html += utils.add_embed(embed_src)
                if body and not is_slideshow:
                    particle_html += body
                if is_slideshow:
                    particle_html += '</div>'
                if content.get('attributes') and content['attributes'].get('class_name') and re.search(r'ieee-(factbox|sidebar)-', content['attributes']['class_name']):
                    content_html += utils.add_blockquote(particle_html)
                elif content.get('attributes') and content['attributes'].get('class_name') and re.search(r'ieee-pullquote-', content['attributes']['class_name']):
                    content_html += utils.add_pullquote(particle_html)
                else:
                    content_html += particle_html
                return content_html
                
        elif content['name'] == 'assembler':
            if content['attributes']['use_pagination']:
                content_html += '<hr/>'
            for child in content['children']:
                content_html += render_content(child)
                if content['attributes']['use_pagination']:
                    content_html += '<hr/>'
            return content_html

        elif content['name'] == 'center' and content.get('children') and content['children'][0]['type'] == 'tag' and content['children'][0]['name'] == 'iframe':
            pass

        elif content['name'] == 'script':
            pass

        else:
            # Filter out captions/credits for some embeds
            if content.get('attributes') and content['attributes'].get('class'):
                if re.search(r'-caption|-credit', content['attributes']['class']):
                    return content_html
            content_html += '<{}>'.format(content['name'])
            end_tag = content['name']

    if content.get('children'):
        child_content = ''
        for child in content['children']:
            child_content += render_content(child)
        if has_dropcap:
            if not child_content.startswith('<'):
                child_content = '<span style="float:left; font-size:4em; line-height:0.8em;">{}</span>{}'.format(child_content[0], child_content[1:])
        content_html += child_content
    if end_tag:
        content_html += '</{}>'.format(end_tag)
        if has_dropcap:
            content_html += '<div style="clear:left;">'
    return content_html


def format_shortcodes(content_html, shortcodes, shortcodes_params, in_gallery=False):
    for key, val in shortcodes.items():
        if key.startswith('[rebelmouse-image'):
            img_src = ''
            m = re.search(r'data-rm-shortcode-id="([^"]+)', val)
            if m and m.group(1) in shortcodes_params:
                params = shortcodes_params[m.group(1)]
                crop_info = json.loads(unquote_plus(params['crop_info']))
                images = []
                for k, v in crop_info['thumbnails'].items():
                    if k.endswith('x'):
                        images.append({"src": v, "width": int(k.strip('x'))})
                if images:
                    img_src = utils.closest_dict(images, 'width', 1000)['src']
                else:
                    img_src = crop_info['image']
                captions = []
                if params.get('caption'):
                    captions.append(params['caption'])
                if params.get('photo_credit'):
                    captions.append(params['photo_credit'])
            else:
                m = re.search(r'crop_info="([^"]+)', val)
                if m:
                    crop_info = json.loads(unquote_plus(m.group(1)))
                    images = []
                    for k, v in crop_info['thumbnails'].items():
                        if k.endswith('x'):
                            images.append({"src": v, "width": int(k.strip('x'))})
                    if images:
                        img_src = utils.closest_dict(images, 'width', 1000)['src']
                    else:
                        img_src = crop_info['image']
                    captions = []
                    m = re.search(r'caption="([^"]+)', val)
                    if m:
                        captions.append(m.group(1))
                    m = re.search(r'photo_credit="([^"]+)', val)
                    if m:
                        captions.append(m.group(1))
            if img_src:
                if in_gallery:
                    new_html = utils.add_image(img_src, ' | '.join(captions), fig_style="margin:0; padding:0;")
                else:
                    new_html = utils.add_image(img_src, ' | '.join(captions))
                content_html = content_html.replace(key, new_html)
            else:
                logger.warning('unhandled rebelmouse-image shortcode ' + val)
        elif key.startswith('[youtube'):
            m = re.search(r'src="([^"]+)', val)
            new_html = utils.add_embed(m.group(1))
            content_html = content_html.replace(key, new_html)
        elif key.startswith('[twitter_embed'):
            m = re.search(r'https://twitter\.com/[^\s]+', key)
            new_html = utils.add_embed(m.group(0))
            content_html = content_html.replace(key, new_html)
        elif key.startswith('[instagram'):
            m = re.search(r'https://www\.instagram\.com/[^\s]+', key)
            new_html = utils.add_embed(m.group(0))
            content_html = content_html.replace(key, new_html)
        elif key.startswith('[shortcode-InText-Newsletter'):
            content_html = content_html.replace(key, '')
        else:
            content_html = content_html.replace(key, val)
    return content_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    article_html = utils.get_url_html(url)
    soup = BeautifulSoup(article_html, 'lxml')
    el = soup.find('script', string=re.compile(r'REBELMOUSE_BOOTSTRAP_DATA'))
    if not el:
        logger.warning('unable to determine bootstrap url in ' + url)
        return None
    s = el.string.strip().replace('true', '1').replace('false', '""')
    if s.endswith(';'):
        s = s[:-1]
    n = s.find('{')
    bootstrap_data = json.loads(s[n:])
    if save_debug:
        utils.write_file(bootstrap_data, './debug/bootstrap.json')
    if 'bootstrap_path' in site_json:
        bootstrap_path = site_json['bootstrap_path'].replace('SITE_ID', str(bootstrap_data['site']['id'])).replace('RESOURCE_ID', bootstrap_data['resourceId']).replace('PATH_PARAMS', quote_plus(json.dumps(bootstrap_data['pathParams'], separators=(',', ':')))).replace('PAGE_PATH', quote_plus(bootstrap_data['path'])).replace('POST_ID', str(bootstrap_data['post']['id']))
    elif bootstrap_data.get('fullBootstrapUrl'):
        bootstrap_path = bootstrap_data['fullBootstrapUrl'].replace('\\u0026', '&')
    else:
        bootstrap_path = '/res/bootstrap/data.js?site_id=' + bootstrap_data['site']['id'] + '&resource_id=' + bootstrap_data['resourceId'] + '&path_params=' + quote_plus(json.dumps(bootstrap_data['pathParams'], separators=(',', ':'))) + '&warehouse10x=1&override_device=desktop&post_id=' + bootstrap_data['post']['id']
    bootstrap_url = split_url.scheme + '://' + split_url.netloc + bootstrap_path
    print(bootstrap_url)
    bootstrap_json = utils.get_url_json(bootstrap_url)

    post_json = bootstrap_json['post']
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['post_url']
    if post_json.get('og_title'):
        item['title'] = post_json['og_title']
    else:
        item['title'] = BeautifulSoup(post_json['headline'], 'html.parser').get_text()

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
        if len(authors) == 1:
            item['author']['name'] = authors[0]
        else:
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if post_json.get('section'):
        item['tags'].append(post_json['section']['title'])
    if post_json.get('public_tags'):
        item['tags'] += post_json['public_tags'].copy()
    if not item.get('tags'):
        del item['tags']

    if post_json.get('sharing_post_texts') and post_json['sharing_post_texts'].get('variables') and post_json['sharing_post_texts']['variables'].get('Post_Description'):
        item['summary'] = post_json['sharing_post_texts']['variables']['Post_Description']
    elif post_json.get('sharing_post_texts') and post_json['sharing_post_texts'].get('facebook_desc'):
        item['summary'] = post_json['sharing_post_texts']['facebook_desc']
    elif post_json.get('meta_description'):
        item['summary'] = post_json['meta_description']
    elif post_json.get('og_description'):
        item['summary'] = post_json['og_description']
    elif post_json.get('description'):
        item['summary'] = post_json['description']

    item['content_html'] = ''

    if post_json.get('subheadline'):
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['subheadline'])

    image_info = None
    if post_json.get('image_info'):
        image_info = post_json['image_info']
    elif post_json.get('teaser_image_info'):
        image_info = post_json['teaser_image_info']
    if image_info:
        images = []
        for key, val in image_info.items():
            if key.endswith('x'):
                images.append({"src": val, "width": int(key.strip('x'))})
        if images:
            item['image'] = utils.closest_dict(images, 'width', 1000)['src']
        elif 'origin' in image_info:
            item['image'] = image_info['origin']
        elif post_json.get('image_id'):
            item['image'] = 'https://assets.rbl.ms/' + str(post_json['image_id']) + '/origin.png'
        elif post_json.get('image_thumb'):
            item['image'] = post_json['image_thumb']

    if post_json.get('video'):
        if post_json.get('video_provider') and post_json['video_provider'] == 'youtube':
            item['content_html'] += utils.add_embed(post_json['video'])
        else:
            query = parse_qs(urlsplit(post_json['video']).query)
            if query.get('jwplayer_video_url'):
                item['content_html'] += utils.add_embed(query['jwplayer_video_url'][0])
            elif query.get('video_url'):
                embed_args = {}
                if post_json.get('photo_caption'):
                    embed_args['caption'] = re.sub(r'</?p>', '', post_json['photo_caption'])
                item['content_html'] += utils.add_embed(query['video_url'][0], embed_args)
            else:
                logger.warning('unhandled video {} in {}'.format(post_json['video'], item['url']))
    elif 'image' in item:
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
        item['content_html'] += utils.add_image(item['image'], ' | '.join(captions))

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if post_json.get('structurized_content'):
        content_json = json.loads(post_json['structurized_content'])
        if save_debug:
            utils.write_file(content_json, './debug/content.json')
        for child in content_json['children']:
            item['content_html'] += render_content(child)
        body = None
    elif post_json.get('listicle') and post_json['listicle'].get('items'):
        if post_json.get('description_before_listicle_filter'):
            body = BeautifulSoup(post_json['description_before_listicle_filter'], 'html.parser')
        else:
            body = BeautifulSoup(post_json['body'], 'html.parser')
        el = body.find('listicle')
        if el:
            new_html = ''
            for it in post_json['listicle']['items_order']:
                listicle = post_json['listicle']['items'][it[0]]
                if listicle.get('headline'):
                    new_html += '<h3>' + listicle['headline'] + '</h3>'
                if len(it) == 1:                
                    if listicle.get('media'):
                        if listicle.get('media_shortcodes'):
                            new_html += format_shortcodes(listicle['media'], listicle['media_shortcodes'], listicle['media_shortcodes_params'])
                        else:
                            new_html += listicle['media']
                    if listicle.get('body'):
                        new_html += listicle['body']
                else:
                    new_html += '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:1em 0;">'
                    for i in it:
                        new_html += '<div style="flex:1; min-width:360px;">'
                        listicle = post_json['listicle']['items'][i]
                        if listicle.get('media'):
                            if listicle.get('media_shortcodes'):
                                new_html += format_shortcodes(listicle['media'], listicle['media_shortcodes'], listicle['media_shortcodes_params'], in_gallery=True)
                            else:
                                new_html += listicle['media']
                        new_html += '</div>'
                    new_html += '</div>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
    elif post_json.get('body'):
        body = BeautifulSoup(post_json['body'], 'html.parser')

    if body:
        if save_debug:
            utils.write_file(str(body), './debug/debug.html')
        has_dropcap = False
        for el in body.find_all(class_='horizontal-rule'):
            el.name = 'hr'
            el.attrs = {}
            el['style'] = 'margin:1em 0;'
        for el in body.find_all('p', class_='pull-quote'):
            new_html = utils.add_pullquote(el.decode_contents())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        for el in body.find_all('blockquote', recursive=False):
            if not el.get('class'):
                el['style'] = config.blockquote_style
                continue
            elif 'twitter-tweet' in el['class']:
                links = el.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
            elif 'tiktok-embed' in el['class']:
                new_html = utils.add_embed(el['cite'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled blockquote class ' + str(el['class']))
        for el in body.find_all('p', class_='drop-caps'):
            el['class'] = ['dropcap']
            if has_dropcap == False:
                item['content_html'] += '<style>' + config.dropcap_style + '</style>'
                has_dropcap = True
        for el in body.find_all(class_='shortcode-media'):
            for it in el.find_all(class_='image-media'):
                it.decompose()
            el.unwrap()
        for el in body.select('p:has(> a > img)'):
            if split_url.netloc not in el.img['src'] and 'assets.rbl.ms' not in el.img['src']:
                new_html = utils.add_image(el.img['src'], link=el.a['href'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
        for el in body.find_all(class_=['rm-embed', 'rm-shortcode']):
            it = el.find('iframe')
            if it:
                new_html = utils.add_embed(it['src'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled {} in {}'.format(el['class'], item['url']))
        for el in body.find_all('center', recursive=False):
            el.unwrap()
        for el in body.find_all('iframe', recursive=False):
            new_html = utils.add_embed(el['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        item['content_html'] += str(body)

    if post_json.get('original_url'):
        item['content_html'] += '<p><a href="{}">Read more at {}</a></p>'.format(post_json['original_url'], post_json['original_domain'])

    if post_json.get('shortcodes'):
        item['content_html'] = format_shortcodes(item['content_html'], post_json['shortcodes'], post_json['shortcodes_params'])
    elif post_json.get('media_shortcodes'):
        item['content_html'] = format_shortcodes(item['content_html'], post_json['media_shortcodes'], post_json['media_shortcodes_params'])

    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
