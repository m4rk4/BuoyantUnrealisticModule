import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def resize_img_src(img_src, width=1000):
    split_url = urlsplit(img_src)
    return '{}://{}{}?resize={}:*'.format(split_url.scheme, split_url.netloc, split_url.path, width)


def resize_image(image, width=1000):
    if image.get('hips_url'):
        img_src = image['hips_url']
    elif image.get('aws_url'):
        img_src = 'https://hips.hearstapps.com/' + image['aws_url'].replace('https://', '')
    else:
        img_src = 'https://hips.hearstapps.com/hmg-prod{}'.format(image['pathname'])
    if width < 0:
        return img_src
    return resize_img_src(img_src, width)


def image_caption(image, attribs=None):
    captions = []
    if attribs and attribs.get('caption'):
        captions.append(attribs['caption'])
    if image.get('metadata') and image['metadata'].get('caption'):
        if not image['metadata']['caption'] in captions:
            captions.append(image['metadata']['caption'])
    if image['image_metadata'].get('photo_credit'):
        if not image['image_metadata']['photo_credit'] in captions:
            captions.append(image['image_metadata']['photo_credit'])
    if image.get('source'):
        if not image['source']['title'] in captions:
            captions.append(image['source']['title'])
    if image.get('photographer'):
        if not image['photographer']['name'] in captions:
            captions.append(image['photographer']['name'])
    caption = ' | '.join(captions)
    if caption.lower() == 'hearst owned':
        caption = ''
    return caption


def add_image(image, attribs=None, gallery=False, add_desc=True):
    caption = image_caption(image, attribs)

    if image.get('metadata') and (image['metadata'].get('embed_image_link_url') or image['metadata'].get('slide_image_link_url')):
        if image['metadata'].get('embed_image_link_url'):
            link = image['metadata']['embed_image_link_url']
            if image['metadata'].get('embed_image_link_title'):
                link_title = image['metadata']['embed_image_link_title']
            else:
                link_title = 'View more photos'
        else:
            link = image['metadata']['slide_image_link_url']
            if image['metadata'].get('slide_image_link_title'):
                link_title = image['metadata']['slide_image_link_title']
            else:
                link_title = 'View more photos'
        if caption:
            caption += ' | '
        caption += '<a href="{}">{}</a>'.format(link, link_title)
    else:
        # Original image
        link = resize_image(image, -1)

    heading = ''
    desc = ''
    if add_desc:
        if image.get('metadata') and image['metadata'].get('custom_tag'):
            heading = '<div style="text-align:center; font-size:1.2em; font-weight:bold">{}</div>'.format(
                image['metadata']['custom_tag'].upper())
        if image['metadata'].get('headline'):
            desc += '<div style="text-align:center; font-size:1.3em; font-weight:bold">{}</div>'.format(image['metadata']['headline'])
        if image['metadata'].get('dek'):
            desc += image['metadata']['dek']
            #for blk in image['metadata']['dekDom']['children']:
                #desc += format_block(blk, None, netloc)

    if gallery:
        fig_style = 'margin:0; padding:8px;'
    else:
        fig_style = ''

    return utils.add_image(resize_image(image), caption, link=link, fig_style=fig_style, heading=heading, desc=desc)


def add_product(product, outer_table=True):
    product_html = '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
    # if outer_table:
        # product_html += '<table style="width:90%; margin-left:auto; margin-right:auto;">'

    # product_html += '<tr><td style="width:128px;"><img src="{}" style="width:128px;"/></td><td>'.format(resize_image(product['image'], 128))
    product_html += '<div style="flex:1; min-width:128px; max-width:160px; margin:auto;"><img src="{}" style="width:100%" /></div>'.format(resize_image(product['image'], 256))

    product_html += '<div style="flex:2; min-width:200px; margin:1em;">'
    if product.get('label'):
        product_html += '<div style="font-size:0.9em; font-weight:bold;">{}</div>'.format(product['label'])

    if product.get('custom_name'):
        name = product['custom_name']
    else:
        name = product['name']
        if product.get('custom_brand'):
            name = product['custom_brand'] + ' ' + name
    product_html += '<div style="font-size:1.2em; font-weight:bold;">{}</div>'.format(name)

    retailers = []
    if product.get('retailer') and product['retailer'].get('id'):
        retailers.append(product['retailer'])
    if product.get('retailers'):
        retailers += [it for it in product['retailers'] if it.get('id')]

    for retailer in retailers:
        price = ''
        if retailer.get('price_currency'):
            if retailer['price_currency'] == 'USD':
                price += '$'
            else:
                logger.warning('unhandled price currency ' + retailer['price_currency'])
        else:
            price += 'Shop'
        if product.get('custom_price'):
            price += product['custom_price']
        else:
            if retailer['price'] != '0.00':
                price += retailer['price']
        if retailer.get('display_name') and retailer['display_name']:
            price += ' at ' + retailer['display_name']
        else:
            price += ' at ' + retailer['retailer_name']
        # product_html += '<div style="width:fit-content; padding:4px; background-color:#59E7ED;"><a href="{}" style="text-decoration:none; color:black;">{}</a></div>'.format(retailer['url'], price)
        product_html += utils.add_button(retailer['url'], price, '#59E7ED', center=False)

    product_html += '</div></div>'
    # product_html += '</td></tr>'
    # if outer_table:
    #     product_html += '</table>'
    return product_html


def format_block(block, content, netloc):
    block_html = ''
    start_tag = ''
    end_tag = ''
    dropcap = ''
    if block['type'] == 'text':
        return block['data']
    elif block['type'] == 'tag':
        if block['name'] == 'a':
            if block['attribs'].get('href'):
                start_tag = '<a href="{}">'.format(block['attribs']['href'])
                end_tag = '</a>'

        elif block['name'] == 'p':
            if block.get('attribs') and block['attribs'].get('class') and 'body-dropcap' in block['attribs']['class']:
                if not dropcap:
                    dropcap = '<style>' + config.dropcap_style + '</style>'
                    start_tag = dropcap
                # dropcap = True
                start_tag += '<p class="dropcap">'
                # end_tag = '</p><span style="clear:left;"></span>'
                end_tag = '</p>'
            elif block.get('attribs') and block['attribs'].get('class') and 'body-tip' in block['attribs']['class']:
                start_tag = '<div style="font-weight:bold; padding:2em; border-top:1px solid black; border-bottom:1px solid black;">'
                end_tag = '</div>'
            elif block.get('attribs') and block['attribs'].get('class') and re.search(r'body-h\d', block['attribs']['class']):
                m = re.search(r'body-(h\d)', block['attribs']['class'])
                start_tag = '<{}>'.format(m.group(1))
                end_tag = '</{}>'.format(m.group(1))
            else:
                start_tag = '<p>'
                end_tag = '</p>'

        elif block['name'] == 'anchor-heading':
            m = re.search(r'body-(h\d)', block['attribs']['class'])
            if m:
                start_tag = '<{}>'.format(m.group(1))
                end_tag = '</{}>'.format(m.group(1))
            else:
                logger.warning('unhandled tag anchor-heading')

        elif block['name'] == 'image':
            #image = next((it for it in content['media'] if (it.get('id') and it['id'] == block['attribs']['mediaid'])), None)
            image = next((it for it in content['media'] if (it.get('id') and (it['id'] == block['attribs']['mediaid'] or it['id'] == block['attribs']['id']))), None)
            if image:
                return add_image(image, block['attribs'])
            else:
                logger.warning('unhandled image mediaid {}'.format(block['attribs']['mediaid']))

        elif block['name'] == 'gallery':
            if block['response'].get('galleryTitle'):
                if 'deals' in block['response']['galleryTitle']:
                    return ''
                else:
                    block_html += '<h2>' + block['response']['galleryTitle'] + '</h2>'
            block_html += '<div style="display:flex; flex-direction:row; flex-wrap:wrap; justify-content:center;">'
            #block_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
            for slide in block['response']['parsedSlides']:
                if not slide:
                    continue
                block_html += '<div style="flex:1; min-width:380px;">'
                if (slide.get('__typename') and slide['__typename'] == 'Image') or (slide.get('media_type') and slide['media_type'] == 'image'):
                    block_html += add_image(slide, gallery=True)
                elif (slide.get('__typename') and slide['__typename'] == 'Product') or slide.get('product_id'):
                    block_html += add_product(slide)
                else:
                    logger.warning('unhandled slide type ' + slide['__typename'])
                block_html += '</div>'
            block_html += '</div>'

        elif block['name'] == 'composite':
            gallery_images = []
            gallery_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
            for image in block['response']['media']:
                gallery_html += '<div style="flex:1; min-width:360px;">' + add_image(image) + '</div>'
                gallery_images.append({"src": resize_image(image, -1), "caption": image_caption(image), "thumb": resize_image(image, 640)})
            gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
            block_html += '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + gallery_html

        elif block['name'] == 'loop':
            return utils.add_video(block['attribs']['src'], 'video/mp4', '', block['attribs']['caption'])

        elif block['name'] == 'youtube' or block['name'] == 'twitter' or block['name'] == 'instagram':
            for blk in block['children']:
                block_html += format_block(blk, content, netloc)
            return utils.add_embed(block_html)

        elif block['name'] == 'mediaosvideo':
            media_json = utils.get_url_json('https://nitehawk.hearst.io/embeds/' + block['attribs']['embedid'])
            if media_json:
                caption = '<a href="{}">{}</a>'.format(media_json['metadata']['content_url']['prod'], media_json['media']['title'])
                video = next((it for it in media_json['media']['transcodings'] if '480p_sd' in it['preset_name']), None)
                if video:
                    block_html = utils.add_video(video['full_url'], 'video/mp4', media_json['media']['cropped_preview_image'], caption)
                else:
                    video = next((it for it in media_json['media']['transcodings'] if it['preset_name'] == 'apple_m3u8'), None)
                    if video:
                        block_html = utils.add_video(video['full_url'], 'application/x-mpegURL', media_json['media']['cropped_preview_image'], caption)
            if block_html:
                return block_html
            else:
                logger.warning('unhandled mediaosvideo block')

        elif block['name'] == 'iframe':
            src = block['attribs']['src']
            if src.startswith('//'):
                src = 'https:' + src
            return utils.add_embed(src)

        elif block['name'] == 'blockquote':
            for blk in block['children']:
                block_html += format_block(blk, content, netloc)
            return utils.add_blockquote(block_html, False)

        elif block['name'] == 'pullquote':
            for blk in block['children']:
                block_html += format_block(blk, content, netloc)
            return utils.add_pullquote(block_html)

        elif block['name'] == 'br' or block['name'] == 'hr':
            return '<{}/>'.format(block['name'])

        elif block['name'] == 'editoriallinks':
            block_html += '<h3>{}</h3><ul>'.format(block['response']['bonsaiLinkset']['title'])
            for it in block['response']['bonsaiLinkset']['links']:
                url = 'https://{}/{}'.format(netloc, it['content']['section']['slug'])
                if it['content'].get('subsection'):
                    url += '/{}'.format(it['content']['subsection']['slug'])
                url += '/a{}/{}'.format(it['content']['display_id'], it['content']['slug'])
                block_html += '<li><a href="{}">{}</a></li>'.format(url, it['content']['title'])
            block_html += '</ul>'
            return block_html

        elif block['name'] == 'product':
            product = block['response']['product']
            block_html += '<table style="width:90%; margin-left:auto; margin-right:auto; border:1px solid black;">'
            block_html += add_product(product, False)
            if product.get('statements'):
                block_html += '<tr><td colspan="2">'
                pros = []
                cons = []
                for it in product['statements'].values():
                    if it['type'] == 'pro':
                        pros.append(it)
                    elif it['type'] == 'con':
                        cons.append(it)
                    else:
                        logger.warning('unhandled statement type ' + it['type'])
                if pros:
                    block_html += '<strong>Pros</strong><ul>'
                    for it in pros:
                        block_html += '<li>{}</li>'.format(it['value'])
                    block_html += '</ul>'
                if cons:
                    block_html += '<strong>Cons</strong><ul>'
                    for it in cons:
                        block_html += '<li>{}</li>'.format(it['value'])
                    block_html += '</ul>'
                block_html += '</td></tr>'
            block_html += '</table>'
            return block_html

        elif block['name'] == 'vehicle':
            if content.get('alternative_body'):
                return '<div style="width:90%; margin-left:auto; margin-right:auto; padding:8px; border:1px solid black;">{}</div>'.format(content['alternative_body'])
            else:
                logger.warning('unhandled vehicle tag')

        elif re.search(r'^(insurance-marketplace(-plugin)?|poll|watch-next|recirculation|lotlinx-module-plugin)$', block['name']):
            return ''

        else:
            if not re.search(r'^(center|em|h\d|li|mark|ol|strong|sup|u|ul)$', block['name']):
                logger.debug('unhandled tag ' + block['name'])
            start_tag = '<{}>'.format(block['name'])
            end_tag = '</{}>'.format(block['name'])

    children_html = ''
    if block.get('children'):
        for blk in block['children']:
            children_html += format_block(blk, content, netloc)

    block_html += start_tag
    # if dropcap:
    #     if children_html.startswith('<'):
    #         block_html += re.sub(r'^(<[^>]+>)(.)', r'\1<span style="float:left; font-size:4em; line-height:0.8em;">\2</span>', children_html)
    #     elif children_html.startswith('“'):
    #         block_html += '<span style="float:left; font-size:4em; line-height:0.8em;">{}</span>{}'.format(children_html[:2], children_html[2:])
    #     else:
    #         block_html += '<span style="float:left; font-size:4em; line-height:0.8em;">{}</span>{}'.format(children_html[0], children_html[1:])
    # else:
    block_html += children_html
    block_html += end_tag
    return block_html


def get_gallery_content(soup, url, args, site_json, save_debug):
    el = soup.find('script', id='data-layer')
    if not el:
        logger.warning('unable to find data-layer in ' + url)
        return None
    data_json = json.loads(el.string)
    if save_debug:
        utils.write_file(data_json, './debug/debug.json')

    item = {}
    item['id'] = data_json['content']['id']
    item['url'] = data_json['canonicalUrl']
    item['title'] = data_json['content']['title']

    dt = datetime(int(data_json['content']['modifiedDate']['year']), int(data_json['content']['modifiedDate']['month']), int(data_json['content']['modifiedDate']['day']), int(data_json['content']['modifiedDate']['hour']), int(data_json['content']['modifiedDate']['minute']), tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {}
    if data_json['content'].get('authors'):
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(data_json['content']['authors']))
    else:
        item['author']['name'] = data_json['site']['name']

    if data_json['content'].get('tags'):
        item['tags'] = data_json['content']['tags'].copy()

    if data_json['content'].get('images') and data_json['content']['images']['lede']:
        item['_image'] = resize_img_src(data_json['content']['images']['lede']['url'])

    item['content_html'] = ''
    el = soup.find(class_=re.compile('-lede-image'))
    if el:
        it = el.find(class_='content-lede-image-credit')
        if it:
            caption = it.get_text()
        else:
            caption = ''
        it = el.find('img')
        if it:
            item['content_html'] += utils.add_image(resize_img_src(it['src']), caption)
        else:
            logger.warning('unhandled slideshow-lede-image in ' + item['url'])

    el = soup.find(class_='slideshow-desktop-dek')
    if el:
        item['content_html'] += el.decode_contents()

    el = soup.find(class_='listicle-intro')
    if el:
        item['content_html'] += el.decode_contents()

    split_url = urlsplit(url)
    gallery_json = utils.get_url_json('{}://{}/ajax/contentmedia/?id={}'.format(split_url.scheme, split_url.netloc, item['id']))
    if save_debug:
        utils.write_file(gallery_json, './debug/gallery.json')
    if not gallery_json:
        logger.warning('unable to get gallery content for ' + item['url'])

    for media in gallery_json:
        if media['data']['type'] == 'image':
            if media['data'].get('headline'):
                heading = '<div style="text-align:center; font-size:1.2em; font-weight:bold">{}</div>'.format(media['data']['headline'])
            else:
                heading = ''
            item['content_html'] += utils.add_image(resize_img_src(media['data']['media']['src']), media['data'].get('credit'), heading=heading, desc=media['data'].get('dek'))
        elif media['data']['type'] == 'embed':
            if media['data']['media'].get('headline'):
                item['content_html'] += '<div style="text-align:center; font-size:1.1em; font-weight:bold">{}</div>'.format(media['data']['media']['headline'])
            item['content_html'] += utils.add_embed(media['data']['media']['embed_url'])
            if media['data']['media'].get('dek'):
                item['content_html'] += media['data']['media']['dek']
        elif media['data']['type'] == 'product':
            item['content_html'] += '<table style="width:90%; margin-left:auto; margin-right:auto;">'
            item['content_html'] += '<tr><td style="width:128px;"><img src="{}" style="width:128px;"/></td>'.format(resize_img_src(media['data']['thumb']['src'], 128))
            item['content_html'] += '<td style="vertical-align:top;"><small>{}</small><br/><span style="font-size:1.1em; font-weight:bold;">{}</span>'.format(media['data']['product']['brand'], media['data']['product']['name'])
            item['content_html'] += '<div style="width:fit-content; padding:4px; background-color:#59E7ED;"><a href="{}" style="text-decoration:none; color:black;">{} at {}</a></div></td></tr></table>'.format(media['data']['product']['outboundLink'], media['data']['product']['price'], media['data']['product']['vendor'])
            item['content_html'] += media['data']['product']['description']

        else:
            logger.warning('unhandled gallery media type {} in {}'.format(media['data']['type'], item['url']))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        el = soup.find('meta', attrs={"name": "sailthru.contenttype"})
        if el and (el['content'] == 'gallery' or el['content'] == 'listicle'):
            return get_gallery_content(soup, url, args, site_json, save_debug)
        else:
            logger.warning('unhandled content in ' + url)
            return None

    next_data = json.loads(el.string)
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    content_json = next_data['props']['pageProps']['data']['content'][0]

    item = {}
    item['id'] = content_json['id']

    #item['url'] = next_data['HRST']['article']['canonicalUrl']
    item['url'] = next_data['props']['pageProps']['layoutContextProps']['canonicalUrl']

    if '</' in content_json['metadata']['index_title']:
        item['title'] = BeautifulSoup(content_json['metadata']['index_title'], 'html.parser').get_text()
    else:
        item['title'] = content_json['metadata']['index_title']

    dt = datetime.fromisoformat(content_json['originally_published_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(content_json['updated_at'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    authors = []
    if content_json.get('authors'):
        for it in content_json['authors']:
            authors.append(it['profile']['display_name'])
    elif content_json['metadata'].get('custom_editors'):
        authors = json.loads(content_json['metadata']['custom_editors'].replace('\'', '\"'))
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))


    item['tags'] = []
    if content_json.get('section'):
        item['tags'].append(content_json['section']['title'])
    if content_json.get('subsection'):
        item['tags'].append(content_json['subsection']['title'])
    if content_json.get('tags'):
        for it in content_json['tags']:
            item['tags'].append(it['title'])
    if not item.get('tags'):
        del item['tags']

    # Media roles:
    # SLIDE: 1,
    # SOCIAL: 2,
    # LEDE: 3,
    # BODY_MEDIA: 4,
    # MARQUEE: 5,
    # SPONSORED_MARQUEE: 6,
    # PREVIEW: 7,
    # ASSOCIATED_IMAGE: 8,
    # ASSOCIATED_VIDEO: 9,
    # CUSTOM_PREVIEW_IMAGE: 10,
    # CONTENT_TESTING: 11,
    # INDEX: 12,
    # SECTION_VIDEO: 13,
    # VIDEO_HUB: 14,
    # MEDIA_ROLE_PINTEREST: 16,
    # OFF_PLATFORM: 16,
    # CUSTOM_PROMO: 17,
    # FEED: 18,
    # GHOST_SLIDE: 19,
    # SPOTLIGHT_MARQUEE: 20,
    # EMBEDDED_CONTENT: 21
    if content_json.get('media'):
        image = next((it for it in content_json['media'] if it['role'] == 2), None)
        if image:
            item['_image'] = resize_image(image)
        else:
            item['_image'] = resize_image(content_json['media'][0])

    item['summary'] = content_json['metadata']['seo_meta_description']

    if 'embed' in args:
        item['content_html'] = '<div style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(split_url.netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}" target="_blank">Read</a></p></div></div><div>&nbsp;</div>'.format(config.server, quote_plus(item['url']))
        return item

    item['content_html'] = ''
    if content_json['metadata'].get('dek'):
        item['content_html'] = content_json['metadata']['dek']
        item['content_html'] = re.sub(r'^<p>', '<p><em>', item['content_html'])
        item['content_html'] = re.sub(r'</p>$', '</em></p>', item['content_html'])

    media = next((it for it in content_json['media'] if it['role'] == 3), None)
    if media:
        if media['media_type'] == 'image':
            item['content_html'] += add_image(image)
        elif media['media_type'] == 'file':
            # loop video
            image = next((it for it in content_json['media'] if (it['media_type'] == 'image' and it['role'] == 3)), None)
            if image:
                poster = resize_image(image)
            else:
                poster = ''
            item['content_html'] += utils.add_video('https://media.hearstapps.com/loop/video/{}'.format(media['filename']), 'video/mp4', poster)
        elif media['media_type'] == 'video':
            captions = []
            if media.get('title'):
                captions.append(media['title'])
            if media.get('credit'):
                captions.append(media['credit'])
            video_src = ''
            sources = []
            for it in media['transcodings']:
                if it.get('full_url'):
                    video_src = it['full_url']
                    if it.get('height'):
                        sources.append(it)
                    elif it.get('mapped_preset_name'):
                        m = re.search(r'_(\d+)p_(sd|hd)', it['mapped_preset_name'])
                        if m:
                            source = {}
                            source['full_url'] = it['full_url']
                            source['height'] = int(m.group(1))
            if sources:
                source = utils.closest_dict(sources, 'height', 480)
                video_src = source['full_url']
            if video_src:
                item['content_html'] += utils.add_video(video_src, 'video/mp4', media['croppedPreviewImage'], ' | '.join(captions))
            else:
                logger.warning('unknown video source in ' + item['url'])

    if next_data['props']['pageProps'].get('introductionDom'):
        for block in next_data['props']['pageProps']['introductionDom']['children']:
            item['content_html'] += format_block(block, content_json, split_url.netloc)

    if next_data['props']['pageProps'].get('introductoryTextDom'):
        for block in next_data['props']['pageProps']['introductoryTextDom']['children']:
            item['content_html'] += format_block(block, content_json, split_url.netloc)

    def sub_fractions(matchobj):
        if matchobj.group(1) == '0':
            num = ''
        else:
            num = matchobj.group(1)
        if matchobj.group(2) == '125':
            return num + ' 1/8'
        elif matchobj.group(2) == '25':
            return num + ' 1/4'
        elif matchobj.group(2) == '333':
            return num + ' 1/3'
        elif matchobj.group(2) == '375':
            return num + ' 3/8'
        elif matchobj.group(2) == '5':
            return num + ' 1/2'
        elif matchobj.group(2) == '625':
            return num + ' 5/8'
        elif matchobj.group(2) == '667':
            return num + ' 2/3'
        elif matchobj.group(2) == '75':
            return num + ' 3/4'
        elif matchobj.group(2) == '875':
            return num + ' 7/8'

    def format_time(time_str):
        t = []
        time = time_str.split(':')
        if time[0] != '00':
            t.append('{} hr'.format(int(time[0])))
        if time[1] != '00':
            t.append('{} min'.format(int(time[1])))
        if time[2] != '00':
            t.append('{} sec'.format(int(time[2])))
        return ', '.join(t)

    if content_json.get('recipe'):
        item['content_html'] += '<ul style="list-style-type: none; padding:0; margin:0;">'
        if content_json['recipe'].get('yields'):
            item['content_html'] += '<li>Yields: {}'.format(content_json['recipe']['yields'])
            if content_json['recipe'].get('yields_upper'):
                item['content_html'] += ' - {}'.format(content_json['recipe']['yields_upper'])
            if content_json['recipe'].get('yields_unit'):
                item['content_html'] += ' {}'.format(content_json['recipe']['yields_unit'])
            item['content_html'] += '</li>'
        if content_json['recipe'].get('calories_per_serving'):
            item['content_html'] += '<li>Calories per serving: {}</li>'.format(content_json['recipe']['calories_per_serving'])
        if content_json['recipe'].get('prep_time'):
            item['content_html'] += '<li>Prep time: {}</li>'.format(format_time(content_json['recipe']['prep_time']))
        if content_json['recipe'].get('process_time'):
            item['content_html'] += '<li>Process time: {}</li>'.format(format_time(content_json['recipe']['process_time']))
        if content_json['recipe'].get('total_time') and content_json['recipe']['total_time'] != '00:00:00':
            item['content_html'] += '<li>Total time: {}</li>'.format(format_time(content_json['recipe']['total_time']))
        item['content_html'] += '</ul>'

        item['content_html'] += '<h3>Ingredients</h3>'
        for group in content_json['recipe']['ingredient_groups']:
            if group.get('subhead'):
                item['content_html'] += '<h4 style="margin-bottom:0;">{}</h4>'.format(group['subhead'])
            item['content_html'] += '<ul>'
            for it in group['ingredients']:
                desc = re.sub(r'^<p>(.*)</p>$', r'\1', it['description'])
                if it.get('amount'):
                    item['content_html'] += '<li><b>' + re.sub(r'(\d+)\.(\d+)', sub_fractions, str(it['amount']))
                    if it.get('unit'):
                        item['content_html'] += ' ' + it['unit']
                    item['content_html'] += '</b> {}</li>'.format(desc)
                else:
                    item['content_html'] += '<li>{}</li>'.format(desc)
            item['content_html'] += '</ul>'

    if next_data['props']['pageProps'].get('instructionsDom'):
        item['content_html'] += '<h3>Instructions</h3>'
        for ins in next_data['props']['pageProps']['instructionsDom']:
            if ins.get('subhead'):
                item['content_html'] += '<h4 style="margin-bottom:0;">{}</h4>'.format(ins['subhead'])
            for block in ins['steps']['children']:
                item['content_html'] += format_block(block, content_json, split_url.netloc)

    if next_data['props']['pageProps'].get('bodyDom'):
        for block in next_data['props']['pageProps']['bodyDom']['children']:
            if block['type'] == 'tag' and block['name'] == 'product-summary-view':
                item['content_html'] += '<table style="width:90%; margin-left:auto; margin-right:auto; border-collapse:collapse;">'
                for product in next_data['props']['pageProps']['products'].values():
                    if product['__typename'] == 'ContentProduct':
                        item['content_html'] += add_product(product, False)
                item['content_html'] += '</table>'
            else:
                item['content_html'] += format_block(block, content_json, split_url.netloc)

    if next_data['props']['pageProps'].get('slides'):
        gallery_images = []
        gallery_html = ''
        if next_data['props']['pageProps']['displayType'] == 'gallery':
            gallery_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
        for slide in next_data['props']['pageProps']['slides']:
            if slide['media_type'] == 'image':
                if next_data['props']['pageProps']['displayType'] == 'listicle':
                    if slide['metadata'].get('headline'):
                        item['content_html'] += '<h2>' + slide['metadata']['headline'] + '</h2>'
                    item['content_html'] += add_image(slide, add_desc=False)
                    if slide['metadata'].get('dekDom') and slide['metadata']['dekDom'].get('children'):
                        for block in slide['metadata']['dekDom']['children']:
                            item['content_html'] += format_block(block, content_json, split_url.netloc)
                elif next_data['props']['pageProps']['displayType'] == 'gallery':
                    gallery_html += '<div style="flex:1; min-width:360px;">' + add_image(slide, add_desc=False)
                    dek = ''
                    if slide['metadata'].get('dekDom') and slide['metadata']['dekDom'].get('children'):
                        for block in slide['metadata']['dekDom']['children']:
                            dek += format_block(block, content_json, split_url.netloc)
                    gallery_html += dek + '</div>'
                    caption = image_caption(slide)
                    if caption:
                        if dek:
                            dek += '<div><small>' + caption + '</small></div>'
                        else:
                            dek = caption
                    gallery_images.append({"src": resize_image(slide, -1), "caption": dek, "thumb": resize_image(slide, 640)})
        if gallery_html:
            gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
            item['content_html'] += '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + gallery_html

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(args['url'])
    page_html = utils.get_url_html(args['url'])
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + args['url'])
        return None

    next_data = json.loads(el.string)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    urls = []
    for feedinfo in next_data['props']['pageProps']['data']['feedInfo']:
        for block in feedinfo['blocks']:
            for feed in block['feeds']:
                for res in feed['resources']:
                    url = 'https://{}/{}'.format(split_url.netloc, res['section']['slug'])
                    if res.get('subsection'):
                        url += '/{}'.format(res['subsection']['slug'])
                    url += '/a{}/{}'.format(res['display_id'], res['slug'])
                    urls.append(url)

    n = 0
    feed_items = []
    for url in urls:
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    # if feed_title:
    #     feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed