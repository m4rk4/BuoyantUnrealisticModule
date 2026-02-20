import copy, base64, html, json, math, pytz, re
import curl_cffi
from bs4 import BeautifulSoup, Comment, NavigableString
from datetime import datetime, timezone
from markdown2 import markdown
from urllib.parse import parse_qs, quote_plus, unquote_plus, urlsplit

import config, utils
from feedhandlers import hearsttv, rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, site_json, width=1200, height=800):
    # print(img_src)
    if site_json and 'resize_image' in site_json and site_json['resize_image'] == False:
        return img_src
    split_url = urlsplit(img_src)
    query = parse_qs(split_url.query)
    img_path = split_url.scheme + '://' + split_url.netloc
    if site_json and site_json.get('img_path'):
        img_src = img_src.replace(img_path, site_json['img_path'])
        img_path = site_json['img_path']
    img_path += split_url.path + '?'
    if query.get('uuid'):
        img_path += 'uuid=' + query['uuid'][0] + '&'
    if query.get('type'):
        img_path += 'type=' + query['type'][0] + '&'
    if site_json and site_json.get('use_webp'):
        # https://lazyadmin.nl/home-network/unifi-controller/
        img_src = re.sub(r'\.(jpe?g|png)(?!\.webp)', r'.\1.webp', img_src)
    if query.get('url'):
        # print(query)
        return img_src
    if query.get('w') or query.get('h') or query.get('fit'):
        return img_path + 'w=' + str(width)
    if query.get('width') or query.get('height'):
        return img_path + 'width=' + str(width)
    if query.get('resize') and (not query.get('crop') or site_json.get('ignore_resize_crop')):
        # print(query['resize'][0])
        m = re.search(r'(\d+|\*)(,|:)(\d+|\*)', unquote_plus(query['resize'][0]))
        if m:
            w = m.group(1)
            sep = m.group(2)
            h = m.group(3)
            if w.isnumeric() and h.isnumeric():
                height = math.floor(int(h) * width / int(w))
                return img_path + 'resize={}{}{}'.format(width, sep, height)
            elif w.isnumeric():
                return img_path + 'resize={}{}{}'.format(width, sep, h)
            elif h.isnumeric():
                return img_path + 'resize={}{}*'.format(width, sep)
        return img_path + 'width=' + str(width)
    if query.get('fit') and not query.get('crop'):
        # print(query['fit'][0])
        m = re.search(r'(\d+),(\d+)', unquote_plus(query['fit'][0]))
        if m:
            w = int(m.group(1))
            h = int(m.group(2))
            height = math.floor(h * width / w)
            return img_path + 'resize={},{}'.format(width, height)
    if query.get('im') and 'FitAndFill' in query['im'][0]:
        return re.sub(r'FitAndFill=\(\d+,\d+\)', 'FitAndFill({},)'.format(width), img_src)
    if not query and re.search(r';w=\d+;h=\d+', img_src):
        return re.sub(r';w=\d+;h=\d+', ';w={}'.format(width), img_src)
    m = re.search(r'GettyImages-\d+(-\d+x\d+[^\.]*)', split_url.path)
    if m:
        return img_src.replace(m.group(1), '')
    m = re.search(r'/(\d+)xAny/', split_url.path)
    if m:
        return img_src.replace(m.group(0), '/{}xAny/'.format(width))
    m = re.search(r'-\d+x\d+(\.jpg|\.png)', split_url.path)
    if m:
        if utils.url_exists(img_src.replace(m.group(0), m.group(1))):
            return img_src.replace(m.group(0), m.group(1))
    return img_src


def get_img_src(el, site_json, image_netloc, wp_media_url, width=1200, height=800):
    # print(el.name)
    img = None
    if el.name == 'a' and el.get('class') and 'spotlight' in el['class']:
        srcs = []
        for key, val in el.attrs.items():
            if key.startswith('data-src'):
                m = re.search(r'\d+', key)
                srcs.append({"width": int(m.group(0)), "src": val})
        if srcs:
            src = utils.closest_dict(srcs, 'width', width)
            return src['src']
        else:
            return el['href']
    elif el.name == 'a' and el.get('class') and 'ngg-fancybox' in el['class'] and el.get('data-src'):
        return el['data-src']
    if el.name == 'img':
        img = el
    elif el.img:
        img = el.img
    else:
        it = el.find(attrs={"style": re.compile(r'background-image:')})
        if it:
            m = re.search(r'background-image:\s*url\(\'([^\']+)', it['style'])
            if m:
                return m.group(1)
    if not img:
        logger.warning('unknown img in ' + str(el))
        return ''

    img_src = ''
    if img.get('data-lazy-srcset') and not img['data-lazy-srcset'].startswith('data:image/gif;base64'):
        img_src = utils.image_from_srcset(img['data-lazy-srcset'], width)

    elif img.get('data-lazy-load-srcset') and not img['data-lazy-load-srcset'].startswith('data:image/gif;base64'):
        img_src = utils.image_from_srcset(img['data-lazy-load-srcset'], width)

    elif img.get('data-srcset') and not img['data-srcset'].startswith('data:image/gif;base64'):
        img_src = utils.image_from_srcset(img['data-srcset'], width)

    elif img.get('srcset') and not img['srcset'].startswith('data:image/gif;base64'):
        img_src = utils.image_from_srcset(img['srcset'], width)

    elif site_json and site_json['module'] == 'wp_posts_v2' and ('args' not in site_json or 'skip_wp_media' not in site_json['args']) and not 'contenthub.com' in str(img):
        media_id = ''
        if el.get('data-image'):
            media_id = el['data-image']
        elif img.get('class'):
            m = re.search(r'wp-image-(\d+)', ' '.join(img['class']))
            if m:
                media_id = m.group(1)
        elif img.get('aria-describedby'):
            m = re.search(r'-(\d+)$', img['aria-describedby'])
            if m:
                media_id = m.group(1)
        if media_id:
            if wp_media_url:
                media_url = wp_media_url + media_id
                # media_json = utils.get_url_json(media_url, site_json=site_json)
            elif 'wpjson_path' in site_json and isinstance(site_json['wpjson_path'], str):
                media_url = site_json['wpjson_path'] + '/wp/v2/media/' + media_id
            else:
                media_url = ''
            if media_url:
                media_html = add_wp_media(media_url, site_json, None, width)
                if media_html:
                    m = re.search(r'src="([^"]+)', media_html)
                    img_src = m.group(1)

    if not img_src:
        if img.get('data-dt-lazy-src') and not img['data-dt-lazy-src'].startswith('data:image/gif;base64'):
            img_src = resize_image(img['data-dt-lazy-src'], site_json, width, height)

        elif img.get('data-featured-image-url'):
            img_src = resize_image(img['data-featured-image-url'], site_json, width, height)

        elif img.get('data-orig-file'):
            img_src = resize_image(img['data-orig-file'], site_json, width, height)

        elif img.get('data-large-file'):
            img_src = resize_image(img['data-large-file'], site_json, width, height)

        elif img.get('data-lazy-src') and not img['data-lazy-src'].startswith('data:image/gif;base64'):
            img_src = resize_image(img['data-lazy-src'], site_json, width, height)

        elif img.get('data-lazy-load-src') and not img['data-lazy-load-src'].startswith('data:image/gif;base64'):
            img_src = resize_image(img['data-lazy-load-src'], site_json, width, height)

        elif img.get('data-dt-lazy-src') and not img['data-dt-lazy-src'].startswith('data:image/gif;base64'):
            img_src = resize_image(img['data-dt-lazy-src'], site_json, width, height)

        elif img.get('data-src') and not img['data-src'].startswith('data:image/gif;base64'):
            img_src = resize_image(img['data-src'], site_json, width, height)

        elif img.get('data-opt-src') and not img['data-opt-src'].startswith('data:image/gif;base64'):
            img_src = resize_image(img['data-opt-src'], site_json, width, height)

        elif img.get('nw18-data-src') and not img['nw18-data-src'].startswith('data:image/gif;base64'):
            img_src = resize_image(img['nw18-data-src'], site_json, width, height)

        else:
            img_src = resize_image(img['src'], site_json, width, height)

    if img_src.startswith('//'):
        img_src += 'https:' + img_src
    if img_src.startswith('/'):
        if 'image_netloc' in site_json:
            img_src = site_json['image_netloc'] + img_src
        else:
            img_src = image_netloc + img_src
    if img_src and (('image_proxy' in site_json and site_json['image_proxy'] == True) or ('googleusercontent.com/' in img_src)):
        img_src = 'https://wsrv.nl/?url=' + quote_plus(img_src)

    return img_src


def add_wp_media(link_href, site_json, media_json=None, width=1200, caption='', caption_is_desc=False):
    logger.debug('adding wp media ' + link_href)
    if not media_json:
        if link_href.endswith('/wp-json/'):
            return ''
        if site_json.get('replace_links_path'):
            link_href = link_href.replace(site_json['replace_links_path'][0], site_json['replace_links_path'][1])
        media_json = utils.get_url_json(link_href, site_json=site_json)
        if not media_json:
            return ''

    if media_json.get('data') and media_json['data']['status'] == 404:
        return ''

    if media_json['type'] != 'attachment':
        logger.warning('unhandled media type ' + media_json['type'])
        return ''

    desc = ''
    if not caption:
        captions = []
        image_meta = None
        if media_json.get('caption') and media_json['caption'].get('rendered'):
            if caption_is_desc:
                desc = media_json['caption']['rendered']
            else:
                soup = BeautifulSoup(media_json['caption']['rendered'], 'html.parser')
                # print(soup.get_text())
                if not re.search(r'…\]?', soup.get_text(strip=True)):
                    for el in soup.find_all('p', class_=['attachment', 'read-more']):
                        el.decompose()
                    for el in soup.find_all('a', class_='more-link'):
                        el.decompose()
                    if soup.p:
                        captions.append(soup.p.decode_contents())
                    elif soup.get_text(strip=True):
                        caption = soup.get_text(strip=True)
                        if caption != 'excerpt':
                            captions.append(soup.get_text(strip=True))
        if not captions and media_json.get('meta') and media_json['meta'].get('caption'):
            captions.append(media_json['meta']['caption'])
        if not captions and media_json.get('description') and media_json['description'].get('rendered'):
            soup = BeautifulSoup(media_json['description']['rendered'], 'html.parser')
            if soup.img:
                if soup.img.get('data-image-caption'):
                    captions.append(re.sub(r'</?p>', '', soup.img['data-image-caption'].strip()))
                if soup.img.get('data-image-meta'):
                    try:
                        image_meta = json.loads(soup.img['data-image-meta'])
                        if image_meta.get('caption'):
                            captions.append(image_meta['caption'])
                    except:
                        pass
        if media_json.get('meta') and media_json['meta'].get('credit'):
            captions.append(media_json['meta']['credit'])
        elif media_json.get('meta') and media_json['meta'].get('_image_credit'):
            captions.append(media_json['meta']['_image_credit'])
        elif image_meta and image_meta.get('credit'):
            captions.append(image_meta['credit'])
        if '#post_seo_description' in captions:
            captions.remove('#post_seo_description')
        caption = ' | '.join(captions)

    if media_json['mime_type'] == 'video/mp4':
        return utils.add_video(media_json['source_url'], 'video/mp4', '', caption)

    img_src = ''
    if 'wp_media_size' in site_json:
        val = get_data_value(media_json, site_json['wp_media_size'])
        # print(val)
        if val and isinstance(val, str):
            img_src = val
    if not img_src:
        if media_json.get('media_details') and media_json['media_details'].get('width') and int(media_json['media_details']['width']) <= width:
            img_src = media_json['source_url']
        elif media_json.get('description') and media_json['description'].get('rendered') and 'srcset' in media_json['description']['rendered']:
            el = BeautifulSoup(media_json['description']['rendered'], 'html.parser')
            if el.img:
                if el.img.get('data-srcset'):
                    img_src = utils.image_from_srcset(el.img['data-srcset'], width)
                elif el.img.get('srcset'):
                    img_src = utils.image_from_srcset(el.img['srcset'], width)
    if not img_src:
        if media_json.get('media_details') and media_json['media_details'].get('sizes'):
            media = utils.closest_dict(list(media_json['media_details']['sizes'].values()), 'width', width)
            img_src = media['source_url']
        else:
            img_src = media_json['source_url']
    if img_src.startswith('//'):
        img_src += 'https:' + img_src
    if img_src.startswith('/'):
        if 'image_netloc' in site_json:
            img_src = site_json['image_netloc'] + img_src
        else:
            img_src = 'https://' + urlsplit(link_href).netloc + img_src
    if img_src and 'image_proxy' in site_json and site_json['image_proxy'] == True:
        img_src = 'https://wsrv.nl/?url=' + quote_plus(img_src)
    return utils.add_image(img_src, caption, link=media_json.get('link'), desc=desc)


def add_image(image_el, image_tag, site_json, base_url, wp_media_url):
    # image is a BeautifulSoup element
    img_src = get_img_src(image_el, site_json, base_url, wp_media_url)
    if not img_src:
        return ''
    captions = []
    if image_tag.get('credit'):
        it = utils.get_soup_elements(image_tag['credit'], image_el)
        if it and it[0].get_text(strip=True):
            captions.append(it[0].decode_contents())
            it[0].decompose()
    if image_tag.get('caption'):
        if 'text' in image_tag['caption'] and image_tag['caption']['text'] == True:
            if image_el.get_text(strip=True):
                captions.insert(0, image_el.get_text(strip=True))
        else:
            it = utils.get_soup_elements(image_tag['caption'], image_el)
            if it and it[0].get_text(strip=True):
                # captions.insert(0, it[0].decode_contents())
                captions.insert(0, re.sub(r'<br/?>$', '', it[0].decode_contents()).strip())
                it[0].decompose()
    if not captions and image_el.img and image_el.img.get('data-image-meta'):
        try:
            image_meta = json.loads(html.unescape(image_el.img['data-image-meta']))
            if image_meta.get('caption'):
                captions.append(image_meta['caption'])
            if image_meta.get('credit'):
                captions.append(image_meta['credit'])
            elif image_meta.get('copyright'):
                captions.append(image_meta['copyright'])
        except:
            pass
    caption = ' | '.join(captions)
    desc = ''
    if image_tag.get('desc'):
        it = utils.get_soup_elements(image_tag['desc'], image_el)
        if it and it[0].get_text(strip=True):
            desc = it.decode_contents()
    link = ''
    if image_tag.get('link'):
        it = utils.get_soup_elements(image_tag['link'], image_el)
        if it and it[0].get('href'):
            link = it[0]['href']
    if not link:
        if image_el.name == 'a':
            link = image_el['href']
        else:
            it = image_el.select('a:has(img)')
            if it:
                link = it[0]['href']
    return utils.add_image(img_src, caption, link=link, desc=desc)


def add_gallery(gallery, tag, site_json, base_url, wp_media_url):
    gallery_html = ''
    images = utils.get_soup_elements(tag['image'], gallery)
    if images:
        gallery_images = []
        data_image = []
        for image in images:
            if image.get('data-image'):
                if image['data-image'] in data_image:
                    continue
                else:
                    data_image.append(image['data-image'])

            captions = []
            if tag['image'].get('credit'):
                it = utils.get_soup_elements(tag['image']['credit'], image)
                if it and it[0].decode_contents().strip():
                    captions.append(it[0].decode_contents().strip())
                    it[0].decompose()
            if tag['image'].get('caption'):
                it = utils.get_soup_elements(tag['image']['caption'], image)
                if it and it[0].decode_contents().strip():
                    if it[0].name == 'script':
                        el = BeautifulSoup(it[0].string, 'html.parser')
                        caption = el.find(class_='caption')
                        if caption:
                            captions.insert(0, caption.decode_contents().strip())
                        else:
                            captions.insert(0, el.decode_contents().strip())
                    else:
                        captions.insert(0, it[0].decode_contents().strip())
                    it[0].decompose()
            caption = ' | '.join(captions)

            if image.name == 'a':
                link = image['href']
            else:
                el = image.find('a')
                if el:
                    link = el['href']
                else:
                    link = ''

            if image.name == 'video':
                el = image.find('source')
                if el:
                    img_src = el['src']
                elif image.get('src'):
                    img_src = image['src']
                if image.get('poster'):
                    thumb = image['poster']
                else:
                    thumb = config.server + '/image?url=' + quote_plus(img_src)
                if not link:
                    link = img_src
                gallery_images.append({"src": img_src, "caption": caption, "thumb": thumb, "link": link, "video_type": "video/mp4"})
            else:
                img_src = get_img_src(image, site_json, base_url, wp_media_url, 2000)
                if not img_src:
                    continue
                thumb = get_img_src(image, site_json, base_url, wp_media_url, 800)
                if not link:
                    link = img_src
                gallery_images.append({"src": img_src, "caption": caption, "thumb": thumb, "link": link})
        n = len(gallery_images)
        captions = []
        if tag.get('credit'):
            it = utils.get_soup_elements(tag['credit'], gallery)
            if it and it[0].decode_contents().strip():
                captions.append(it[0].decode_contents().strip())
                it[0].decompose()
        if tag.get('caption'):
            it = utils.get_soup_elements(tag['caption'], gallery)
            if it and it[0].decode_contents().strip():
                captions.insert(0, it[0].decode_contents().strip())
                it[0].decompose()
        gallery_caption = ' | '.join(captions)
        if gallery_caption:
            # Find duplicate captions
            s = re.sub(r'\W', '', gallery_caption).lower()
            x = []
            for i, image in enumerate(gallery_images):
                if image['caption']:
                    if re.sub(r'\W', '', image['caption']).lower() == s:
                        x.append(i)
            if len(x) > 0:
                if len(x) == n and n > 1:
                    for image in gallery_images:
                        image['caption'] = ''
                else:
                    gallery_caption = ''
        show_gallery_poster = 'show_gallery_link' in tag and tag['show_gallery_link'] == True
        return utils.add_gallery(gallery_images, gallery_caption=gallery_caption, show_gallery_poster=show_gallery_poster)

    #     if gallery_caption:
    #         flex_margin = '1em 0 0 0'
    #     else:
    #         flex_margin = '1em 0'
    #     if n == 1:
    #         if gallery_images[0].get('caption'):
    #             caption = gallery_images[0]['caption']
    #         else:
    #             caption = gallery_caption
    #         if 'video_type' in gallery_images[0]:
    #             gallery_html += utils.add_video(gallery_images[0]['src'], gallery_images[0]['video_type'], gallery_images[0]['thumb'], caption)
    #         else:
    #             gallery_html = utils.add_image(gallery_images[0]['src'], caption, link=gallery_images[0]['link'])
    #         caption = ''
    #     else:
    #         for i, image in enumerate(gallery_images):
    #             if i == 0:
    #                 if n % 2 == 1:
    #                     # start with full width image if odd number of images
    #                     if 'video_type' in image:
    #                         gallery_html += utils.add_video(image['src'], image['video_type'], image['thumb'], image['caption'], fig_style='margin:1em 0 8px 0; padding:0;')
    #                     else:
    #                         gallery_html += utils.add_image(image['thumb'], image['caption'], link=image['link'], fig_style='margin:1em 0 8px 0; padding:0;')
    #                 else:
    #                     gallery_html += '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:' + flex_margin + ';"><div style="flex:1; min-width:360px;">'
    #                     if 'video_type' in image:
    #                         gallery_html += utils.add_video(image['src'], image['video_type'], image['thumb'], image['caption'], fig_style='margin:0; padding:0;')
    #                     else:
    #                         gallery_html += utils.add_image(image['thumb'], image['caption'], link=image['link'], fig_style='margin:0; padding:0;')
    #                     gallery_html += '</div>'
    #             elif i == 1:
    #                 if n % 2 == 1:
    #                     gallery_html += '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:' + flex_margin + ';">'
    #                 gallery_html += '<div style="flex:1; min-width:360px;">'
    #                 if 'video_type' in image:
    #                     gallery_html += utils.add_video(image['src'], image['video_type'], image['thumb'], image['caption'], fig_style='margin:0; padding:0;')
    #                 else:
    #                     gallery_html += utils.add_image(image['thumb'], image['caption'], link=image['link'], fig_style='margin:0; padding:0;')
    #                 gallery_html += '</div>'
    #             else:
    #                 gallery_html += '<div style="flex:1; min-width:360px;">'
    #                 if 'video_type' in image:
    #                     gallery_html += utils.add_video(image['src'], image['video_type'], image['thumb'], image['caption'], fig_style='margin:0; padding:0;')
    #                 else:
    #                     gallery_html += utils.add_image(image['thumb'], image['caption'], link=image['link'], fig_style='margin:0; padding:0;')
    #                 gallery_html += '</div>'
    #             del image['link']
    #         gallery_html += '</div>'
    #     if gallery_caption:
    #         gallery_html += '<div style="font-size:smaller; margin:4px 0 1em 0;">' + gallery_caption + '</div>'
    #     if n > 2 and ('show_gallery_link' not in tag or tag['show_gallery_link'] == True):
    #         gallery_url = config.server + '/gallery?images=' + quote_plus(json.dumps(gallery_images))
    #         if 'show_gallery_poster' in tag and tag['show_gallery_poster'] == True:
    #             if caption:
    #                 caption = '<a href="' + gallery_url + '" target="_blank">View gallery</a>: ' + caption
    #             elif gallery_images[0].get('caption'):
    #                 caption = '<a href="' + gallery_url + '" target="_blank">View gallery</a>: ' + gallery_images[0]['caption']
    #             else:
    #                 caption = '<a href="' + gallery_url + '" target="_blank">View gallery</a>'
    #             caption += ' ({} images)'.format(n)
    #             gallery_html = utils.add_image(gallery_images[0]['src'], caption, link=gallery_url, overlay=config.gallery_button_overlay)
    #         else:
    #             gallery_html = '<h3><a href="' + gallery_url + '" target="_blank">View photo gallery</a></h3>' + gallery_html
    # return gallery_html


def add_nbc_video(video_id, wpjson_path):
    videos = utils.get_url_json(wpjson_path + '/nbc/v1/template/videos?_fields=template_items')
    if not videos:
        return ''
    i = 1
    while i <= videos['template_items']['pagination']['total_pages']:
        video = next((it for it in videos['template_items']['items'] if it['post_noid'] == video_id), None)
        if not video:
            video = next((it for it in videos['template_items']['video_archive'] if it['post_noid'] == video_id), None)
        if video:
            return utils.add_video(video['video']['meta']['mp4_url'], 'video/mp4', video['video']['meta']['mpx_thumbnail_url'], video['title'], use_videojs=True)
        i += 1
        videos = utils.get_url_json(wpjson_path + '/nbc/v1/template/videos?_fields=template_items&page=' + str(i))
    logger.warning('nbc video not found: ' + video_id)
    return ''


def add_nxs_player_video(nxs_player):
    params = json.loads(nxs_player['data-video_params'].replace("'/", '"'))
    utils.write_file(params, './debug/video_params.json')
    video_id = ''
    if params.get('video'):
        video_id = params['video']
    elif params.get('playlist'):
        lura_feed = utils.get_url_json('https://feed.mp.lura.live/v2/feed/' + params['playlist']['id'] + '?start=0&fmt=json')
        if lura_feed:
            video_id = lura_feed['docs'][0]['obj_id']
    if video_id:
        # Get higher quality image
        lura_rest = utils.get_url_html('https://tkx.mp.lura.live/rest/v2/mcp/video/' + video_id + '?anvack=' + params['accessKey'])
        if lura_rest:
            i = lura_rest.find('{')
            j = lura_rest.rfind('}') + 1
            video_json = json.loads(lura_rest[i:j])
            poster = video_json['src_image_url']
            caption = video_json['def_title']
    if video_id and params.get('accessKey') and params.get('token'):
        key_json = {
            "v": video_id,
            "token": params['token'],
            "accessKey": params['accessKey']
        }
        key = base64.b64encode(json.dumps(key_json, separators=(',', ':')).encode()).decode()
        lura_url = 'https://w3.mp.lura.live/player/prod/v3/anvload.html?key=' + key
        video_url = config.server + '/video?url=' + quote_plus(lura_url)
        return utils.add_image(poster, caption, link=video_url, overlay=config.video_button_overlay)
    elif 'nxs' in params and 'mp4Url' in params['nxs']:
        return utils.add_video(params['nxs']['mp4Url'], 'video/mp4', poster, caption, use_videojs=True)
    elif video_json and video_json.get('published_urls') and video_json['published_urls'][0].get('embed_url'):
        # embed_url looks like it will expire
        return utils.add_video(video_json['published_urls'][0]['embed_url'], 'application/x-mpegURL', poster, caption, use_videojs=True)
    return ''


def format_block(block, site_json, base_url):
    block_html = ''
    if block.get('name'):
        block_name = block['name']
    elif block.get('blockName'):
        block_name = block['blockName']
    else:
        logger.warning('unknown block name ' + str(block))
        return block_html
    if block.get('attributes'):
        block_attrs = block['attributes']
    elif block.get('attrs'):
        block_attrs = block['attrs']
    else:
        block_attrs = {}
    if block_name == 'core/paragraph':
        block_html += '<p'
        if 'dropCap' in block_attrs and block_attrs['dropCap'] == True:
            block_html += ' class="drop-cap"'
        if 'fontSize' in block_attrs:
            block_html += ' style="font-size:' + block_attrs['fontSize'] + ';"'
        block_html += '>' + block_attrs['content'] + '</p>'
    elif block_name == 'core/heading':
        block_html += '<h{0}>{1}</h{0}>'.format(block_attrs['level'], block_attrs['content'])
    elif block_name == 'core/image':
        captions = []
        if block_attrs.get('caption'):
            captions.append(block_attrs['caption'])
        if block_attrs.get('credit'):
            captions.append(block_attrs['credit'])
        if block_attrs.get('url'):
            img_src = block_attrs['url']
        elif 'image' in block_attrs and 'original' in block_attrs['image']:
            img_src = block_attrs['image']['original']
        elif 'innerContent' in block:
            soup = BeautifulSoup(block['innerContent'], 'html.parser')
            img_src = get_img_src(soup, site_json, base_url, '', 2000)
            if not captions:
                el = soup.find('figcaption')
                if el and el.get_text(strip=True):
                    captions.append(el.decode_contents().strip())
        else:
            logger.warning('unknown img src for core/image ' + str(block))
            img_src = ''
        if 'align' in block_attrs and block_attrs['align'] == 'left':
            block_html += utils.add_image(img_src, ' | '.join(captions), width=block_attrs['width'], height=block_attrs['height'], img_style='float:left; margin-right:8px;')
        elif 'align' in block_attrs and block_attrs['align'] == 'right':
            block_html += utils.add_image(img_src, ' | '.join(captions), img_style='float:right; margin-left:8px; height:{}px; width:{}px;'.format(block_attrs['height'], block_attrs['width']))
        else:
            block_html += utils.add_image(img_src, ' | '.join(captions))
    elif block_name == 'core/embed':
        block_html += utils.add_embed(block_attrs['url'])
    elif block_name == 'core/html' and block_attrs['content'].startswith('<iframe'):
        m = re.search(r'src="([^"]+)', block_attrs['content'])
        block_html += utils.add_embed(m.group(1))
    elif block_name == 'core/list':
        if 'ordered' in block_attrs and block_attrs == True:
            tag = 'ol'
        else:
            tag = 'ul'
        block_html += '<' + tag + '>'
        for blk in block['innerBlocks']:
            block_html += format_block(blk, site_json, base_url)
        block_html += '</' + tag + '>'
    elif block_name == 'core/list-item':    
        block_html += '<li>' + block_attrs['content'] + '</li>'
    elif block_name == 'core/columns':
        block_html += '<div style="display:flex; flex-wrap:wrap; margin:1em 0; gap:8px;">'
        for blk in block['innerBlocks']:
            block_html += format_block(blk, site_json, base_url)
        block_html += '</div>'
    elif block_name == 'core/column':
        block_html += '<div style="flex:1; min-width:360px;">'
        for blk in block['innerBlocks']:
            block_html += format_block(blk, site_json, base_url)
        block_html += '</div>'
    elif block_name == 'core/table':
        block_html += '<table>'
        for row in block_attrs['body']:
            block_html += '<tr>'
            for cell in row['cells']:
                block_html += '<' + cell['tag']
                if cell.get('colspan'):
                    block_html += ' colspan="{}"'.format(cell['colspan'])
                if cell.get('rowspan'):
                    block_html += ' rowspan="{}"'.format(cell['rowspan'])
                if cell.get('align'):
                    block_html += ' style="text-align:{}"'.format(cell['align'])
                block_html += '>' + cell['content'] + '</' + cell['tag'] + '>'
            block_html += '</tr>'
        block_html += '</table>'
    elif block_name == 'core/spacer':
        block_html += '<div style="height:'
        if 'height' in block_attrs:
            block_html += block_attrs['height']
        else:
            block_html += '1em'
        block_html += ';"></div>'
    elif block_name == 'tidal-blocks/header':
        if 'preamble' in block_attrs:
            block_html += '<p><em>' + block_attrs['preamble'] + '</em></p>'
    elif block_name == 'pym-shortcode/pym' or block_name == 'cpr/ad-unit' or block_name == 'denverite/ad':
        pass
    else:
        logger.warning('unhandled content block name ' + block_name)
    return block_html


def find_post_id(page_soup):
    post_id = ''
    post_url = ''
    # Find the direct wp-json link
    el = page_soup.find('link', attrs={"rel": "alternate", "type": "application/json", "href": re.compile(r'wp-json')})
    if el:
        post_url = el['href']
        m = re.search(r'/(\d+)', post_url)
        if m:
            post_id = m.group(1)
    else:
        # The shortlink is generally of the form: https://www.example.com?p=post_id
        el = page_soup.find('link', attrs={"rel": "shortlink"})
        if el:
            query = parse_qs(urlsplit(el['href']).query)
            if query.get('p'):
                post_id = query['p'][0]
    if not post_id:
        # Sometimes the post id is sometimes in the id/class of the article/content section
        el = page_soup.find(id=re.compile(r'post-\d+'))
        if el:
            m = re.search(r'post-(\d+)', el['id'])
            if m:
                post_id = m.group(1)
    if not post_id:
        el = page_soup.find(class_=re.compile(r'postid-\d+'))
        if el:
            m = re.search(r'postid-(\d+)', ' '.join(el['class']))
            if m:
                post_id = m.group(1)
    if not post_id:
        m = re.search(r'"articleId","(\d+)"', str(page_soup))
        if m:
            if m:
                post_id = m.group(1)
    if not post_id:
        el = page_soup.find('script', id='page-data', attrs={"type": "application/json"})
        if el:
            page_data = json.loads(el.string)
            try:
                post_id = page_data['page']['originId']
            except:
                post_id = ''
    if post_id:
        logger.debug('found post id {}, post url {}'.format(post_id, post_url))
    return post_id, post_url


def get_page_soup(url, site_json, save_debug=False):
    # page_html = utils.get_url_html(url, site_json=site_json)
    # if not page_html:
    #     return None
    # if save_debug:
    #     utils.write_file(page_html, './debug/page.html')
    # page_soup = BeautifulSoup(page_html, 'lxml')
    try:
        r = curl_cffi.get(url, impersonate=config.impersonate, proxies=config.proxies)
    except curl_cffi.requests.exceptions.CertificateVerifyError:
        r = curl_cffi.get(url, impersonate=config.impersonate)
    if r.status_code != 200:
        return None
    if save_debug:
        utils.write_file(r.text, './debug/page.html')
    page_soup = BeautifulSoup(r.text, 'lxml')
    return page_soup


def get_meta_tags(soup):
    meta = {}
    def add_to_meta(key, val):
        nonlocal meta
        if key not in meta:
            meta[key] = val
        elif isinstance(meta[key], str) and meta[key] != val:
            meta[key] = [meta[key]]
            meta[key].append(val)
        elif isinstance(meta[key], list) and val not in meta[key]:
            meta[key].append(val)

    for el in soup.find_all('meta'):
        if el.get('content'):
            if el.get('name'):
                add_to_meta(el['name'], el['content'])
            elif el.get('property'):
                add_to_meta(el['property'], el['content'])
    # for el in soup.find_all(attrs={"itemprop": True}):
    #     if el.get('content'):
    #         add_to_meta(el['itemprop'], el['content'])
    return meta


def get_yoast_scheme_graph(soup):
    yoast_schema_graph = []
    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        def fix_review_body(matchobj):
            return re.sub(r'\n', '', matchobj.group(0))
        el_json = json.loads(re.sub(r'"reviewBody":"([^"]+)"', fix_review_body, el.string))
        if isinstance(el_json, dict):
            if el_json.get('@graph'):
                yoast_schema_graph += el_json['@graph']
            else:
                yoast_schema_graph.append(el_json)
        elif isinstance(el_json, list):
            yoast_schema_graph += el_json

    def get_itemprops(el_itemtype, item, soup):
        if el_itemtype.get('itemref'):
            itemprops = soup.find_all(id=el_itemtype['itemref'], attrs={"itemprop": True})
            print(itemprops)
        else:
            itemprops = el_itemtype.find_all(attrs={"itemprop": True})
        for it in itemprops:
            if not it or not it.name:
                continue
            key = it['itemprop']
            if it.get('itemtype'):
                split_url = urlsplit(it['itemtype'])
                if key in item:
                    item[key] = [item[key]]
                    item[key].append({
                        "@context": split_url.scheme + '://' + split_url.netloc,
                        "@type": split_url.path.strip('/')
                    })
                    get_itemprops(it, item[key][-1], soup)
                else:
                    item[key] = {
                        "@context": split_url.scheme + '://' + split_url.netloc,
                        "@type": split_url.path.strip('/')
                    }
                    get_itemprops(it, item[key], soup)
            elif it.get('content'):
                item[key] = it['content']
            elif it.get_text(strip=True):
                item[key] = it.get_text(strip=True)
            it.decompose()

    # make a copy since elements get removed and may be necessary for content
    soup_copy = copy.copy(soup)
    for el in soup_copy.find_all(attrs={"itemtype": True, "itemprop": False}):
        split_url = urlsplit(el['itemtype'])
        item = {
            "@context": split_url.scheme + '://' + split_url.netloc,
            "@type": split_url.path.strip('/')
        }
        get_itemprops(el, item, soup_copy)
        yoast_schema_graph.append(item)
    return yoast_schema_graph


def get_data_value(data, keys):
    try:
        val = data
        for key in keys:
            val = val[key]
        return val
    except:
        return None


def get_content(url, args, site_json, save_debug=False, page_soup=None):
    split_url = urlsplit(url)
    base_url = split_url.scheme + '://' + split_url.netloc
    paths = list(filter(None, re.sub(r'\.(html|php)$', '', split_url.path[1:]).split('/')))
    params = parse_qs(split_url.query)
    # if paths[-1].endswith('.html'):
    #     paths[-1] = re.sub(r'\.html$', '', paths[-1])
    if len(paths) > 0 and paths[-1] == 'embed':
        del paths[-1]
        args['embed'] = True

    post_id = ''
    post_url = ''
    posts_path = ''
    wpjson_path = ''
    wp_post = None
    page_soup = None

    if 'load_page' in args or 'wpjson_path' not in site_json:
        page_soup = get_page_soup(url, site_json, save_debug)
        if page_soup:
            if 'ignore_canonical' not in args:
                el = page_soup.find('link', attrs={"rel": "canonical"})
                if el and el.get('href'):
                    if urlsplit(el['href']).netloc != split_url.netloc:
                        logger.debug('getting content from ' + el['href'])
                        item = utils.get_content(el['href'], args, save_debug)
                        if item:
                            return item
            post_id, post_url = find_post_id(page_soup)
            if 'wpjson_path' not in site_json:
                post_url = ''

    if post_url:
        wp_post = utils.get_url_json(post_url, site_json=site_json)

    if not wp_post:
        if 'wpjson_path' in site_json:
            if isinstance(site_json['wpjson_path'], str):
                if site_json['wpjson_path'].startswith('/'):
                    wpjson_path = split_url.scheme + '://' + split_url.netloc + site_json['wpjson_path']
                else:
                    wpjson_path = site_json['wpjson_path']
            elif isinstance(site_json['wpjson_path'], dict):
                for key, val in site_json['wpjson_path'].items():
                    if key in paths:
                        wpjson_path = val
                        break
                if not wpjson_path:
                    if 'default' in site_json['wpjson_path']:
                        wpjson_path = site_json['wpjson_path']['default']

        if 'posts_type' in site_json and page_soup and post_id:
            el = page_soup.find(class_='post-' + post_id)
            if el:
                for x in el['class']:
                    if x.startswith('type-') and x in site_json['posts_type']:
                        posts_path = site_json['posts_type'][x]
                        break
        elif 'posts_path' in site_json:
            if site_json and isinstance(site_json['posts_path'], str):
                posts_path = site_json['posts_path']
            elif site_json and isinstance(site_json['posts_path'], dict):
                # for key, val in site_json['posts_path'].items():
                for x in paths:
                    if x in site_json['posts_path']:
                        posts_path = site_json['posts_path'][x]
                        break
                if not posts_path:
                    if 'default' in site_json['posts_path']:
                        posts_path = site_json['posts_path']['default']
                    elif page_soup:
                        for key, val in site_json['posts_path'].items():
                            el = page_soup.find(class_=key)
                            if el:
                                posts_path = val
                                break

        if wpjson_path and posts_path:
            if post_id:
                post_url = wpjson_path + posts_path + '/' + post_id
            elif params.get('p'):
                post_id = params['p'][0]
                post_url = wpjson_path + posts_path + '/' + post_id
            elif 'slug' in site_json and site_json['slug'] and isinstance(site_json['slug'], int):
                if paths[site_json['slug']].isnumeric():
                    post_id = paths[site_json['slug']]
                    post_url = wpjson_path + posts_path + '/' + post_id
                else:
                    post_url = wpjson_path + posts_path + '?slug=' + paths[site_json['slug']]

            if not post_url:
                # look for post id in the path
                for m in re.findall(r'\d{4,}', split_url.path):
                    if split_url.netloc == 'www.thedailymash.co.uk' and len(m) > 8:
                        post_id = m[8:]
                    elif (len(m) == 4 and datetime.now().year - 10 <= int(m[:4]) <= datetime.now().year) or (len(m) == 8 and int(m[:4]) <= datetime.now().year and int(m[4:6]) <= 12 and int(m[6:8]) <= 31):
                        # year or date
                        continue
                    else:
                        post_id = m
                    post_url = wpjson_path + posts_path + '/' + post_id
                    wp_post = utils.get_url_json(post_url, site_json=site_json)
                    if wp_post:
                        break
                    else:
                        post_id = ''
                        post_url = ''

            if not post_url:
                # try slugs
                for it in reversed(paths):
                    if ('exclude_slugs' in site_json and it in site_json['exclude_slugs']) or it.isnumeric():
                        continue
                    post_url = wpjson_path + posts_path + '?slug=' + it
                    wp_post = utils.get_url_json(post_url, site_json=site_json)
                    if wp_post:
                        break
                    else:
                        post_url = ''

            if not post_url and not page_soup:
                page_soup = get_page_soup(url, site_json, save_debug)
                if page_soup:
                    post_id, post_url = find_post_id(page_soup)
                    if post_id and not post_url:
                        post_url = wpjson_path + posts_path + '/' + post_id

    if not post_url:
        logger.debug('unable to determine wp-json post url for ' + url)

    if post_url and not wp_post:
        wp_post = utils.get_url_json(post_url, site_json=site_json)
        if not wp_post:
            if split_url.netloc == 'www.pcgamesn.com' and posts_path.endswith('/review'):
                post_html = utils.get_url_html(post_url, site_json=site_json)
                if post_html:
                    if save_debug:
                        utils.write_file(post_html, './debug/post.html')
                    m = re.search(r'\{"id":.*', post_html)
                    if m:
                        try:
                            wp_post = json.loads(m.group(0))
                        except:
                            wp_post = None

    post_data = {}
    next_data = None
    nxst_data = None
    meta_json = {}
    yoast_schema_graph = []

    if wp_post:
        if save_debug:
            utils.write_file(wp_post, './debug/wp_post.json')
        if isinstance(wp_post, dict):
            post_data['post'] = wp_post
        elif isinstance(wp_post, list):
            post = next((x for x in wp_post if split_url.path in x['link']), None)
            if post:
                post_data['post'] = post
            else:
                post_data['post'] = wp_post[0]
        if post_data['post'].get('yoast_head_json') and post_data['post']['yoast_head_json'].get('schema') and post_data['post']['yoast_head_json']['schema'].get('@graph'):
            yoast_schema_graph = post_data['post']['yoast_head_json']['schema']['@graph']
        elif post_data['post'].get('aioseo_head_json') and post_data['post']['aioseo_head_json'].get('schema') and post_data['post']['aioseo_head_json']['schema'].get('@graph'):
            yoast_schema_graph = post_data['post']['aioseo_head_json']['schema']['@graph']
        elif post_data['post'].get('yoast_head'):
            yoast_head = BeautifulSoup(post_data['post']['yoast_head'], 'html.parser')
            post_data['meta'] = get_meta_tags(yoast_head)
            yoast_schema_graph = get_yoast_scheme_graph(yoast_head)
    else:
        post_data['post'] = {}

    if page_soup:
        if not yoast_schema_graph:
            yoast_schema_graph = get_yoast_scheme_graph(page_soup)
        meta_json = get_meta_tags(page_soup)
        el = page_soup.find('script', id='page-data', attrs={"type": "application/json"})
        if el:
            post_data['page_data'] = json.loads(el.string)
        el = page_soup.find('script', id='__NEXT_DATA__')
        if el:
            next_data = json.loads(el.string)
        el = page_soup.find('script', string=re.compile(r'window\.NXSTdata\.content ='))
        if el:
            m = re.search(r'window\.NXSTdata\.content,\s*(\{.*?\})\s*\)\s*window', el.string)
            if m:
                nxst_data = json.loads(m.group(1))

    if yoast_schema_graph:
        if save_debug:
            utils.write_file(yoast_schema_graph, './debug/yoast.json')
        def parse_graph(graph):
            nonlocal post_data
            for it in graph:
                if '@graph' in it:
                    parse_graph(it['@graph'])
                elif it.get('@type') and isinstance(it['@type'], str):
                    if it['@type'] not in post_data:
                        post_data[it['@type']] = it
                    elif isinstance(post_data[it['@type']], list):
                        post_data[it['@type']].append(it)
                    else:
                        post_data[it['@type']] = [post_data[it['@type']]]
                        post_data[it['@type']].append(it)
        parse_graph(yoast_schema_graph)

    if not meta_json and post_data.get('post') and post_data['post'].get('jetpack_og_tags') and post_data['post']['jetpack_og_tags'].get('meta'):
        for it in post_data['post']['jetpack_og_tags']['meta']:
            if it.get('property') and it.get('content'):
                meta_json[it['property']] = it['content']
    if meta_json:
        post_data['meta'] = meta_json

    if next_data:
        post_data['next_data'] = next_data

    if nxst_data:
        post_data['nxst_data'] = nxst_data

    if save_debug:
        utils.write_file(post_data, './debug/debug.json')

    article_key = ''
    for key in post_data.keys():
        if key.endswith('Article'):
            article_key = key
            break

    wp_media_url = ''
    if 'media_path' in site_json:
        wp_media_url = site_json['wpjson_path'] + site_json['media_path'] + '/'
    elif post_data.get('post') and post_data['post'].get('_links'):
        if post_data['post']['_links'].get('wp:featuredmedia'):
            wp_media_url = re.sub(r'\d+$', '', post_data['post']['_links']['wp:featuredmedia'][0]['href'])
        elif post_data['post']['_links'].get('wp:attachment'):
            wp_media_url = utils.clean_url(post_data['post']['_links']['wp:attachment'][0]['href']) + '/'
        if not wp_media_url or wp_media_url.endswith('/wp-json/'):
            wp_media_url = re.sub(r'[^/]+/\d+$', '', post_data['post']['_links']['self'][0]['href']) + 'media/'

    item = {}
    if 'id' in site_json:
        val = get_data_value(post_data, site_json['id'])
        if val:
            item['id'] = val
    elif post_id:
        item['id'] = post_id
    elif post_data.get('meta') and post_data['meta'].get('parsely-metadata'):
        m = re.search(r'"post_id":"([^"]+)', post_data['meta']['parsely-metadata'])
        if m:
            item['id'] = m.group(1)

    if 'url' in site_json:
        val = get_data_value(post_data, site_json['url'])
        if val:
            item['url'] = val

    if 'title' in site_json:
        if isinstance(site_json['title'], list):
            val = get_data_value(post_data, site_json['title'])
            if val:
                item['title'] = val
        elif isinstance(site_json['title'], dict):
            for el in utils.get_soup_elements(site_json['title'], page_soup):
                item['title'] = el.get_text(strip=True)
                break

    dt_pub = None
    if 'date_published' in site_json:
        val = get_data_value(post_data, site_json['date_published'])
        if val:
            dt_pub = datetime.fromisoformat(val)

    dt_mod = None
    if 'date_modified' in site_json:
        val = get_data_value(post_data, site_json['date_modified'])
        if val:
            dt_mod = datetime.fromisoformat(val)

    authors = []
    if 'author' in site_json:
        if isinstance(site_json['author'], list):                    
            def get_authors(author_key_list, author_key, author_split):
                nonlocal post_data
                authors = []
                val = get_data_value(post_data, author_key_list)
                if val:
                    if isinstance(val, str):
                        if author_split:
                            authors += [x.strip() for x in val.split(author_split)]
                        else:
                            authors.append(val)
                    elif isinstance(val, dict) and author_key:
                        if author_split:
                            authors += [x.strip() for x in val[author_key].split(author_split)]
                        else:
                            authors.append(val[author_key])
                    elif isinstance(val, list):
                        for author in val:
                            if isinstance(author, str):
                                if author_split:
                                    authors += [x.strip() for x in author.split(author_split)]
                                else:
                                    authors.append(author)
                            elif isinstance(author, dict) and author_key:
                                if author_split:
                                    authors += [x.strip() for x in author[author_key].split(author_split)]
                                else:
                                    authors.append(author[author_key])
                return authors
            if isinstance(site_json['author'][0], list):
                for i, it in enumerate(site_json['author']):
                    author = get_authors(it, site_json['author_key'][i] if site_json.get('author_key') else None, site_json['author_split'][i] if site_json.get('author_split') else None)
                    if author:
                        authors += author
            else:
                authors = get_authors(site_json['author'], site_json.get('author_key'), site_json.get('author_split'))
        elif isinstance(site_json['author'], dict):
            for el in utils.get_soup_elements(site_json['author'], page_soup):
                author = ''
                if el.name == 'meta':
                    author = el['content']
                elif el.name == 'a':
                    author = el.get_text(strip=True)
                else:
                    for it in el.find_all('a', href=re.compile(r'author|correspondents|staff')):
                        author = it.get_text(strip=True)
                        if author not in authors:
                            authors.append(author)
                if not author and 'author_regex' in site_json['author']:
                    m = re.search(site_json['author']['author_regex'], el.get_text(strip=True))
                    if m:
                        author = m.group(site_json['author']['author_regex_group']).strip()
                if not author and el.get_text(strip=True):
                    author = re.sub(r'^By:?\s*(.*?)[\s\W]*$', r'\1', el.get_text(strip=True), flags=re.I)
                if author:
                    author = re.sub(r'(.*?),\s?Associated Press$', r'\1 (Associated Press)', author)
                    if author not in authors:
                        authors.append(author)
                if authors and not site_json['author'].get('multi'):
                    break

    item['tags'] = []
    if 'tags' in site_json:
        if isinstance(site_json['tags'], list):
            val = get_data_value(post_data, site_json['tags'])
            if val:
                if isinstance(val, str):
                    if 'tags_delimiter' in site_json:
                        item['tags'] += [x.strip() for x in val.split(site_json['tags_delimiter'])]
                    else:
                        item['tags'].append(val)
                elif isinstance(val, list):
                    item['tags'] += val.copy()
        elif isinstance(site_json['tags'], dict):
            for el in utils.get_soup_elements(site_json['tags'], page_soup):
                if el.name == 'a' or ('no_link' in site_json['tags'] and site_json['tags']['no_link'] == True):
                    item['tags'].append(el.get_text(strip=True))
                else:
                    for it in el.find_all('a'):
                        item['tags'].append(it.get_text(strip=True))

    if 'summary' in site_json:
        if isinstance(site_json['summary'], list):
            val = get_data_value(post_data, site_json['title'])
            if val:
                item['summary'] = val

    subtitle = ''
    if 'subtitle' in site_json:
        if isinstance(site_json['subtitle'], list):
            val = get_data_value(post_data, site_json['subtitle'])
            if val:
                subtitle = re.sub(r'^<p>|</p>$', '', val.strip())
        elif isinstance(site_json['subtitle'], dict):
            for el in utils.get_soup_elements(site_json['subtitle'], page_soup):
                subtitle = el.get_text(strip=True)
                break

    lede_html = ''
    lede_caption = ''
    if 'lede_video' in site_json and isinstance(site_json['lede_video'], dict):
        for el in utils.get_soup_elements(site_json['lede_video'], page_soup):
            if el.name == 'iframe':
                lede_html = utils.add_embed(el['src'])
                break
            elif el.name == 'video':
                if el.get('poster'):
                    item['image'] = el['poster']
                it = el.find('source')
                if it:
                    lede_html = utils.add_video(it['src'], it['type'], el.get('poster'), el.get('title'), use_videojs=True)
                elif el.get('src'):
                    lede_html = utils.add_video(el['src'], 'video/mp4', el.get('poster'), el.get('title'), use_videojs=True)

    if not lede_html and 'lede_image' in site_json:
        if isinstance(site_json['lede_image'], list):
            val = get_data_value(post_data, site_json['lede_image'])
            if val:
                img_src = val
                caption = ''
                if 'lede_caption' in site_json and isinstance(site_json['lede_caption'], list):
                    val = get_data_value(post_data, site_json['lede_caption'])
                    if val:
                        caption = val
                lede_html = utils.add_image(img_src, caption)
                item['image'] = img_src
        elif isinstance(site_json['lede_image'], dict):
            for el in utils.get_soup_elements(site_json['lede_image'], page_soup):
                img_src = get_img_src(el, site_json, base_url, '')
                if img_src:
                    item['image'] = img_src
                    caption = ''
                    if 'lede_caption' in site_json and isinstance(site_json['lede_caption'], dict):
                        for it in utils.get_soup_elements(site_json['lede_caption'], page_soup):
                            caption = it.decode_contents()
                    if caption:
                        lede_html = utils.add_image(img_src, caption)
                    else:
                        lede_html = add_image(el, site_json['lede_image'], site_json, base_url, wp_media_url)
                    break

    if post_data.get('post'):
        if 'id' not in item:
            if 'id' in post_data['post']:
                item['id'] = post_data['post']['id']
            elif 'guid' in post_data['post'] and isinstance(post_data['post']['guid'], str):
                item['id'] = post_data['post']['guid']
            elif 'guid' in post_data['post'] and isinstance(post_data['post']['guid'], dict):
                item['id'] = post_data['post']['guid']['rendered']

        if 'url' not in item:
            if 'link' in post_data['post']:
                item['url'] = post_data['post']['link']
            elif 'yoast_head_json' in post_data['post'] and 'canonical' in post_data['post']['yoast_head_json']:
                item['url'] = post_data['post']['yoast_head_json']['canonical']
            elif 'yoast_head_json' in post_data['post'] and 'og_url' in post_data['post']['yoast_head_json']:
                item['url'] = post_data['post']['yoast_head_json']['og_url']

        if 'title' not in item:
            if 'title' in post_data['post'] and isinstance(post_data['post']['title'], str):
                item['title'] = post_data['post']['title']
            elif 'title' in post_data['post'] and isinstance(post_data['post']['title'], dict):
                item['title'] = BeautifulSoup(post_data['post']['title']['rendered'], 'html.parser').get_text()
            elif 'yoast_head_json' in post_data['post'] and 'title' in post_data['post']['yoast_head_json']:
                item['title'] = post_data['post']['yoast_head_json']['title']
            elif 'yoast_head_json' in post_data['post'] and 'og_title' in post_data['post']['yoast_head_json']:
                item['title'] = post_data['post']['yoast_head_json']['og_title']
        if post_data['post'].get('parent_info') and post_data['post']['parent_info']['parent_id'] != post_data['post']['id']:
            item['title'] = post_data['post']['parent_info']['parent_title'] + ': ' + item['title']

        if not dt_pub:
            if 'date_gmt' in post_data['post']:
                dt_pub = datetime.fromisoformat(post_data['post']['date_gmt']).replace(tzinfo=pytz.utc)
            elif 'yoast_head_json' in post_data['post'] and 'article_published_time' in post_data['post']['yoast_head_json']:
                dt_pub = datetime.fromisoformat(post_data['post']['yoast_head_json']['article_published_time'])

        if not dt_mod:
            if 'modified_gmt' in post_data['post']:
                dt_mod = datetime.fromisoformat(post_data['post']['modified_gmt']).replace(tzinfo=pytz.utc)
            elif 'yoast_head_json' in post_data['post'] and 'article_modified_time' in post_data['post']['yoast_head_json']:
                dt_mod = datetime.fromisoformat(post_data['post']['yoast_head_json']['article_modified_time'])

        if not authors and 'author' in post_data['post']['_links']:
            for link in post_data['post']['_links']['author']:
                author = ''
                if site_json.get('replace_links_path'):
                    link_href = link['href'].replace(site_json['replace_links_path'][0], site_json['replace_links_path'][1])
                else:
                    link_href = link['href']
                if 'authors' in site_json:
                    m = re.search(r'\d+$', link_href)
                    if m and m.group(0) in site_json['authors']:
                        author = site_json['authors'][m.group(0)]
                    else:
                        author = site_json['authors']['default']
                if not author and 'skip_wp_user' not in args:
                    link_json = utils.get_url_json(link_href, site_json=site_json)
                    if link_json and link_json.get('name') and not re.search(r'No Author', link_json['name'], flags=re.I):
                        author = link_json['name'].strip()
                if author:
                    authors.append(author)
        if not authors and 'ns:byline' in post_data['post']['_links'] and 'skip_wp_byline' not in args:
            for link in  post_data['post']['_links']['ns:byline']:
                author = ''
                if site_json.get('replace_links_path'):
                    link_href = link['href'].replace(site_json['replace_links_path'][0], site_json['replace_links_path'][1])
                else:
                    link_href = link['href']
                link_json = utils.get_url_json(link_href, site_json=site_json)
                if link_json and link_json.get('title') and link_json['title'].get('rendered'):
                    author = link_json['title']['rendered'].strip()
                    if author:
                        authors.append(author)
        if not authors and 'wp:term' in post_data['post']['_links'] and 'skip_wp_term' not in args:
            for link in  post_data['post']['_links']['wp:term']:
                if not 'taxonomy' in link or link['taxonomy'] != 'author':
                    continue
                if site_json.get('replace_links_path'):
                    link_href = link['href'].replace(site_json['replace_links_path'][0], site_json['replace_links_path'][1])
                else:
                    link_href = link['href']
                link_json = utils.get_url_json(link_href, site_json=site_json)
                if link_json:
                    for author in link_json:
                        authors.append(author['name'])
        if not authors:
            if 'yoast_head_json' in post_data['post'] and 'author' in post_data['post']['yoast_head_json']:
                authors.append(post_data['post']['yoast_head_json']['author'])
            elif 'yoast_head_json' in post_data['post'] and 'twitter_misc' in post_data['post']['yoast_head_json'] and post_data['post']['yoast_head_json']['twitter_misc'].get('Written by'):
                authors.append(post_data['post']['yoast_head_json']['twitter_misc']['Written by'])

        if post_data['post'].get('_links') and 'wp:term' in post_data['post']['_links'] and 'skip_wp_terms' not in args:
            for link in post_data['post']['_links']['wp:term']:
                if 'taxonomy' in link and link['taxonomy'] != 'author' and link['taxonomy'] != 'channel' and link['taxonomy'] != 'contributor' and link['taxonomy'] != 'site-layouts' and link['taxonomy'] != 'lineup' and link['taxonomy'] != 'content_type' and not link['taxonomy'].startswith('tc_'):
                    if site_json.get('replace_links_path'):
                        link_href = link['href'].replace(site_json['replace_links_path'][0], site_json['replace_links_path'][1])
                    else:
                        link_href = link['href']
                    key = urlsplit(link_href).path.strip('/').split('/')[-1]
                    if key in post_data['post'] and isinstance(post_data['post'][key], list):
                        n = len(post_data['post'][key])
                        if n > 10:
                            link_href += '&per_page=' + str(math.ceil(n / 10) * 10)
                    link_json = utils.get_url_json(link_href, site_json=site_json)
                    if link_json:
                        for it in link_json:
                            if it.get('name'):
                                item['tags'].append(it['name'])
        if post_data['post'].get('terms'):
            if post_data['post']['terms'].get('category'):
                item['tags'] += [x['name'] for x in post_data['post']['terms']['category']]
            if post_data['post']['terms'].get('post_tag'):
                item['tags'] += [x['name'] for x in post_data['post']['terms']['post_tag']]
        if post_data['post'].get('class_list'):
            if isinstance(post_data['post']['class_list'], list):
                for val in post_data['post']['class_list']:
                    if not re.search(r'^(post|type|has|status|format|hentry)', val):
                        item['tags'].append(val)
            elif isinstance(post_data['post']['class_list'], dict):
                for val in post_data['post']['class_list'].values():
                    if not re.search(r'^(post|type|has|status|format|hentry)', val):
                        item['tags'].append(val)

        if 'summary' not in item:
            if 'excerpt' in post_data['post'] and isinstance(post_data['post']['excerpt'], str):
                item['summary'] = re.sub(r'^<p>|</p>$', '', post_data['post']['excerpt'].strip())
            elif 'excerpt' in post_data['post'] and isinstance(post_data['post']['excerpt'], dict):
                item['summary'] = re.sub(r'^<p>|</p>$', '', post_data['post']['excerpt']['rendered'].strip())
            elif 'yoast_head_json' in post_data['post'] and 'description' in post_data['post']['yoast_head_json']:
                item['summary'] = post_data['post']['yoast_head_json']['description']
            elif 'yoast_head_json' in post_data['post'] and 'og_description' in post_data['post']['yoast_head_json']:
                item['summary'] = post_data['post']['yoast_head_json']['og_description']

        if 'meta' in post_data['post'] and 'multi_title' in post_data['post']['meta']:
            multi_title = json.loads(post_data['post']['meta']['multi_title'])
            if 'titles' in multi_title and 'headline' in multi_title['titles'] and 'additional' in multi_title['titles']['headline'] and multi_title['titles']['headline']['additional'].get('headline_subheadline'):
                subtitle = multi_title['titles']['headline']['additional']['headline_subheadline']

        if not lede_html and 'meta' in post_data['post'] and 'nbc_page_title' in post_data['post']['meta'] and post_data['post']['meta'].get('lede_video_id'):
            el = page_soup.find('figure', class_='article-featured-media video-lead')
            if el:
                it = el.find('div', attrs={"data-react-component": "VideoPlaylist"})
                if it and it.get('data-props'):
                    data_props = json.loads(it['data-props'])
                    if data_props['videos'][0].get('isLivestream') and data_props['videos'][0]['isLivestream'] == '1':
                        lede_html = 'SKIP'
                    elif data_props['videos'][0].get('mp4Url'):
                        lede_html = utils.add_video(data_props['videos'][0]['mp4Url'], 'video/mp4', data_props['videos'][0]['poster'], data_props['videos'][0]['title'], use_videojs=True)
                        if 'image' not in item:
                            item['image'] = data_props['videos'][0]['poster']
                    elif data_props['videos'][0].get('m3u8Url'):
                        lede_html = utils.add_video(data_props['videos'][0]['m3u8Url'], 'application/x-mpegURL', data_props['videos'][0]['poster'], data_props['videos'][0]['title'])
                        if 'image' not in item:
                            item['image'] = data_props['videos'][0]['poster']
                    else:
                        lede_html = add_nbc_video(data_props['videos'][0]['videoContentId'], wpjson_path)
            if not lede_html:
                lede_html = add_nbc_video(post_data['post']['meta']['lede_video_id'], wpjson_path)

        if not lede_html and 'meta' in post_data['post'] and 'featured_bc_video_id' in post_data['post']['meta'] and isinstance(post_data['post']['meta']['featured_bc_video_id'], dict) and post_data['post']['meta']['featured_bc_video_id'].get('id') and 'shortcodes' in post_data['post']:
            video_data = next((it for it in post_data['post']['shortcodes'] if it['type'] == post_data['post']['meta']['featured_bc_video_id']['type']), None)
            if video_data:
                lede_html = utils.add_embed('https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(video_data['attributes']['account_id'], video_data['attributes']['player_id'], post_data['post']['meta']['featured_bc_video_id']['id']))
                if 'image' not in item:
                    item['image'] = post_data['post']['meta']['featured_bc_video_id']['thumbnail'][0]

        if not lede_html and post_data['post'].get('custom_gallery'):
            item['_gallery'] = []
            for it in post_data['post']['custom_gallery']:
                if it.get('caption'):
                    caption = re.sub(r'^<p>|</p>$', '', it['caption'].strip())
                elif it['image'].get('caption'):
                    caption = re.sub(r'^<p>|</p>$', '', it['image']['caption'].strip())
                else:
                    caption = ''
                item['_gallery'].append({"src": it['image']['url'], "caption": caption, "thumb": it['image']['sizes']['medium_large']})
                if it['image'].get('description'):
                    item['_gallery'][-1]['desc'] = it['image']['description']
            gallery_url = config.server + '/gallery?url=' + quote_plus(item['url'])
            caption = '<a href="' + gallery_url + '" target="_blank">View gallery</a>'
            lede_html = utils.add_image(post_data['post']['custom_gallery'][0]['image']['sizes']['large'], caption, link=gallery_url, overlay=config.gallery_button_overlay)
            args['skip_lede_img'] = False
            if 'image' not in item:
                item['image'] = post_data['post']['custom_gallery'][0]['image']['sizes']['large']

        if not lede_html and 'lead_media' in post_data['post']:
            if post_data['post']['lead_media']['type'] == 'video' and 'lakana/anvplayer' in post_data['post']['lead_media']['raw']:
                caption = ''
                poster = ''
                if 'NewsArticle' in post_data and 'associatedMedia' in post_data['NewsArticle']:
                    for it in post_data['NewsArticle']['associatedMedia']:
                        poster = it['thumbnailUrl']
                        caption = it['name']
                        if it['@type'] == 'VideoObject' and it.get('contentUrl') and post_data['post']['lead_media']['id'] in it['contentUrl']:
                            lede_html = utils.add_video(it['contentUrl'], 'application/x-mpegURL', poster, caption)
                            if 'image' not in item:
                                item['image'] = it['thumbnailUrl']
                            break
                if not lede_html:
                    # https://www.yourerie.com/news/local-news/behrend-students-helping-craft-future-vision-of-former-burton-school/
                    if post_data['post']['lead_media'].get('id'):
                        el = page_soup.find(attrs={"data-video_id": post_data['post']['lead_media']['id'], "data-video_params": True})
                    else:
                        el = page_soup.find(class_='article-featured-media--lakanaanvplayer')
                        if el:
                            el = el.find(class_='nxs-player-wrapper')
                    if el:
                        lede_html = add_nxs_player_video(el)
                        if 'image' not in item and lede_html:
                            m = re.search(r'src="([^"]+)', lede_html)
                            if m:
                                item['image'] = m.group(1)

        if not lede_html and 'meta' in post_data['post'] and '_pmc_featured_video_override_url' in post_data['post']['meta'] and post_data['post']['meta'].get('_pmc_featured_video_override_url'):
            # https://www.billboard.com/lists/alex-warren-ordinary-hot-100-number-one-third-week/
            # https://www.rollingstone.com/music/music-features/sabrina-carpenter-new-album-mans-best-friend-fame-1235359144/
            caption = ''
            poster = ''
            if post_data['post']['meta'].get('_pmc_featured_video_response_data'):
                video_data = json.loads(post_data['post']['meta']['_pmc_featured_video_response_data'])
                if video_data.get('title'):
                    caption = video_data['title']
                elif video_data.get('selectionTitle'):
                    caption = video_data['selectionTitle']
                if video_data.get('thumbnailUrl'):
                    # poster = video_data['thumbnailUrl']
                    poster = 'https://wsrv.nl/?url=' + quote_plus(video_data['thumbnailUrl'])
            if not poster and post_data['post'].get('jetpack_featured_media_url'):
                poster = post_data['post']['jetpack_featured_media_url']
            lede_html = utils.add_video(post_data['post']['meta']['_pmc_featured_video_override_url'], 'video/mp4', poster, caption, use_videojs=True)
            if poster and 'image' not in item:
                item['image'] = poster

        if not lede_html and post_data['post'].get('_links'):
            if post_data['post']['_links'].get('wp:featuredmedia') and 'skip_wp_media' not in args:
                if 'cc_featured_image_caption' in post_data['post']:
                    captions = []
                    if post_data['post']['cc_featured_image_caption'].get('caption_text'):
                        captions.append(post_data['post']['cc_featured_image_caption']['caption_text'])
                    if post_data['post']['cc_featured_image_caption'].get('source_text'):
                        if post_data['post']['cc_featured_image_caption'].get('source_url'):
                            captions.append('<a href="' + post_data['post']['cc_featured_image_caption']['source_url'] + '">' + post_data['post']['cc_featured_image_caption']['source_text'] + '</a>')
                        else:
                            captions.append(post_data['post']['cc_featured_image_caption']['source_text'])
                    caption = ' | '.join(captions)
                else:
                    caption = ''
                for link in post_data['post']['_links']['wp:featuredmedia']:
                    lede_html = add_wp_media(link['href'], site_json, caption=caption)
                    if lede_html and 'image' not in item:
                        m = re.search(r'src="([^"]+)', lede_html)
                        item['image'] = m.group(1)
                if not lede_html and post_data['post'].get('featured_media') and wp_media_url:
                    lede_html = add_wp_media(wp_media_url + str(post_data['post']['featured_media']), site_json, caption=caption)
            elif post_data['post']['_links'].get('wp:attachment') and 'skip_wp_media' not in args:
                for link in  post_data['post']['_links']['wp:attachment']:
                    link_json = utils.get_url_json(link['href'], site_json=site_json)
                    if link_json:
                        for it in link_json:
                            if 'media_type' in it and it['media_type'] == 'image':            
                                lede_html = add_wp_media(it['_links']['self'][0]['href'], site_json, media_json=it)
                                if lede_html:
                                    if 'image' not in item:
                                        m = re.search(r'src="([^"]+)', lede_html)
                                        item['image'] = m.group(1)
                                    break
                    if lede_html:
                        break

            if not lede_html and post_data['post']['_links'].get('hero_image') and 'skip_wp_media' not in args:
                for link in  post_data['post']['_links']['hero_image']:
                    lede_html = add_wp_media(link['href'], site_json)
                    if lede_html and 'image' not in item:
                        m = re.search(r'src="([^"]+)', lede_html)
                        item['image'] = m.group(1)

            if not lede_html and post_data['post']['_links'].get('landscape_image') and 'skip_wp_media' not in args:
                for link in  post_data['post']['_links']['landscape_image']:
                    lede_html = add_wp_media(link['href'], site_json)
                    if lede_html and 'image' not in item:
                        m = re.search(r'src="([^"]+)', lede_html)
                        item['image'] = m.group(1)

        if not lede_html and post_data['post'].get('jetpack_featured_media_url'):
            lede_html = utils.add_image(post_data['post']['jetpack_featured_media_url'])
            if 'image' not in item:
                item['image'] = post_data['post']['jetpack_featured_media_url']

        if not lede_html and post_data['post'].get('featured_image'):
            if post_data['post']['featured_image'].get('excerpt'):
                caption = re.sub(r'^<p>|</p>$', '', post_data['post']['featured_image']['excerpt'].strip())
            else:
                caption = ''
            lede_html = utils.add_image(post_data['post']['featured_image']['source'], caption)
            if 'image' not in item:
                item['image'] = post_data['post']['featured_image']['source']

        if not lede_html and post_data['post'].get('acf') and post_data['post']['acf'].get('featured_video'):
            lede_html = add_wp_media(site_json['wpjson_path'] + '/wp/v2/media/' + str(post_data['post']['acf']['featured_video']), site_json)

    elif article_key:
        if 'id' not in item:
            if post_data[article_key].get('@id'):
                item['id'] = post_data[article_key]['@id']
            elif post_data[article_key].get('mainEntityOfPage'):
                if isinstance(post_data[article_key]['mainEntityOfPage'], dict):
                    if post_data[article_key]['mainEntityOfPage'].get('@id'):
                        item['id'] = post_data[article_key]['mainEntityOfPage']['@id']
                    elif post_data[article_key]['mainEntityOfPage'].get('id'):
                        item['id'] = post_data[article_key]['mainEntityOfPage']['id']
                elif isinstance(post_data[article_key]['mainEntityOfPage'], str):
                    item['id'] = post_data[article_key]['mainEntityOfPage']

        if 'url' not in item and item['id'].startswith('https'):
            item['url'] = item['id']

        if 'title' not in item and post_data[article_key].get('headline'):
            item['title'] = post_data[article_key]['headline']

        if not dt_pub and post_data[article_key].get('datePublished'):
            dt_pub = datetime.fromisoformat(post_data[article_key]['datePublished'])

        if not dt_mod and post_data[article_key].get('dateModified'):
            dt_mod = datetime.fromisoformat(post_data[article_key]['dateModified'])

        if not authors:
            if post_data[article_key].get('author'):
                if isinstance(post_data[article_key]['author'], dict) and post_data[article_key]['author'].get('name'):
                    if isinstance(post_data[article_key]['author']['name'], str):
                        authors.append(post_data[article_key]['author']['name'])
                    elif isinstance(post_data[article_key]['author']['name'], list):
                        authors += post_data[article_key]['author']['name']
                elif isinstance(post_data[article_key]['author'], list):
                    for author in post_data[article_key]['author']:
                        if isinstance(author, dict) and author.get('name'):
                            if isinstance(author['name'], str):
                                authors.append(author['name'])
                            elif isinstance(author['name'], list):
                                authors += author['name']
                        elif isinstance(author, str):
                            authors.append(author)
            if not authors and post_data[article_key].get('publisher') and post_data[article_key]['publisher'].get('name'):
                authors.append(post_data[article_key]['publisher']['name'])

        if post_data[article_key].get('articleSection') and isinstance(post_data[article_key]['articleSection'], str):
            item['tags'].append(post_data[article_key]['articleSection'])

        if post_data[article_key].get('keywords') and isinstance(post_data[article_key]['keywords'], list):
            item['tags'] += post_data[article_key]['keywords'].copy()

        if 'image' not in item and post_data[article_key].get('image'):
            if 'ImageObject' in post_data and isinstance(post_data['ImageObject'], dict):
                if post_data['ImageObject'].get('url'):
                    item['image'] = post_data['ImageObject']['url']
                elif post_data['ImageObject'].get('contentUrl'):
                    item['image'] = post_data['ImageObject']['contentUrl']
                if post_data['ImageObject'].get('caption'):
                    lede_caption = post_data['ImageObject']['caption']
            elif isinstance(post_data[article_key]['image'], dict):
                if post_data[article_key]['image'].get('url'):
                    item['image'] = post_data[article_key]['image']['url']
                elif post_data[article_key]['image'].get('contentUrl'):
                    item['image'] = post_data[article_key]['image']['contentUrl']
                if post_data[article_key]['image'].get('caption'):
                    lede_caption = post_data[article_key]['image']['caption']
            elif isinstance(post_data[article_key]['image'], list):
                if post_data[article_key]['image'][0].get('url'):
                    item['image'] = post_data[article_key]['image'][0]['url']
                elif post_data[article_key]['image'][0].get('contentUrl'):
                    item['image'] = post_data[article_key]['image'][0]['contentUrl']
                if post_data[article_key]['image'][0].get('caption'):
                    lede_caption = post_data[article_key]['image'][0]['caption']

        if 'summary' not in item and post_data[article_key].get('description'):
            item['summary'] = post_data[article_key]['description']

        # if post_data[article_key].get('video') and post_data[article_key]['video'].get('embedUrl'):
        #     lede_html = utils.add_embed(post_data[article_key]['video']['embedUrl'])

    if 'meta' in post_data:
        if 'url' not in item:
            if post_data['meta'].get('og:url'):
                item['url'] = post_data['meta']['og:url']
            elif post_data['meta'].get('url'):
                item['url'] = post_data['meta']['url']

        if 'title' not in item and post_data['meta'].get('og:title'):
            item['title'] = post_data['meta']['og:title']

        if not dt_pub and post_data['meta'].get('article:published_time'):
            dt_pub = datetime.fromisoformat(post_data['meta']['article:published_time'])

        if not dt_mod and post_data['meta'].get('article:modified_time'):
            dt_mod = datetime.fromisoformat(post_data['meta']['article:modified_time'])

        if post_data['meta'].get('keywords'):
            item['tags'] += [x.strip() for x in post_data['meta']['keywords'].split(',')]
        if post_data['meta'].get('news_keywords'):
            item['tags'] += [x.strip() for x in post_data['meta']['news_keywords'].split(',')]
        if post_data['meta'].get('article:tag') and isinstance(post_data['meta']['article:tag'], list):
            item['tags'] += post_data['meta']['article:tag'].copy()
        if post_data['meta'].get('cXenseParse:taxonomy'):
            item['tags'] += [x.strip() for x in post_data['meta']['cXenseParse:taxonomy'].split('/')]

        if 'image' not in item and post_data['meta'].get('og:image'):
            if isinstance(post_data['meta']['og:image'], list):
                item['image'] = post_data['meta']['og:image'][0]
            else:
                item['image'] = post_data['meta']['og:image']

        if 'summary' not in item:
            if post_data['meta'].get('og:description'):
                item['summary'] = post_data['meta']['og:description']
            elif post_data['meta'].get('description'):
                item['summary'] = post_data['meta']['description']

    if 'id' not in item and post_id:
        item['id'] = post_id

    if 'url' not in item:
        item['url'] = url
    if 'replace_netloc' in site_json:
        item['url'] = item['url'].replace(site_json['replace_netloc'][0], site_json['replace_netloc'][1])
    if item['url'].startswith('/'):
        item['url'] = split_url.scheme + '//' + split_url.netloc + item['url']

    if re.search(r'&#\d+', item['title']):
        item['title'] = html.unescape(item['title'])

    tz = None
    if 'tz' in site_json:
        if site_json['tz'] == 'local':
            tz = pytz.timezone(config.local_tz)
        else:
            tz = pytz.timezone(site_json['tz'])

    if dt_pub:
        if dt_pub.tzinfo and dt_pub.tzinfo != timezone.utc:
            dt_pub = dt_pub.astimezone(timezone.utc)
        elif not dt_pub.tzinfo:
            if tz:
                dt_pub = tz.localize(dt_pub).astimezone(pytz.utc)
            else:
                dt_pub = dt_pub.replace(tzinfo=pytz.utc)
        item['date_published'] = dt_pub.isoformat()
        item['_timestamp'] = dt_pub.timestamp()
        item['_display_date'] = utils.format_display_date(dt_pub)

    if dt_mod:
        if dt_mod.tzinfo and dt_mod.tzinfo != timezone.utc:
            dt_mod = dt_mod.astimezone(timezone.utc)
        elif not dt_mod.tzinfo:
            if tz:
                dt_mod = tz.localize(dt_mod).astimezone(pytz.utc)
            else:
                dt_mod = dt_mod.replace(tzinfo=pytz.utc)
        item['date_modified'] = dt_mod.isoformat()

    if not authors:
        if 'WebSite' in post_data and 'name' in post_data['WebSite']:
            authors.append(post_data['WebSite']['name'])
        elif 'meta' in post_data and 'og:site_name' in post_data['meta']:
            authors.append(post_data['meta']['og:site_name'])
        else:
            authors.append(split_url.netloc)
    if authors:
        # print(authors)
        # Remove duplicates (case-sensitive, preserve order)
        # authors = list(dict.fromkeys(authors))
        authors = utils.dedupe_case_insensitive(authors)
        item['authors'] = []
        item['author'] = {"name": ""}
        n = len(authors)
        for i in range(n):
            author = re.sub(r'^By ', '', authors[i], flags=re.I)
            item['authors'].append({"name": author})
            if i > 0:
                if i == n - 1:
                    item['author']['name'] += ' and '
                else:
                    item['author']['name'] += ', '
            item['author']['name'] += author

    if len(item['tags']) == 0:
        del item['tags']
    else:
        item['tags'] = utils.dedupe_case_insensitive(item['tags'])

    item['content_html'] = ''

    if split_url.netloc == 'reason.com':
        if post_data['post']['type'] == 'podcast':
            dt = datetime.fromisoformat(post_data['NewsArticle']['datePublished'])
            m = re.findall(r'\d+', post_data['NewsArticle']['audio']['duration'])
            duration = ':'.join(m)
            lede_html = utils.add_audio_v2(post_data['NewsArticle']['audio']['contentUrl'], post_data['NewsArticle']['mainEntity']['partOfSeries']['thumbnailUrl'], item['title'], item['url'], post_data['NewsArticle']['mainEntity']['partOfSeries']['name'], post_data['NewsArticle']['mainEntity']['partOfSeries']['webFeed'].replace('/feed', ''), utils.format_display_date(dt, date_only=True), duration)
            el = page_soup.find(class_='rcom-video-episode')
            if el:
                it = el.find('iframe')
                if it:
                    lede_html += utils.add_embed(it['src'])
        elif post_data['post']['type'] == 'video':
            el = page_soup.find(class_='rcom-video-episode')
            if el:
                it = el.find('iframe')
                if it:
                    lede_html += utils.add_embed(it['src'])

    elif split_url.netloc == 'bookriot.com' and post_data['post']['type'] == 'podcast':
        page_soup = get_page_soup(item['url'], site_json)
        if page_soup:
            el = page_soup.select('div.post-content > iframe')
            if el:
                lede_html += utils.add_embed(el[0]['data-lazy-src'])

    elif (split_url.netloc == 'cyberscoop.com' or split_url.netloc == 'defensescoop.com' or split_url.netloc == 'edscoop.com' or split_url.netloc == 'fedscoop.com' or split_url.netloc == 'statescoop.com'):
        if post_data['post']['type'] == 'podcast':
            page_soup = get_page_soup(item['url'], site_json)
            if page_soup:
                el = page_soup.select('article.single-podcast div.single-podcast__player > iframe')
                if el:
                    lede_html += utils.add_embed(el[0]['src'])
                    item['image'] = post_data['post']['parsely']['meta']['image']['url']
        elif post_data['post']['type'] == 'video':
            lede_html = 'SKIP'
            item['image'] = post_data['post']['parsely']['meta']['image']['url']

    elif split_url.netloc == 'www.stereogum.com':
        if 'hero' in post_data['post']['acf'] and post_data['post']['acf']['hero'].get('image'):
            lede_html = utils.add_image(post_data['post']['acf']['hero']['image'], post_data['post']['acf']['hero'].get('caption'))
            if 'image' not in item:
                item['image'] = post_data['post']['acf']['hero']['image']
        elif 'post_hero' in post_data['post']['acf'] and post_data['post']['acf']['post_hero'].get('image'):
            lede_html = utils.add_image(post_data['post']['acf']['post_hero']['image'], post_data['post']['acf']['post_hero'].get('caption'))
            if 'image' not in item:
                item['image'] = post_data['post']['acf']['post_hero']['image']

    elif split_url.netloc == 'www.mediaplaynews.com':
        el = page_soup.select('div.entry-content > div.embed-container > iframe')
        if el:
            lede_html = utils.add_embed(el[0]['src'])
            item['image'] = post_data['post']['yoast_head_json']['og_image'][0]['url']

    elif split_url.netloc == 'latenighter.com':
        el = page_soup.select('div.entry-content > div.single-featured-image iframe')
        if el:
            lede_html = utils.add_embed(el[0]['src'])

    elif split_url.netloc == 'bigthink.com' and (post_data['post']['type'] == 'ftm_episode' or post_data['post']['type'] == 'ftm_video'):
        if 'jwplayer.com' in post_data['Article']['image']['url']:
            item['image'] = post_data['Article']['image']['url']
            lede_html = utils.add_embed(post_data['Article']['image']['url'].replace('/poster.jpg', ''))

    elif split_url.netloc == 'gvwire.com' and 'Article' in post_data and 'Video' in post_data['Article']['articleSection']:
        page_soup = get_page_soup(url, site_json, save_debug)
        if page_soup:
            el = page_soup.find('iframe', class_='jet-video-iframe')
            if el:
                lede_html = utils.add_embed(el['data-lazy-load'])
                if subtitle.startswith('('):
                    subtitle = ''

    elif split_url.netloc == 'www.onegreenplanet.org' and 'category-videos' in post_data['post']['class_list']:
        page_soup = get_page_soup(url, site_json, save_debug)
        if page_soup:
            el = page_soup.select('.main-slider-wrap > iframe')
            if el:
                lede_html = utils.add_embed(el[0]['src'])
                item['image'] = post_data['post']['jetpack_featured_media_url']

    elif split_url.netloc == 'www.theroot.com' and post_data['post']['format'] == 'video':
        video_soup = BeautifulSoup(post_data['post']['content']['rendered'], 'html.parser')
        el = video_soup.find('source')
        if el:
            item['content_html'] = utils.add_video(el['src'], el['type'], item['image'], item['title'])
            if 'embed' not in args:
                item['content_html'] += post_data['post']['excerpt']['rendered']
            return item

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if post_data['post'].get('wppr_data') and post_data['post']['wppr_data'].get('cwp_rev_product_name'):
        item['content_html'] += '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:0 1em; margin:1em 0;">'
        if post_data['post']['wppr_data'].get('cwp_rev_price'):
            item['content_html'] += '<div style="display:flex; justify-content:space-between; align-items:center; font-size:1.1em; font-weight:bold; margin:1em 0;"><div>' + post_data['post']['wppr_data']['cwp_rev_product_name'] + '</div><div>' + post_data['post']['wppr_data']['cwp_rev_price'] + '</div></div>'
        else:
            item['content_html'] += '<div style="font-size:1.1em; font-weight:bold; margin:1em 0;">' + post_data['post']['wppr_data']['cwp_rev_product_name'] + '</div>'
        if post_data['post']['wppr_data'].get('wppr_rating'):
            n = float(post_data['post']['wppr_data']['wppr_rating'])
            item['content_html'] += utils.add_score_gauge(n, str(n/10), margin='auto')
        if post_data['post']['wppr_data'].get('wppr_pros') or post_data['post']['wppr_data'].get('wppr_cons'):
            item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
            if post_data['post']['wppr_data'].get('wppr_pros'):
                item['content_html'] += '<div style="margin:1em 0; flex:1; min-width:256px;"><div style="font-weight:bold;">PROS</div><ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>'
                for it in post_data['post']['wppr_data']['wppr_pros']:
                    item['content_html'] += '<li>' + it + '</li>'
                item['content_html'] += '</ul></div>'
            if post_data['post']['wppr_data'].get('wppr_cons'):
                item['content_html'] += '<div style="margin:1em 0; flex:1; min-width:256px;"><div style="font-weight:bold;">CONS</div><ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>'
                for it in post_data['post']['wppr_data']['wppr_cons']:
                    item['content_html'] += '<li>' + it + '</li>'
                item['content_html'] += '</ul></div>'
            item['content_html'] += '</div>'
        item['content_html'] += '</div>'
    elif post_data['post'].get('meta') and post_data['post']['meta'].get('first-highlight'):
        item['content_html'] += '<h3>Highlights:</h3><ul><li>' + post_data['post']['meta']['first-highlight'] + '</li>'
        if post_data['post']['meta'].get('second-highlight'):
            item['content_html'] += '<li>' + post_data['post']['meta']['second-highlight'] + '</li>'
        if post_data['post']['meta'].get('third-highlight'):
            item['content_html'] += '<li>' + post_data['post']['meta']['third-highlight'] + '</li>'
        item['content_html'] += '</ul><hr style="margin:1em 0;">'
    elif split_url.netloc == 'www.rollingstone.com' and post_data['post']['meta'].get('pmc-review-rating'):
        item['content_html'] += utils.add_stars(float(post_data['post']['meta']['pmc-review-rating']))
    elif split_url.netloc == 'www.cgmagonline.com' and post_data['post']['type'] == 'review':
        if post_data['post']['acf'].get('blu_review_rating'):
            item['content_html'] += utils.add_score_gauge(10 * post_data['post']['acf']['blu_review_rating'], str(post_data['post']['acf']['blu_review_rating']))
        item['content_html'] += '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; padding:1em;">'
        item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;">' + post_data['post']['acf']['blu_review_name'] + '</div>'
        item['content_html'] += '<p>' + post_data['post']['acf']['blu_review_final_header'] + '</p>'
        item['content_html'] += '<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:8px; margin:8px;">'
        if post_data['post']['acf'].get('product_image'):
            link_json = utils.get_url_json(site_json['wpjson_path'] + '/wp/v2/media/' + str(post_data['post']['acf']['product_image']), site_json=site_json)
            if link_json:
                item['content_html'] += '<div style="flex:1; min-width:160px; max-width:160px;"><img src="' + link_json['source_url'] + '" style="width:100%;"/></div>'
        item['content_html'] += '<div style="flex:2; min-width:320px;"><ul>'
        if 'game' in paths:
            item['content_html'] += '<li>Developer: ' + post_data['post']['acf']['developer'] + '</li>'
            item['content_html'] += '<li>Publisher: ' + post_data['post']['acf']['publisher'] + '</li>'
            item['content_html'] += '<li>Platforms: ' + post_data['post']['acf']['platforms'] + '</li>'
            if post_data['post']['acf'].get('played_on_system'):
                val = []
                for it in post_data['post']['acf']['played_on_system']:
                    link_json = utils.get_url_json(site_json['wpjson_path'] + '/wp/v2/game-platform/' + str(it), site_json=site_json)
                    if link_json:
                        val.append('<a href="{}" target="_blank">{}</a>'.format(link_json['link'], link_json['name']))
                if val:
                    item['content_html'] += '<li>Played On: ' + ', '.join(val) + '</li>'
            if post_data['post']['acf'].get('game_genre_tax'):
                val = []
                for it in post_data['post']['acf']['game_genre_tax']:
                    link_json = utils.get_url_json(site_json['wpjson_path'] + '/wp/v2/game-genre/' + str(it), site_json=site_json)
                    if link_json:
                        val.append('<a href="' + link_json['link'] + '" target="_blank">' + link_json['name'] + '</a>')
                if val:
                    item['content_html'] += '<li>Genre: ' + ', '.join(val) + '</li>'
            if post_data['post']['acf'].get('esrb_rating'):
                val = []
                for it in post_data['post']['acf']['esrb_rating']:
                    link_json = utils.get_url_json(site_json['wpjson_path'] + '/wp/v2/esrb-rating/' + str(it), site_json=site_json)
                    if link_json:
                        val.append('<a href="' + link_json['link'] + '" target="_blank">' + link_json['name'] + '</a>')
                if val:
                    item['content_html'] += '<li>ESRB: ' + ', '.join(val) + '</li>'
            dt = datetime.fromisoformat(post_data['post']['acf']['release_date'])
            month = dt.strftime('%b')
            if month != 'May':
                month += '.'
            item['content_html'] += '<li>Release Date: {} {}, {}</li>'.format(month, dt.day, dt.year)
        elif 'movie' in paths:
            item['content_html'] += '<li>IMDB: <a href="' + post_data['post']['acf']['imdb_link'] + '" target="_blank">Link</a></li>'
            dt = datetime.fromisoformat(post_data['post']['acf']['premiere_date'])
            month = dt.strftime('%b')
            if month != 'May':
                month += '.'
            item['content_html'] += '<li>Premier Date: {} {}, {}</li>'.format(month, dt.day, dt.year)
            item['content_html'] += '<li>Runtime: ' + post_data['post']['acf']['running_time'] + '</li>'
            item['content_html'] += '<li>Genre: ' + ', '.join(post_data['post']['acf']['film_genre']) + '</li>'
            item['content_html'] += '<li>Director: ' + post_data['post']['acf']['directors'] + '</li>'
            item['content_html'] += '<li>Cast: ' + post_data['post']['acf']['stars'] + '</li>'
            item['content_html'] += '<li>MPAA Rating: ' + post_data['post']['acf']['mpaa_rating'] + '</li>'
        elif 'tv-series' in paths:
            item['content_html'] += '<li>IMDB: <a href="' + post_data['post']['acf']['imdb_tv_link'] + '" target="_blank">Link</a></li>'
            if post_data['post']['acf'].get('premiere_date'):
                dt = datetime.fromisoformat(post_data['post']['acf']['premiere_date'])
                month = dt.strftime('%b')
                if month != 'May':
                    month += '.'
                item['content_html'] += '<li>Premier Date: {} {}, {}</li>'.format(month, dt.day, dt.year)
            if post_data['post']['acf'].get('number_of_episodes'):
                item['content_html'] += '<li>Number of Episodes: ' + str(post_data['post']['acf']['number_of_episodes']) + '</li>'
            if isinstance(post_data['post']['acf']['tv_genre'], str):
                item['content_html'] += '<li>Genre: ' + post_data['post']['acf']['tv_genre'] + '</li>'
            elif isinstance(post_data['post']['acf']['tv_genre'], list):
                item['content_html'] += '<li>Genre: ' + ', '.join(post_data['post']['acf']['tv_genre']) + '</li>'
            if post_data['post']['acf'].get('studio'):
                item['content_html'] += '<li>Platform: ' + post_data['post']['acf']['studio'] + '</li>'
            if post_data['post']['acf'].get('creators'):
                item['content_html'] += '<li>Creator(s): ' + post_data['post']['acf']['creators'] + '</li>'
            item['content_html'] += '<li>Cast: ' + post_data['post']['acf']['stars'] + '</li>'
            item['content_html'] += '<li>Rating: ' + post_data['post']['acf']['rating'] + '</li>'
        elif 'hardware' in paths:
            item['content_html'] += '<li>Manufacturer: ' + post_data['post']['acf']['manufacturer'] + '</li>'
            item['content_html'] += '<li>Type: ' + post_data['post']['acf']['hardware_type'] + '</li>'
            item['content_html'] += '<li>MSRP: $' + post_data['post']['acf']['msrp_price'] + '</li>'
        elif 'tabletop' in paths:
            item['content_html'] += '<li>Publisher: ' + post_data['post']['acf']['publisher'] + '</li>'
            item['content_html'] += '<li>MSRP: $' + post_data['post']['acf']['msrp'] + '</li>'
            if post_data['post']['acf'].get('art_by'):
                item['content_html'] += '<li>Art By: ' + post_data['post']['acf']['art_by'] + '</li>'
            if post_data['post']['acf'].get('designer'):
                item['content_html'] += '<li>Designer: ' + post_data['post']['acf']['designer'] + '</li>'
            item['content_html'] += '<li>No. of Players: ' + post_data['post']['acf']['number_of_players'] + '</li>'
            item['content_html'] += '<li>Age Rating: ' + post_data['post']['acf']['age_rating'] + '</li>'
        elif 'book' in paths:
            item['content_html'] += '<li>Author: ' + post_data['post']['acf']['author'] + '</li>'
            if post_data['post']['acf'].get('isbn'):
                item['content_html'] += '<li>ISBN: ' + post_data['post']['acf']['isbn'] + '</li>'
            item['content_html'] += '<li>Publisher: ' + post_data['post']['acf']['book_publisher'] + '</li>'
            item['content_html'] += '<li>Retail Price: $' + post_data['post']['acf']['retail_price'] + '</li>'
            if post_data['post']['acf'].get('art_by'):
                item['content_html'] += '<li>Art By: ' + post_data['post']['acf']['art_by'] + '</li>'
        item['content_html'] += '</ul></div></div>'
        if post_data['post']['acf'].get('amazon_affiliate_link'):
            item['content_html'] += utils.add_button(post_data['post']['acf']['amazon_affiliate_link'], 'Buy Online')
        if post_data['post']['acf'].get('review_supplied'):
            item['content_html'] += '<div><small><em>' + post_data['post']['acf']['review_supplied'] + '</em></small></div>'
        item['content_html'] += '</div>'
    elif split_url.netloc == 'www.truthdig.com':
        if post_data['post']['type'] == 'photo_essays':
            page_soup = get_page_soup(item['url'], site_json, save_debug)
            if page_soup:
                for el in page_soup.select('ul.td-slides > li.td-slides-slide'):
                    for it in el.find_all('span', attrs={"style": "font-weight: 400"}):
                        it.unwrap()
                    it = el.find(class_='td-slide-content')
                    if it:
                        desc = it.decode_contents()
                    else:
                        desc = ''
                    if el.img:
                        img_src = get_img_src(el.img, site_json, base_url, '', 2000)
                        thumb = get_img_src(el.img, site_json, base_url, '', 800)
                        item['content_html'] += utils.add_image(thumb, '', link=img_src, desc=desc)
                    else:
                        item['content_html'] += desc
        elif post_data['post']['type'] == 'newsletter_td':
            if not 'author' in item:
                item['author'] = {
                    "name": "Truthdig Newsletter"
                }
                item['authors'] = []
                item['authors'].append(item['author'])
            page_soup = get_page_soup(item['url'], site_json, save_debug)
            if page_soup:
                for el in page_soup.select('.ngl-article-title > a'):
                    item['content_html'] += utils.add_embed(el['href'])
                return item
    elif split_url.netloc == 'bleedingcool.com' and post_data['post'].get('acf'):
        if post_data['post']['acf'].get('itemReviewed'):
            item['content_html'] += '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:1em; margin:1em 0;">'
            if post_data['post']['acf'].get('itemReviewed') or post_data['post']['acf'].get('reviewBody'):
                item['content_html'] += '<div style="font-size:1.2em; font-weight:bold;">' + post_data['post']['acf']['itemReviewed'] + '</div>'
            if post_data['post']['acf'].get('reviewImage') and post_data['post']['acf'].get('reviewRating'):
                item['content_html'] += '<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:1em; margin:1em 0;"><div style="flex:1; min-width:256px;">' + utils.add_image(post_data['post']['acf']['reviewImage']['url']) + '</div><div style="flex:1; min-width:256px;">' + utils.add_score_gauge(10 * float(post_data['post']['acf']['reviewRating']), post_data['post']['acf']['reviewRating'], margin='auto') + '</div></div>'
            elif post_data['post']['acf'].get('reviewRating'):
                item['content_html'] += utils.add_score_gauge(10 * float(post_data['post']['acf']['reviewRating']), post_data['post']['acf']['reviewRating'], margin='0.5em auto')
            if post_data['post']['acf'].get('reviewBody'):
                item['content_html'] += '<p>' + post_data['post']['acf']['reviewBody'] + '</p>'
            if post_data['post']['acf'].get('reviewCredits'):
                item['content_html'] += '<div><strong>Credits:</strong></div><ul style="margin-top:0;">'
                vals = []
                for x in post_data['post']['acf']['reviewCredits']:
                    if x['creditTitle'] not in vals:
                        vals.append(x['creditTitle'])
                for val in vals:
                    item['content_html'] += '<li>' + val + ': ' + ', '.join([x['creditValue'] for x in post_data['post']['acf']['reviewCredits'] if x['creditTitle'] == val]) + '</li>'
                item['content_html'] += '</ul>'
            item['content_html'] += '</div>'
        if post_data['post']['acf'].get('post_summary'):
            item['content_html'] += '<h4 style="margin-bottom:0;">Article Summary</h4>' + post_data['post']['acf']['post_summary']

    content_html = ''
    if split_url.netloc == 'bookriot.com':
        if post_data['post'].get('content_top_premium'):
            content_html += post_data['post']['content_top_premium']
        if post_data['post'].get('content_middle_premium'):
            content_html += post_data['post']['content_middle_premium']
        if post_data['post'].get('content_bottom_premium'):
            content_html += post_data['post']['content_bottom_premium']
        if not content_html:
            content_html = post_data['post']['content']['rendered']
    elif split_url.netloc == 'www.stereogum.com':
        for it in post_data['post']['acf']['article_modules']:
            if it['acf_fc_layout'] == 'text_block':
                content_html += it['copy']
            elif it['acf_fc_layout'] == 'image_block':
                content_html += utils.add_image(it['image'], it.get('caption'))
            elif it['acf_fc_layout'] == 'sub_headline':
                item['content_html'] = '<p><em>' + it['copy'] + '</em></p>' + item['content_html']
            elif it['acf_fc_layout'] == 'membership_block':
                continue
            else:
                logger.warning('unhandled acf_fc_layout type {} in {}'.format(it['acf_fc_layout'], item['url']))
    elif split_url.netloc == 'nerdist.com':
        # The first paragraph is sometimes not closed
        def fix_nerdist_content(matchobj):
            if matchobj.group(2) == '</':
                return matchobj.group(0)
            else:
                return matchobj.group(1) + '</p>' + matchobj.group(2) + matchobj.group(3)
        content_html = re.sub(r'^(<p>.*?)(</?)(p|div|figure)', fix_nerdist_content, post_data['post']['content']['rendered'].strip())
        content_html = re.sub(r'</p></p>$', '</p>', content_html)
        # utils.write_file(content_html, './debug/debug.txt')
    elif split_url.netloc == 'theshaderoom.com':
        # The first paragraph is sometimes not closed
        def fix_theshaderoom_content(matchobj):
            if '</p>' in matchobj.group(0):
                return matchobj.group(0)
            return re.sub(r'<h5', r'</p><h5', matchobj.group(0))
        content_html = re.sub(r'^<p>.*?<p>', fix_theshaderoom_content, post_data['post']['content']['rendered'].strip())
    elif split_url.netloc == 'nextdraft.com':
        if len(paths) == 2:
            page_soup = get_page_soup(item['url'], site_json, save_debug)
            if page_soup:
                for el in page_soup.select('.single-blurb-title > a'):
                    it = get_content(el['href'], args, site_json, False)
                    if it:
                        item['content_html'] += '<h2><a href="' + it['url'] + '" target="_blank">' + it['title'] + '</a></h2>' + it['content_html']
                return item
        else:
            content_html = re.sub(r'<br\s?/>\s*\+', '<br/><br/>+', post_data['post']['content']['rendered'])
    elif split_url.netloc == 'www.gematsu.com':
        content_html = post_data['post']['content']['rendered'].replace('<!--more-->', '</p>')
    elif split_url.netloc == 'www.gig-blog.net':
        content_html = post_data['post']['content']['rendered']
        for i, el in enumerate(page_soup.find_all(class_='ngg-galleryoverview')):
            content_html = content_html.replace('ngg_shortcode_{}_placeholder'.format(i), str(el))
    elif 'content' in post_data['post']:
        if isinstance(post_data['post']['content'], dict):
            if post_data['post']['content'].get('clean_render'):
                content_html = post_data['post']['content']['clean_render']
            elif post_data['post']['content'].get('rendered'):
                content_html = post_data['post']['content']['rendered']
            elif post_data['post']['content'].get('blocks'):
                n = len(post_data['post']['content']['blocks'])
                for i, block in enumerate(post_data['post']['content']['blocks']):
                    if block['name'] == 'core/spacer':
                        if i > 0:
                            if re.search(r'/pym|/ad', post_data['post']['content']['blocks'][i - 1]['name']):
                                continue
                        if i < n - 1:
                            if re.search(r'/pym|/ad', post_data['post']['content']['blocks'][i + 1]['name']):
                                continue
                    content_html += format_block(block, site_json, base_url)
        elif isinstance(post_data['post']['content'], str):
            content_html = post_data['post']['content']
    elif 'content' in site_json:
        for el in utils.get_soup_elements(site_json['content'], page_soup):
            if 'unwrap' in site_json['content'] and site_json['content']['unwrap'] == False:
                content_html = str(el)
            else:
                content_html = el.decode_contents()
    elif post_data['post'].get('acf') and post_data['post']['acf'].get('page_layout'):
        for block in post_data['post']['acf']['page_layout']:
            if block['acf_fc_layout'] == 'layout_wysiwyg':
                content_html += block['component_wysiwyg']['content']
            elif block['acf_fc_layout'] == 'layout_large_image':
                content_html += add_wp_media(wp_media_url + str(block['component_large_image']['image']), site_json, caption=block['component_large_image'].get('caption_override'))
            elif block['acf_fc_layout'] == 'layout_accordion':
                for i, it in enumerate(block['component_accordion']['entries']):
                    if i == 0:
                        content_html += '<details style="padding:1em 0; border-top:1px solid light-dark(#333,#ccc); border-bottom:1px solid light-dark(#333,#ccc);">'
                    else:
                        content_html += '<details style="padding:1em 0; border-bottom:1px solid light-dark(#333,#ccc);">'
                    content_html += '<summary style="font-weight:bold;">' + it['title'] + '</summary><div style="margin:1em 0 1em 1em;>' + it['content'] + '</div></details>'
            elif block['acf_fc_layout'] == 'layout_featured_resource' or block['acf_fc_layout'] == 'layout_featured_action':
                # related content link
                continue
            else:
                logger.warning('unhandled acf_fc_layout {} in {}'.format(block['acf_fc_layout'], item['url']))

    if 'LiveBlogPosting' in post_data and 'family' in site_json and site_json['family'] == 'nexstar':
        el = page_soup.find('script', id='liveblog-js-extra')
        if el:
            i = el.string.find('{')
            j = el.string.rfind('}') + 1
            liveblog_settings = json.loads(el.string[i:j])
            liveblog_json = utils.get_url_json(liveblog_settings['endpoint_url'] + 'get-entries/1/' + liveblog_settings['latest_entry_id'] + '-' +  liveblog_settings['latest_entry_timestamp'], site_json=site_json)
            if liveblog_json:
                if save_debug:
                    utils.write_file(liveblog_json, './debug/liveblog.json')
                for it in liveblog_json['entries']:
                    content_html += '<hr style="margin:2em 0;"/>'
                    # TODO: not sure on timezone
                    tz_loc = pytz.timezone(config.local_tz)
                    dt_loc = datetime.fromtimestamp(it['entry_time'])
                    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
                    content_html += '<div><small>Update: ' + utils.format_display_date(dt) + '</small></div>'
                    content_html += '<h3 style="margin-bottom:0;">' + it['entry_title'] + '</h3>'
                    content_html += '<div><small>By ' + re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in it['authors']])) + '</small></div>'
                    content_html += it['render']
    if post_data['post'].get('buylinks'):
        for key, val in post_data['post']['buylinks'].items():
            if val['uuid']:
                content_html = content_html.replace('<' + val['uuid'] + '/>', val['content'])
    if post_data['post'].get('mzed_course'):
        # content_html = content_html.replace('<' + post_data['post']['mzed_course']['uuid'] + '/>', post_data['post']['mzed_course']['content'])
        content_html = content_html.replace('<' + post_data['post']['mzed_course']['uuid'] + '/>', '')

    if page_soup and 'add_content' in site_json:
        for it in site_json['add_content']:
            for el in utils.get_soup_elements(it, page_soup):
                if 'position' in it and it['position'] == 'bottom':
                    if 'unwrap' in it and it['unwrap'] == True:
                        content_html += el.decode_contents()
                    else:
                        content_html += str(el)
                else:
                    if 'unwrap' in it and it['unwrap'] == True:
                        content_html = el.decode_contents() + content_html
                    else:
                        content_html = str(el) + content_html

    content_html = format_content(content_html, item['url'], args, site_json, post_data, page_soup, wpjson_path, wp_media_url).strip()

    if lede_html and lede_html != 'SKIP' and not content_html.startswith('<figure') and ('skip_lede_img' not in args or args['skip_lede_img'] == False) and ('acf' not in post_data['post'] or 'top_featured_image' not in post_data['post']['acf'] or post_data['post']['acf']['top_featured_image'] == True):
        item['content_html'] = lede_html + item['content_html']
    elif 'add_lede_img' in args and 'image' in item:
        item['content_html'] = utils.add_image(item['image'], lede_caption) + item['content_html']

    if subtitle and not (subtitle.endswith('[&hellip;]') or 'Read more</a>' in subtitle):
        item['content_html'] = '<p><em>' + subtitle + '</em></p>' + item['content_html']

    item['content_html'] += content_html

    if post_data['post'].get('type') and post_data['post']['type'] == 'pmc_list':
        # https://www.billboard.com/lists/alex-warren-ordinary-hot-100-number-one-third-week/
        list_url = wpjson_path + site_json['posts_path']['list_item']
        for it in post_data['post']['meta']['pmc_list_order']:
            list_item = utils.get_url_json(list_url + '/' + str(it), site_json=site_json)
            if list_item:
                item['content_html'] += '<hr style="margin:2em 0;">'
                if list_item.get('parsely'):
                    item['content_html'] += '<h2>' + list_item['parsely']['meta']['headline'] + '</h2>'
                    if list_item['parsely']['meta']['image'].get('url'):
                        # TODO: caption?
                        item['content_html'] += utils.add_image(list_item['parsely']['meta']['image']['url'])
                else:
                    item['content_html'] += '<h2>' + re.sub(r'^<p>|</p>$', '', list_item['title']['rendered'].strip()) + '</h2>'
                    if list_item['_links'].get('wp:featuredmedia'):
                        item['content_html'] += add_wp_media(list_item['_links']['wp:featuredmedia'][0]['href'], site_json)
                item['content_html'] += format_content(list_item['content']['rendered'], item['url'], args, site_json, page_soup, wpjson_path)

    elif post_data['post'].get('type') and post_data['post']['type'] == 'pmc-gallery':
        # https://www.billboard.com/photos/musicians-who-died-2025-1235881159/
        # TODO: get gallery photo info from items in post_data['post']['meta']['pmc-gallery']
        if not page_soup:
            page_soup = get_page_soup(item['url'], site_json, save_debug)
        if page_soup:
            el = page_soup.find('script', id='pmc-gallery-vertical-js-extra')
            if el:
                i = el.string.find('{')
                j = el.string.rfind('}') + 1
                pmc_gallery = json.loads(el.string[i:j])
                item['_gallery'] = []
                item['content_html'] += '<h3><a href="' + config.server + '/gallery?url=' + quote_plus(item['url']) + '" target="_blank">View photo gallery</a></h3>'
                for it in pmc_gallery['gallery']:
                    img_src = it['sizes']['pmc-gallery-xxl']['src']
                    thumb = it['sizes']['pmc-gallery-l']['src']
                    if it.get('image_credit'):
                        caption = it['image_credit']
                    else:
                        caption = ''
                    desc = ''
                    if it.get('title'):
                        desc += '<h3>' + it['title'] + '</h3>'
                    if it.get('caption'):
                        desc += it['caption']
                    item['_gallery'].append({"src": img_src, "caption": caption, "thumb": thumb, "desc": desc})
                    item['content_html'] += '<hr style="margin:2em 0;">' + utils.add_image(img_src, caption) + desc

    elif post_data['post'].get('type') and post_data['post']['type'] == 'nerdist_video':
        item['content_html'] = utils.add_embed('https://www.youtube.com/watch?v=' + post_data['post']['meta']['youtube_id']) + item['content_html']
        if 'author' not in item:
            item['author'] = {
                "name": post_data['post']['meta']['mpx_channel']
            }
            item['authors'] = []
            item['authors'].append(item['author'])       

    elif split_url.netloc == 'variety.com':
        if post_data['post']['meta'].get('variety-review-origin'):
            item['content_html'] += '<hr style="margin:1em 0;"><p style="font-weight:bold;">' + item['title'] + '</p>'
            item['content_html'] += '<p style="font-weight:bold;">' + post_data['post']['meta']['variety-review-origin'] + '</p>'
        if post_data['post']['meta'].get('variety-primary-credit'):
            item['content_html'] += '<p>Production: ' + post_data['post']['meta']['variety-primary-credit'] + '</p>'
        if post_data['post']['meta'].get('variety-secondary-credit'):
            item['content_html'] += '<p>Crew: ' + post_data['post']['meta']['variety-secondary-credit'] + '</p>'
        if post_data['post']['meta'].get('variety-primary-cast'):
            item['content_html'] += '<p>Cast: ' + post_data['post']['meta']['variety-primary-cast'] + '</p>'

    elif split_url.netloc == 'www.hollywoodreporter.com':
        if post_data['post']['meta'].get('pmc-review-title'):
            item['content_html'] += '<hr style="margin:1em 0;"><h3>' + post_data['post']['meta']['pmc-review-title'] + '</h3>'
        if post_data['post']['meta'].get('_synopsis'):
            item['content_html'] += '<p><em>' + post_data['post']['meta']['_synopsis'] + '</em></p>'
        if post_data['post']['meta'].get('thr-review-summary-credits'):
            item['content_html'] += '<p>' + post_data['post']['meta']['thr-review-summary-credits']
            if post_data['post']['meta'].get('thr-review-mpaa-rating'):
                item['content_html'] += '<strong>Rated:</strong> ' + post_data['post']['meta']['thr-review-mpaa-rating'] + '<br>'
            if post_data['post']['meta'].get('thr-review-running-time'):
                item['content_html'] += '<strong>Run time:</strong> ' + post_data['post']['meta']['thr-review-running-time']
            item['content_html'] += '</p>'

    elif split_url.netloc == 'www.pewresearch.org':
        if post_data['post'].get('report_materials'):
            item['content_html'] += '<h3>Report Materials</h3><ul style=\'list-style-type:"📄&nbsp;"\'>'
            for it in post_data['post']['report_materials']:
                item['content_html'] += '<li><a href="' + it['url'] + '" target="_blank">' + it['label'] + '</a></li>'
            item['content_html'] += '</ul>'
        if post_data['post'].get('report_pagination') and post_data['post']['report_pagination'].get('next_post'):
            item['content_html'] += '<p>Next page: <a href="' + config.server + '/content?read&url=' + quote_plus(post_data['post']['report_pagination']['next_post']['link']) + '" target="_blank">' + post_data['post']['report_pagination']['next_post']['title'] + '</a></p>'

    elif split_url.netloc == 'metro.co.uk' and 'mdt_review' in post_data['post'] and post_data['post']['mdt_review'].get('rating'):
        item['content_html'] = utils.add_stars(post_data['post']['mdt_review']['rating']) + item['content_html']

    elif split_url.netloc == 'theawesomer.com' and post_data['post']['_links'].get('wp:attachment'):
        for link in post_data['post']['_links']['wp:attachment']:
            link_json = utils.get_url_json(link['href'], site_json=site_json)
            if link_json:
                for it in link_json:
                    if it['media_type'] != 'image':
                        logger.warning('unhandled media_type {} in {}'.format(it['media_type'], link['href']))
                        continue
                    m = re.search(r'youtube-video-([^/]+)', it['link'])
                    if m:
                        for el in page_soup.find_all('iframe'):
                            if m.group(1).lower() in el['src'].lower():
                                item['content_html'] += utils.add_embed(el['src']) + '<div>&nbsp;</div>'
                                break
                    else:
                        item['content_html'] += add_wp_media(it['_links']['self'][0]['href'], site_json, it, caption_is_desc=True) + '<div>&nbsp;</div>'

    elif split_url.netloc == 'secretlosangeles.com':
        item['content_html'] = re.sub(r'\[trackLink[^\]]*link_url="([^"]+)"[^\]]*\](.*?)\[/trackLink\]', r'<a href="\1">\2</a>', item['content_html'])

    elif split_url.netloc == 'bigthink.com' and (post_data['post']['type'] == 'ftm_episode' or post_data['post']['type'] == 'ftm_video'):
        el = page_soup.find('div', class_='prose', attrs={"x-show": re.compile(r'transcript')})
        if el:
            item['content_html'] += '<hr style="margin:1em 0;"/><h2>Transcript</h2>' + el.decode_contents()

    elif split_url.netloc == 'shkspr.mobi' and 'Review' in post_data:
        if 'reviewRating' in post_data['Review'] and post_data['Review']['reviewRating'].get('ratingValue'):
            item['content_html'] += utils.add_stars(float(post_data['Review']['reviewRating']['ratingValue']))

    elif split_url.netloc == 'www.thurrott.com' and 'membership-content' in post_data['post']['class_list']:
        item['content_html'] += '<h3 style="text-align:center; color:red;"><a href="' + item['url'] + '" target="_blank">A subscription is required for the full content</a></h3>'

    elif 'family' in site_json and site_json['family'] == 'postmedia':
        if 'NewsArticle' in post_data and post_data['NewsArticle'].get('video'):
            item['content_html'] += utils.add_video(post_data['NewsArticle']['video'][0]['contentUrl'], 'application/x-mpegURL', utils.clean_url(post_data['NewsArticle']['video'][0]['thumbnailUrl']), post_data['NewsArticle']['video'][0]['headline'])
        else:
            el = page_soup.select('.featured-video > #video-container')
            if el and el[0].get('data-video-id'):
                item['content_html'] += utils.add_embed('https://cdn.jwplayer.com/v2/media/' + el[0]['data-video-id'])

    if site_json.get('text_encode'):
        def encode_item(item, enc):
            if isinstance(item, str):
                # print(item)
                item = item.encode(enc, 'replace').decode('utf-8', 'replace')
            elif isinstance(item, list):
                for i, it in enumerate(item):
                    item[i] = encode_item(it, enc)
            elif isinstance(item, dict):
                for key, val in item.items():
                    item[key] = encode_item(val, enc)
            return item
        encode_item(item, site_json['text_encode'])

    return item


def format_content(content_html, url, args, site_json=None, post_data=None, page_soup=None, wpjson_path='', wp_media_url='', module_format_content=None):
    utils.write_file(content_html, './debug/debug.html')

    split_url = urlsplit(url)
    base_url = split_url.scheme + '://' + split_url.netloc

    soup = BeautifulSoup(content_html, 'html.parser')

    # remove comments
    for el in soup.find_all(string=lambda text: isinstance(text, Comment)):
        el.extract()

    if site_json:
        if 'remove_nbsp_paragraphs' in site_json:
            for el in soup.find_all('p', string='\xa0'):
                el.decompose()
        if 'rename' in site_json:
            for it in site_json['rename']:
                for el in utils.get_soup_elements(it['old'], soup):
                    if 'tag' in it['new']:
                        el.name = it['new']['tag']
                    if 'before' in it['new']:
                        el.string = it['new']['before'] + el.string
                    if 'after' in it['new']:
                        el.string += it['new']['after']
                    if 'attrs' in it['new']:
                        for key, val in el.attrs.copy().items():
                            if key == 'href' or key == 'src':
                                continue
                            elif 'keep_attrs' in it['old'] and key in it['old']['keep_attrs']:
                                continue
                            else:
                                del el[key]
                        for key, val in it['new']['attrs'].items():
                            if el.get(key):
                                el[key] = val + el[key]
                            else:
                                el[key] = val
        if 'replace' in site_json:
            for it in site_json['replace']:
                for el in utils.get_soup_elements(it, soup):
                    el.replace_with(BeautifulSoup(it['new_html'], 'html.parser'))
        if 'insert_after' in site_json:
            for it in site_json['insert_after']:
                for el in utils.get_soup_elements(it, soup):
                    el.insert_after(BeautifulSoup(it['new_html'], 'html.parser'))
        if 'insert_before' in site_json:
            for it in site_json['insert_before']:
                for el in utils.get_soup_elements(it, soup):
                    el.insert_before(BeautifulSoup(it['new_html'], 'html.parser'))
        if 'decompose' in site_json:
            for it in site_json['decompose']:
                for el in utils.get_soup_elements(it, soup):
                    el.decompose()
        if 'unwrap' in site_json:
            for it in site_json['unwrap']:
                for el in utils.get_soup_elements(it, soup):
                    el.unwrap()
        if 'wrap' in site_json:
            for it in site_json['wrap']:
                for el in utils.get_soup_elements(it, soup):
                    new_el = soup.new_tag(it['new']['tag'])
                    if it['new'].get('attrs'):
                        new_el.attrs = it['new']['attrs']
                    el.wrap(new_el)
        if 'clear_attrs' in site_json and isinstance(site_json['clear_attrs'], list):
            for it in site_json['clear_attrs']:
                for el in utils.get_soup_elements(it, soup):
                    if el.name == 'a':
                        el.attrs = {key: val for key, val in el.attrs.items() if key in ['href', 'target']}
                    else:
                        el.attrs = {}

    el = soup.find('body')
    if el:
        soup = el
    el = soup.find(class_='entry-content')
    if el:
        soup = el

    for el in soup.find_all('pba-embed'):
        new_html = html.unescape(el['code'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    utils.write_file(str(soup), './debug/debug2.html')

    if site_json.get('tables'):
        for tag in site_json['tables']:
            tables = utils.get_soup_elements(tag, soup)
            if tables:
                for table in tables:
                    if table.name == 'table':
                        utils.format_table(table)

    if site_json.get('gallery'):
        for tag in site_json['gallery']:
            galleries = utils.get_soup_elements(tag, soup)
            if galleries:
                for gallery in galleries:
                    new_html = add_gallery(gallery, tag, site_json, base_url, wp_media_url)
                    if new_html:
                        new_el = BeautifulSoup(new_html, 'html.parser')
                        gallery.replace_with(new_el)
                    else:
                        logger.warning('unhandled gallery ' + str(gallery))

    if site_json.get('images'):
        for tag in site_json['images']:
            images = utils.get_soup_elements(tag, soup)
            if images:
                new_html = ''
                for image in images:
                    new_html = add_image(image, tag, site_json, base_url, wp_media_url)
                    if new_html:
                        new_el = BeautifulSoup(new_html, 'html.parser')
                        if 'unwrap_figure' in tag:
                            new_el.img['style'] = new_el.img['style'].replace('margin-left:auto;', 'margin:1em auto;').replace('margin-right:auto; ', '')
                            new_el.figure.unwrap()
                        image.replace_with(new_el)

    if site_json.get('extras'):
        for tag in site_json['extras']:
            extras = utils.get_soup_elements(tag, soup)
            if extras:
                for extra in extras:
                    new_html = ''
                    if extra.get('id') and extra['id'] == 'gp-review-results':
                        for el in extra.find_all('i', class_='fa'):
                            el.decompose()
                        new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:light-dark(#ccc,#333); padding:1em; margin:1em 0;">'
                        el = extra.find(class_='gp-rating-score')
                        if el:
                            n = el.get_text(strip=True)
                            new_html +=  utils.add_score_gauge(10 * float(n), n, margin='auto')
                        el = extra.find(class_='gp-rating-text')
                        if el and el.string:
                            new_html += '<p style="font-size:1.1em; font-weight:bold; text-transform:uppercase; text-align:center;">' + el.string.strip() + '</p>'
                        el = soup.find(id='gp-summary')
                        if el:
                            it = el.find(id="gp-summary-title")
                            if it:
                                new_html += '<div><strong>' + it.get_text(strip=True) + '</strong></div>'
                                it.decompose()
                            else:
                                new_html += '<div><strong>Summary</strong></div>'
                            new_html += '<p>' + el.decode_contents() + '</p>'
                            el.decompose()
                        new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                        el = extra.find(id='gp-good-points')
                        if el:
                            new_html += '<div style="flex:1; min-width:240px; color:ForestGreen;">'
                            it = el.find(id='gp-good-title')
                            if it:
                                new_html += '<div><strong>' + it.get_text(strip=True) + '</strong></div>'
                            else:
                                new_html += '<div><strong>Good</strong></div>'
                            it = el.find('ul')
                            if it:
                                it.attrs = {}
                                new_html += str(it).replace('<ul>', '<ul style=\'list-style-type:"✓&nbsp;"\'>')
                            new_html += '</div>'
                        el = extra.find(id='gp-bad-points')
                        if el:
                            new_html += '<div style="flex:1; min-width:240px; color:Maroon;">'
                            it = el.find(id='gp-bad-title')
                            if it:
                                new_html += '<div><strong>' + it.get_text(strip=True) + '</strong></div>'
                            else:
                                new_html += '<div><strong>Bad</strong></div>'
                            it = el.find('ul')
                            if it:
                                it.attrs = {}
                                new_html += str(it).replace('<ul>', '<ul style=\'list-style-type:"✗&nbsp;"\'>')
                            new_html += '</div>'
                        new_html += '</div>'
                        if soup.find(class_='gp-rating-box'):
                            new_html += '<ul style="margin:0 1em; padding:0;">'
                            for el in soup.select('.gp-rating-box > .gp-hub-fields > .gp-hub-field'):
                                new_html += '<li>'
                                it = el.find(class_='gp-hub-field-name')
                                if it:
                                    new_html += it.decode_contents() + ' '
                                it = el.find(class_='gp-hub-field-list')
                                if it:
                                    new_html += it.decode_contents()
                                new_html += '</li>'
                            new_html += '</ul>'
                            soup.find(class_='gp-rating-box').decompose()
                        new_html += '</div>'
                    elif extra.get('id') and extra['id'] == 'review-body':
                        # https://www.techadvisor.com/article/2837108/ninja-artisan-electric-outdoor-pizza-oven-and-air-fryer-review.html
                        new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:1em; margin:1em 0;">'
                        el = extra.find('img', class_='review-logo')
                        if el:
                            new_html += '<div style="text-align:center;"><img src="' + el['src'] + '" width="160"></div>'
                        el = extra.find(class_='starRating')
                        if el:
                            m = re.search(r'rating:\s*(\d+)', el['style'])
                            if m:
                                new_html += utils.add_stars(int(m.group(1)))
                        new_html += '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:1em 0;">'
                        el = extra.select('h3#pros + ul')
                        if el:
                            el[0].attrs = {}
                            new_html += '<div style="flex:1; min-width:240px; color:ForestGreen;"><div style="font-weight:bold;">Pros</div>' + str(el[0]).replace('<ul>', '<ul style=\'list-style-type:"✓&nbsp;"\'>') + '</div>'
                        el = extra.select('h3#cons + ul')
                        if el:
                            el[0].attrs = {}
                            new_html += '<div style="flex:1; min-width:240px; color:Maroon;"><div style="font-weight:bold;">Cons</div>' + str(el[0]).replace('<ul>', '<ul style=\'list-style-type:"✗&nbsp;"\'>') + '</div>'
                        new_html += '</div>'
                        el = extra.select('h3#our-verdict + p')
                        if el:
                            new_html += '<div style="font-weight:bold;">Our Verdict</div>' + str(el[0])
                        new_html += '</div>'
                    elif extra.get('id') and extra['id'] == 'review_summary':
                        new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:0 1em; margin:1em 0;">'
                        el = extra.select('#review_score > h3')
                        if el:
                            m = re.search(r'^\d+', el[0].get_text(strip=True))
                            if m:
                                new_html += utils.add_score_gauge(10 * int(m.group(0)), m.group(0), margin='0.5em auto')
                        el = extra.select('#review_score > .extratop')
                        if el:
                            new_html += '<div style="text-align:center; text-transform:uppercase; font-size:1.2em;">' + el[0].decode_contents() + '</div>'
                        el = extra.find(id='review_summary_text')
                        if el:
                            new_html += el.decode_contents()
                        new_html += '</div>'
                    elif extra.get('id') and extra['id'] == 'omc-review-wrapper':
                        new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:0 1em; margin:1em 0;">'
                        el = extra.select('#omc-criteria-final-score > span[itemprop=\"rating\"] > h3')
                        if el:
                            new_html += utils.add_stars(float(el[0].string))
                        el = extra.select('#omc-criteria-final-score > h4')
                        if el:
                            new_html += '<div style="text-align:center; font-size:larger; font-weight:bold;">' + el[0].get_text() + '</div>'
                        el = extra.find(id='omc-short-summary')
                        if el:
                            new_html += el.decode_contents()
                        new_html += '</div>'
                    elif extra.get('id') and extra['id'] == 'widgets-sec':
                        new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:1em; margin:1em 0;">'
                        new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                        el = extra.select('.specs-img > img')
                        if el:
                            new_html += '<div style="margin:1em 0; flex:1; min-width:256px;"><img src="' + el[0]['src'] + '" style="width:100%; max-height:240px; object-fit:contain;"></div>'
                        el = extra.select('.ex_rating > span')
                        if el:
                            n = el[0].get_text(strip=True)
                            new_html += '<div style="margin:1em 0; flex:1; min-width:256px;">' + utils.add_score_gauge(10 * float(n), n, margin='0.5em auto') + '</div>'
                        new_html += '</div>'
                        if extra.find(class_='specs-rating'):
                            for el in extra.select('.specs-rating > .specs-heading'):
                                it = el.select('.r_value > div')
                                if it:
                                    n = it[0].get_text(strip=True)
                                    new_html += utils.add_bar(el.span.get_text(), float(n), 10, False)
                        if extra.find(class_=['pros', 'cons']):
                            new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;"><div style="margin:1em 0; flex:1; min-width:256px;">'
                            el = extra.find(class_='pros')
                            if el.h4:
                                new_html += '<div style="font-weight:bold;">' + el.h4.get_text() + '</div>'
                            else:
                                new_html += '<div style="font-weight:bold;">Pros</div>'
                            new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + el.ul.decode_contents() + '</ul>'
                            new_html += '</div><div style="margin:1em 0; flex:1; min-width:256px;">'
                            el = extra.find(class_='cons')
                            if el.h4:
                                new_html += '<div style="font-weight:bold;">' + el.h4.get_text() + '</div>'
                            else:
                                new_html += '<div style="font-weight:bold;">Cons</div>'
                            new_html += '<ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>' + el.ul.decode_contents() + '</ul>'
                            new_html += '</div></div>'
                        new_html += '</div>'
                    elif extra.get('class'):
                        # print(extra['class'])
                        if 'bgr-product-review-block' in extra['class']:
                            el = extra.select('div.bgr-product-review-info h3')
                            if el:
                                new_html += '<h3 style="margin-bottom:0;">' + el[0].get_text(strip=True) + '</h3>'
                            el = extra.select('div.bgr-product-review-info p')
                            if el:
                                new_html += '<div>' + el[0].decode_contents() + '</div>'
                            el = extra.select('div.bgr-product-review-info div.bgr-product-review-stars > span.sr-only')
                            if el:
                                m = re.search(r'\d', el[0].get_text())
                                if m:
                                    new_html += utils.add_stars(int(m.group(0)))
                            if extra.find(class_='bgr-product-review-pros-cons'):
                                for el in extra.select('ul > li'):
                                    el.attrs = {}
                                    if el.svg:
                                        el.svg.decompose()
                                new_html += '<div style="display:flex; flex-wrap:wrap; gap:8px; padding:8px; margin:1em 0; border:1px solid light-dark(#333,#ccc); border-radius:10px;">'
                                new_html += '<div style="flex:1; min-width:240px; color:ForestGreen;"><div style="text-align:center; font-weight:bold;">Pros</div>'
                                el = extra.find('ul', class_='pros')
                                if el:
                                    new_html += str(el).replace('<ul>', '<ul style=\'list-style-type:"✓&nbsp;"\'>')
                                new_html += '</div>'
                                new_html += '<div style="flex:1; min-width:240px; color:Maroon;"><div style="text-align:center; font-weight:bold;">Cons</div>'
                                el = extra.find('ul', class_='cons')
                                if el:
                                    new_html += str(el).replace('<ul>', '<ul style=\'list-style-type:"✗&nbsp;"\'>')
                                new_html += '</div></div>'
                            if extra.find(class_='bgr-product-review-vendors'):
                                for el in extra.select('div.bgr-product-review-vendors > table tr:has(td > a.see-it)'):
                                    caption = ''
                                    it = el.find('td', class_='sale-price')
                                    if it:
                                        caption += it.get_text(strip=True)
                                    else:
                                        it = el.find('td', class_='vendor-product-info')
                                        if it:
                                            caption += it.get_text(strip=True)
                                    it = el.find('span', class_='vendor-name')
                                    if it:
                                        caption += ' at ' + it.get_text(strip=True)
                                    else:
                                        it = el.find('img', class_='vendor-logo')
                                        if it:
                                            caption += ' at ' + it['alt'].replace('logo', '').replace('-', ' ').strip().title()
                                    it = el.find('a', class_='see-it')
                                    new_html += utils.add_button(it['href'], caption)
                        elif 'abr-post-review' in extra['class']:
                            # https://www.nintendo-insider.com/mario-kart-world-review/
                            el = extra.find(class_='abr-review-text')
                            if el:
                                el.attrs = {}
                                el.name = 'h1'
                                el['style'] = 'text-align:center;'
                                for it in el.find_all('span'):
                                    it.unwrap()
                                extra.insert_after(el)
                                extra.decompose()
                        elif 'tdb_single_review_overall' in extra['class']:
                            # https://www.nme.com/reviews/film-reviews/echo-valley-review-sydney-sweeney-julianne-moore-apple-tv-3869048
                            n = len(extra.find_all('i', class_='td-icon-star'))
                            new_html = utils.add_stars(n)
                        elif 'wp-block-kelseymedia-blocks-block-verdict' in extra['class']:
                            new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:0 1em; margin:1em 0;">'
                            el = extra.find(class_='c-stuff-verdict__title')
                            if el:
                                new_html += '<h3>' + el.get_text(strip=True) + '</h3>'
                            el = extra.find(class_='c-stuff-verdict')
                            if el and el.get('data-rating'):
                                new_html += utils.add_stars(int(el['data-rating']))
                            el = extra.find(class_='c-stuff-verdict__text')
                            if el:
                                el.attrs = {}
                                new_html += str(el)
                            if extra.find(class_='c-stuff-verdict__pros_cons'):
                                new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                                el = extra.find(class_='c-stuff-verdict__pros-items')
                                if el:
                                    for it in el.find_all('li'):
                                        it.attrs = {}
                                    new_html += '<div style="margin:1em 0; flex:1; min-width:256px;"><div style="font-weight:bold;">PROS</div><ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + el.decode_contents() + '</ul></div>'
                                el = extra.find(class_='c-stuff-verdict__cons-items')
                                if el:
                                    for it in el.find_all('li'):
                                        it.attrs = {}
                                    new_html += '<div style="margin:1em 0; flex:1; min-width:256px;"><div style="font-weight:bold;">CONS</div><ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>' + el.decode_contents() + '</ul></div>'
                                new_html += '</div>'
                            new_html += '</div>'
                        elif 'wp-block-kelseymedia-blocks-block-stuff-says' in extra['class']:
                            new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:0 1em; margin:1em 0;">'
                            el = extra.find(class_='c-stuff-says__title')
                            if el:
                                new_html += '<h3>' + el.string + '</h3>'
                            el = extra.find(class_='c-stuff-says__rating-score')
                            if el:
                                new_html += utils.add_stars(int(el.string))
                            el = extra.find(class_='c-stuff-says__verdict')
                            if el:
                                el.attrs = {}
                                new_html += str(el)
                            if extra.find(class_='c-stuff-says__good-and-bad-stuff'):
                                new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;"><div style="margin:1em 0; flex:1; min-width:256px;">'
                                el = extra.find(class_='c-stuff-says__good-stuff-title')
                                if el:
                                    new_html += '<div style="font-weight:bold;">' + el.get_text() + '</div>'
                                new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>'
                                for el in extra.find_all(class_='c-stuff-says__good-stuff-item'):
                                    new_html += '<li>' + el.decode_contents() + '</li>'
                                new_html += '</ul></div><div style="margin:1em 0; flex:1; min-width:256px;">'
                                el = extra.find(class_='c-stuff-says__bad-stuff-title')
                                if el:
                                    new_html += '<div style="font-weight:bold;">' + el.get_text() + '</div>'
                                new_html += '<ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>'
                                for el in extra.find_all(class_='c-stuff-says__bad-stuff-item'):
                                    new_html += '<li>' + el.decode_contents() + '</li>'
                                new_html += '</ul></div></div>'
                            new_html += '</div>'
                        elif 'wp-block-kelseymedia-blocks-block-quick-buy-now-button' in extra['class']:
                            el = extra.find('a')
                            if el:
                                new_html = utils.add_button(utils.get_redirect_url(el['href']), el.get_text())
                            else:
                                extra.decompose()
                                continue
                        elif 'lets-review-block__wrap' in extra['class']:
                            new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:0 1em 1em 1em; margin:1em 0;">'
                            el = extra.find(class_='lets-review-block__title')
                            if el:
                                new_html += '<h3 style="text-align:center;">' + el.get_text(strip=True) + '</h3>'
                            if extra.find(class_='lets-review-block__conclusion'):
                                el = extra.find(class_='lets-review-block__conclusion__title')
                                if el:
                                    new_html += '<div><b>' + el.get_text(strip=True) + '</b></div>'
                                el = extra.find(class_='lets-review-block__conclusion')
                                new_html += '<p>' + el.decode_contents() + '</p>'
                            el = extra.select('.lets-review-block__final-score .score')
                            if el:
                                n = el[0].get_text(strip=True)
                                new_html += utils.add_score_gauge(int(n.replace('.', '')), n)
                            else:
                                el = extra.find(class_='lets-review-block__final-score')
                                if el:
                                    n = el.get_text(strip=True)
                                    new_html += utils.add_score_gauge(n.replace('.', ''), n)
                            for el in extra.select('.lets-review-block__crits > .lets-review-block__crit'):
                                it = el.find(class_='lets-review-block__crit__title')
                                new_html += utils.add_bar(it.string, int(el['data-score']), 100)
                            if extra.find(class_='lets-review-block__proscons'):
                                new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                                el = extra.find(class_='lets-review-block__pros')
                                if el:
                                    new_html += '<div style="margin:1em 0; flex:1; min-width:256px;"><div style="font-weight:bold;">'
                                    it = el.find(class_='proscons__title')
                                    if it:
                                        new_html += it.get_text(strip=True)
                                    else:
                                        new_html += 'Pros'
                                    new_html += '</div><ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>'
                                    for it in el.find_all(class_='lets-review-block__pro'):
                                        new_html += '<li>' + it.get_text(strip=True) + '</li>'
                                    new_html += '</ul></div>'
                                el = extra.find(class_='lets-review-block__cons')
                                if el:
                                    new_html += '<div style="margin:1em 0; flex:1; min-width:256px;"><div style="font-weight:bold;">'
                                    it = el.find(class_='proscons__title')
                                    if it:
                                        new_html += it.get_text(strip=True)
                                    else:
                                        new_html += 'Cons'
                                    new_html += '</div><ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>'
                                    for it in el.find_all(class_='lets-review-block__con'):
                                        new_html += '<li>' + it.get_text(strip=True) + '</li>'
                                    new_html += '</ul></div>'
                                new_html += '</div>'
                            if extra.find(class_='lets-review-block__aff'):
                                el = extra.select('.lets-review-block__aff > .lets-review-block__title')
                                if el:
                                    new_html += '<div style="text-align:center; font-weight:bold;">' + el[0].get_text(strip=True) + '</div>'
                                for el in extra.select('.lets-review-block__aff a.aff-button'):
                                    it = el.find(class_='button-title')
                                    new_html += utils.add_button(el['href'], it.get_text(strip=True))
                            new_html += '</div>'
                        elif 'review-box' in extra['class'] and split_url.netloc == 'macsources.com':
                            new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:0 1em 1em 1em; margin:1em 0;">'
                            el = extra.find(class_='heading')
                            if el:
                                new_html += '<h3 style="text-align:center;">' + el.string + '</h3>'
                            el = extra.select('.verdict-box > .overall > .number > .value')
                            if el:
                                n = el[0].get_text().strip(' %')
                                new_html += utils.add_score_gauge(int(n), n)
                            el = extra.select('.verdict-box > .overall > .verdict')
                            if el:
                                new_html += '<div style="text-align:center; font-size:1.1em; font-weight:bold;">' + el[0].string + '</div>'
                            el = extra.select('.verdict-box > .summary')
                            if el:
                                new_html += el[0].decode_contents()
                            new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                            el = extra.find(class_='the-pros-list')
                            if el:
                                for it in el.find_all('svg'):
                                    it.decompose()
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px;"><div style="font-weight:bold;">PROS</div><ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + el.decode_contents() + '</ul></div>'
                            el = extra.find(class_='the-cons-list')
                            if el:
                                for it in el.find_all('svg'):
                                    it.decompose()
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px;"><div style="font-weight:bold;">CONS</div><ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>' + el.decode_contents() + '</ul></div>'
                            new_html += '</div>'
                            for el in extra.select('ul.criteria > li'):
                                it = el.find(class_='rating')
                                if it:
                                    n = int(it.get_text().strip(' %'))
                                    it = el.find(class_='label')
                                    new_html += utils.add_bar(it.get_text(), n, 100)
                            new_html += '</div>'
                        elif 'review-box' in extra['class'] and split_url.netloc == 'gizmodo.com':
                            new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:0 1em;">'
                            el = extra.find('p', class_='text-2xl')
                            if el:
                                new_html += '<h3>' + el.string + '</h3>'
                            el = extra.find('p', class_='text-lg')
                            if el:
                                el.attrs = {}
                                new_html += str(el)
                            n = 0.0
                            for el in extra.find_all(class_='fas'):
                                if 'fa-star-half-alt' in el['class']:
                                    n += 0.5
                                elif 'fa-star' in el['class']:
                                    n += 1.0
                                else:
                                    el.decompose()
                            if n > 0:
                                new_html += utils.add_stars(n)
                            el = extra.select('p:-soup-contains("Pros") + ul')
                            if el:
                                new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px;"><div style="font-weight:bold;">Pros</div>'
                                for it in el[0].find_all('li'):
                                    it.attrs = {}
                                new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + el[0].decode_contents() + '</ul></div>'
                                el = extra.select('p:-soup-contains("Cons") + ul')
                                if el:
                                    new_html += '<div style="margin:1em 0; flex:1; min-width:256px;"><div style="font-weight:bold;">Cons</div>'
                                    for it in el[0].find_all('li'):
                                        it.attrs = {}
                                    new_html += '<ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>' + el[0].decode_contents() + '</ul></div>'
                                new_html += '</div>'
                            new_html += '</div>'
                        elif 'review-wu-content' in extra['class']:
                            # https://gadgetsandwearables.com/2025/06/27/xiaomi-smart-band-10-review/
                            el = extra.find(class_='review-wu-grade-content')
                            if el and el.span and el.span.string.replace('.', '').isnumeric():
                                n = int(el.span.string.replace('.', ''))
                                # new_html += '<div style="margin:1em auto; width:8rem; aspect-ratio:1; line-height:8rem; text-align:center; font-size:3rem; font-weight:bold; border:solid 24px #8DC153; border-radius:50%; mask:linear-gradient(red 0 0) padding-box, conic-gradient(red var(--p, {}%), transparent 0%) border-box;">{}</div>'.format(n, el.span.string)
                                new_html += utils.add_score_gauge(n, el.span.string, 'auto')
                            el = extra.find(class_='review-wu-bars')
                            if el:
                                for it in el.find_all(class_='rev-option'):
                                    new_html += utils.add_bar(it.h3.get_text(strip=True), int(it['data-value']), 100, False)
                            new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                            for it in extra.find_all(class_=['pros', 'cons']):
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px;">'
                                if it.h2:
                                    new_html += '<div style="font-weight:bold;">' + it.h2.get_text(strip=True) + '</div>'
                                if it.ul:
                                    if 'pros' in it['class']:
                                        new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + it.ul.decode_contents() + '</ul>'
                                    elif 'cons' in it['class']:
                                        new_html += '<ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>' + it.ul.decode_contents() + '</ul>'
                                new_html += '</div>'
                            new_html += '</div>'
                        elif 'review-rating-container' in extra['class']:
                            # https://wccftech.com/review/gamesir-supernova-controller-review-aesthetics-optimal-wireless-experience-in-one-package/
                            el = extra.select('div.rating-box > span')
                            if el and el[0].string.replace('.', '').isnumeric():
                                n = int(el[0].string.replace('.', ''))
                                new_html = utils.add_score_gauge(n, el[0].string, 'auto')
                        elif 'review-summary' in extra['class'] and extra.name == 'section':
                            # https://www.the-ambient.com/reviews/reolink-duo-3-wifi-review/
                            el = extra.find('div', class_='star-rating')
                            if el:
                                n = len(el.select('div.full-stars > i.fa-star')) + 0.5 * len(el.select('div.full-stars > i.fa-star-half'))
                                new_el = BeautifulSoup(utils.add_stars(n), 'html.parser')
                                el.replace_with(new_el)
                            extra.name = 'div'
                            extra.attrs = {}
                            extra['style'] = 'margin:1em 0; padding:0 1em 1em 1em; background-color:#e5e7eb; border-radius:10px;'
                        elif 'review-summary' in extra['class']:
                            new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:0 1em 1em 1em; margin:1em 0;">'
                            el = extra.select('.verdict-score > h2')
                            if el:
                                new_html += '<h2 style="margin-bottom:0;">' + el[0].get_text() + '</h2>'
                            el = extra.select('.verdict-score > img')
                            if el:
                                m = re.search(r'/reviews/(\d+)\.svg', el[0]['src'])
                                if m:
                                    new_html += utils.add_score_gauge(10 * int(m.group(1)), m.group(1), margin="0.5em auto")
                            el = extra.find(class_='summary')
                            if el:
                                el.attrs = {}
                                new_html += str(el)
                            if extra.find(class_='pros-and-cons'):
                                new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em; margin-top:1em;"><div style="flex:1; min-width:256px;">'
                                el = extra.select('.pros-and-cons > .pros > span')
                                if el:
                                    new_html += '<div style="font-weight:bold;">' + el[0].get_text(strip=True) + '</div>'
                                else:
                                    new_html += '<div style="font-weight:bold;">Pros</div>'
                                el = extra.select('.pros-and-cons > .pros > ul')
                                if el:
                                    new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + el[0].decode_contents() + '</ul>'
                                new_html += '</div><div style="flex:1; min-width:256px;">'
                                el = extra.select('.pros-and-cons > .cons > span')
                                if el:
                                    new_html += '<div style="font-weight:bold;">' + el[0].get_text(strip=True) + '</div>'
                                else:
                                    new_html += '<div style="font-weight:bold;">Cons</div>'
                                el = extra.select('.pros-and-cons > .cons > ul')
                                if el:
                                    new_html += '<ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>' + el[0].decode_contents() + '</ul>'
                                new_html += '</div></div>'
                            for el in extra.select('.affiliates > .starwidget'):
                                if el.get('data-geo') and 'US' in el['data-geo'].split(',') and el.get('data-afflink'):
                                    if el.get('data-affctatext'):
                                        caption = el['data-affctatext']
                                    else:
                                        caption = ''
                                        if el.get('data-affprice'):
                                            caption += el['data-affprice'] + ' '
                                        else:
                                            caption += 'Check prices '
                                        if el.get('data-affmerchant'):
                                            caption += 'at ' + el['data-affmerchant']
                                    new_html += utils.add_button(el['data-afflink'], caption)
                            new_html += '</div>'
                        elif 'review-verdict' in extra['class']:
                            # https://wccftech.com/review/gamesir-supernova-controller-review-aesthetics-optimal-wireless-experience-in-one-package/
                            for el in extra.find_all('p', recursive=False):
                                new_html += '<p style="font-style:italic;">' + el.decode_contents() + '</p>'
                            if extra.find(class_='review-pros-cons'):
                                new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                                for el in extra.select('div.review-pros-cons > ul'):
                                    new_html += '<div style="margin:1em 0; flex:1; min-width:256px;">'
                                    if el.h6:
                                        caption = el.h6.get_text(strip=True)
                                        new_html += '<div style="font-weight:bold;">' + caption + '</div>'
                                        el.h6.decompose()
                                        if caption.lower() == 'pros':
                                            new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + el.decode_contents() + '</ul>'
                                        elif caption.lower() == 'cons':
                                            new_html += '<ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>' + el.decode_contents() + '</ul>'
                                    else:
                                        new_html += str(el)
                                    new_html += '</div>'
                                new_html += '</div>'
                        elif 'review_grade' in extra['class']:
                            el = extra.find('span')
                            if el:
                                n = el.get_text(strip=True)
                                if n.replace('.', '').isnumeric():
                                    new_html = utils.add_score_gauge(10 * float(n), n, margin='auto', size='240px')
                        elif 'single-score' in extra['class']:
                            # https://thespool.net
                            el = extra.find(class_='single-score-number')
                            if el:
                                n = el.get_text(strip=True)
                                if n.replace('.', '').isnumeric():
                                    new_html = utils.add_score_gauge(10 * float(n), n, margin='auto', size='240px')
                        elif 'summary-panel' in extra['class']:
                            # https://thespool.net
                            new_html = '<ul>'
                            for el in extra.find_all(class_='summary-panel-single'):
                                new_html += '<li>'
                                if el.span:
                                    new_html += '<strong>' + el.span.string + '</strong>: '
                                    el.span.decompose()
                                for it in el.find_all('a'):
                                    if it['href'].startswith('/'):
                                        it['href'] = base_url + it['href']
                                    new_html += str(it) + ', '
                                    it.decompose()
                                if el.get_text():
                                    new_html += el.decode_contents()
                                if new_html.strip().endswith(','):
                                    new_html = new_html.strip()[:-1]
                                new_html += '</li>'
                            new_html = new_html.replace('<li></li>', '') + '</ul>'
                        elif 'wppr-review-container' in extra['class']:
                            # https://techaeris.com
                            img_src = ''
                            el = soup.find('img', src=re.compile(r'Editors-Choice|Highly-rated|Top-Pick', flags=re.I))
                            if el:
                                img_src = el['src']
                                it = el.find_parent(class_='wp-block-image')
                                if it:
                                    it.decompose()
                            n = -1
                            el = extra.select('div.review-wu-grade img')
                            if el:
                                m = re.search(r'ratings-(\d+)', el[0]['src'])
                                if m:
                                    n = int(m.group(1))
                            if n > 0 and img_src:
                                new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em; align-items:center; justify-content:center;">'
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px;"><div style="text-align:center;"><img src="' + img_src + '" style="width:200px;"></div></div>'
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px;">' + utils.add_score_gauge(n, str(n / 10), 'auto') + '</div>'
                                new_html += '</div>'
                            elif n > 0:
                                new_html += utils.add_score_gauge(n, str(n / 10), 'auto')
                            elif img_src:
                                new_html += '<div style="text-align:center;"><img src="' + img_src + '" style="width:200px;"></div>'
                            for el in extra.select('div.review-wu-bars > div.rev-option'):
                                new_html += utils.add_bar(el.h3.get_text(strip=True), int(el['data-value'])/10, 10, False)
                            new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                            for it in extra.find_all(class_=['pros', 'cons']):
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px;">'
                                if it.h2:
                                    new_html += '<div style="font-weight:bold;">' + it.h2.get_text(strip=True) + '</div>'
                                if it.ul:
                                    if 'pros' in it['class']:
                                        new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + it.ul.decode_contents() + '</ul>'
                                    elif 'cons' in it['class']:
                                        new_html += '<ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>' + it.ul.decode_contents() + '</ul>'
                                new_html += '</div>'
                            new_html += '</div>'
                            for el in extra.select('div.affiliate-button > a'):
                                new_html += utils.add_button(el['href'], el.get_text(strip=True))
                        elif 'xe-positives-negatives' in extra['class'] or 'xe-review-reports' in extra['class']:
                            el = extra.find('h2')
                            if el:
                                new_html += str(el)
                            new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em; align-items:center; justify-content:center; margin:1em 0; padding:1em; border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:light-dark(#ccc,#333);">'
                            el = extra.find(class_='xe-review-reports__rating')
                            if el:
                                if el.get_text(strip=True).isnumeric():
                                    n = int(el.get_text(strip=True))
                                    new_html += '<div style="margin:1em 0; flex:1; min-width:256px;">' + utils.add_score_gauge(10 * n, n, margin='auto', size='240px') + '</div>'
                            el = extra.find('ul', class_='xe-review-reports__list')
                            if el:
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px;"><ul>'
                                for li in el.find_all('li'):
                                    it = li.find(class_='xe-review-reports__icon')
                                    if it:
                                        if 'icon-1' in it['class']:
                                            new_html += '<li style=\'margin:0.5em 0; color:ForestGreen; list-style-type:"✓&nbsp;"\'>'
                                        elif 'icon-2' in it['class']:
                                            new_html += '<li style=\'margin:0.5em 0; color:Maroon; list-style-type:"✗&nbsp;"\'>'
                                        elif 'icon-3' in it['class']:
                                            new_html += '<li style=\'margin:0.5em 0; list-style-type:"—&nbsp;"\'>'
                                        else:
                                            new_html += '<li style="margin:0.5em 0;">'
                                        it.decompose()
                                        new_html += li.decode_contents() + '</li>'
                                    else:
                                        new_html += '<li>' + li.decode_contents() + '</li>'
                                new_html += '</ul></div>'
                            new_html += '</div>'
                        elif 'wp-block-gamurs-review-summary' in extra['class']:
                            new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em; align-items:center; justify-content:center; border:1px solid light-dark(#333,#ccc); border-radius:10px;  background-color:#e5e7eb; padding:0 1em; margin-top:1em;">'
                            el = extra.find(class_='wp-block-gamurs-review-summary__number-rating')
                            if el:
                                n = int(el.get_text(strip=True))
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px;">' + utils.add_score_gauge(10 * n, n, 'auto') + '</div>'
                            el = extra.find(class_='wp-block-gamurs-review-summary__text')
                            if el:
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px;">' + el.decode_contents() + '</div>'
                            new_html += '</div>'
                        elif 'wp-review-zine-template' in extra['class']:
                            new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:1em; margin:1em 0;">'
                            el = extra.find(class_='review-total-box')
                            if el:
                                m = re.search(r'^[\d\.]+', el.string)
                                if m:
                                    n = float(m.group(0))
                                    new_html += utils.add_score_gauge(10 * n, n, 'auto')
                            el = extra.find(class_='review-desc')
                            if el:
                                new_html += el.decode_contents()
                            for el in extra.select('ul.review-list > li'):
                                it = el.find(class_='review-result-text')
                                if it:
                                    m = re.search(r'^[\d\.]+', it.string)
                                    n = float(m.group(0))
                                    caption = re.sub(r'[\s\d\.\-/]+$', '', el.span.get_text(strip=True))
                                    new_html += utils.add_bar(caption, n, 10, False)
                            new_html += '</div>'
                        elif 'wp-review-das-template' in extra['class']:
                            new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:1em; margin:1em 0;">'
                            el = extra.select('div.review-total-box > div')
                            if el and el[0].string.replace('.', '').isnumeric():
                                n = float(el[0].string)
                                new_html += utils.add_stars(n)
                            #     n = 20 * float(el[0].string)
                            #     new_html += utils.add_score_gauge(n, el[0].string, 'auto')
                            el = extra.find(class_='review-desc')
                            if el:
                                for it in el.find_all('p'):
                                    it.attrs = {}
                                new_html += el.decode_contents()
                            if extra.find(class_='review-pros-cons'):
                                new_html += '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:1em 0;">'
                                new_html += '<div style="flex:1; min-width:240px; color:ForestGreen;"><div><strong>Pros</strong></div>'
                                el = extra.select('div.review-pros > ul')
                                if el:
                                    new_html += str(el[0]).replace('<ul>', '<ul style=\'list-style-type:"✓&nbsp;"\'>')
                                new_html += '</div><div style="flex:1; min-width:240px; color:Maroon;"><div><strong>Cons</strong></div>'
                                el = extra.select('div.review-cons > ul')
                                if el:
                                    new_html += str(el[0]).replace('<ul>', '<ul style=\'list-style-type:"✗&nbsp;"\'>')
                                new_html += '</div></div>'
                            new_html += '</div>'
                            for el in extra.select('ul.review-links > li > a'):
                                new_html += utils.add_button(el['href'], el.string)
                        elif 'final-verdict-container' in extra['class']:
                            new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:0 1em; margin-top:1em;">'
                            if 'Product' in post_data and 'review' in post_data['Product'] and 'reviewRating' in post_data['Product']['review'] and 'ratingValue' in post_data['Product']['review']['reviewRating']:
                                n = post_data['Product']['review']['reviewRating']['ratingValue']
                                new_html += utils.add_score_gauge(10 * n, n, 'auto')
                            else:
                                el = extra.select('div.rating-wheel-outer > img')
                                if el:
                                    m = re.search(r'(\d+)\.png', el[0]['src'])
                                    if m:
                                        n = int(m.group(0))
                                        new_html += utils.add_score_gauge(10 * n, n, 'auto')
                            new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                            el = extra.select('div.the-good-container > p.content')
                            if el:
                                el[0].attrs = {}
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px; color:ForestGreen;"><div><strong>THE GOOD</strong></div>' + str(el[0]) + '</div>'
                            el = extra.select('div.the-bad-container > p.content')
                            if el:
                                el[0].attrs = {}
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px; color:Maroon;"><div><strong>THE BAD</strong></div>' + str(el[0]) + '</div>'
                            new_html += '</div>'
                            el = extra.find(class_='review-final-verdict')
                            if el:
                                new_html += '<div>Final Verdict: <strong>' + el.string + '</strong></div>'
                            el = extra.find(class_='review-content')
                            if el:
                                new_html += '<p>' + el.decode_contents() + '</p>'
                            el = extra.find(class_='review-note')
                            if el:
                                new_html += '<p><small><em>' + el.decode_contents() + '</em></small></p>'
                            new_html += '</div>'
                        elif 'wp-block-group' in extra['class'] and extra.find(class_='ratingBlock'):
                            el = extra.select('div.ratingColumnOne > h3.wp-block-heading')
                            if el:
                                new_html += '<h3 style="text-align:center;">' + el[0].string + '</h3>'
                            el = extra.select('div.ratingColumnOne > h4.wp-block-heading')
                            if el:
                                new_html += '<div style="font-weight:bold; text-align:center;">' + el[0].string + '</div>'
                            el = extra.find(attrs={"itemprop": "ratingValue"})
                            if el:
                                new_html += utils.add_stars(float(el['content']))
                            el = extra.find(class_='edChoice')
                            if el and el.img:
                                new_html += '<div style="text-align:center;"><img src="' + el.img['src'] + '" style="width:160px;"></div>'
                            el = extra.find(class_='pullQuote')
                            if el:
                                new_html += '<p style="text-align:center;">' + el.decode_contents() + '</p>'
                            if extra.find(class_='proCon'):
                                new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                                for el in extra.select('div.proCon > div.wp-block-column'):
                                    new_html += '<div style="margin:1em 0; flex:1; min-width:256px;">'
                                    if el.h4:
                                        caption = el.h4.get_text(strip=True)
                                        new_html += '<div style="font-weight:bold;">' + caption + '</div>'
                                        if caption.lower() == 'pros':
                                            new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + el.ul.decode_contents() + '</ul>'
                                        elif caption.lower() == 'cons':
                                            new_html += '<ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>' + el.ul.decode_contents() + '</ul>'
                                    else:
                                        new_html += str(el)
                                    new_html += '</div>'
                                new_html += '</div>'
                        elif 'mj-slides' in extra['class']:
                            image = extra.find('figure', class_='scroll__graphic')
                            if image:
                                img_src = get_img_src(image, site_json, base_url, wp_media_url)
                                captions = []
                                el = extra.find_next_sibling()
                                if el and el.get('class') and 'wp-caption-text' in el['class']:
                                    it = el.find(class_='media-caption')
                                    if it and it.get_text(strip=True):
                                        captions.append(it.decode_contents())
                                    it = el.find(class_='media-credit')
                                    if it and it.get_text(strip=True):
                                        captions.append(it.decode_contents())
                                    el.decompose()
                                desc = ''
                                for it in extra.find_all(class_='slide'):
                                    if 'invisible' not in it['class']:
                                        desc += '<p style="width:80%; margin-left:auto; margin-right:auto; text-align:center; font-weight:bold;">' + it.get_text() + '</p>'
                                new_html = utils.add_image(img_src, ' | '.join(captions), desc=desc)
                        elif 'affiliate__item' in extra['class']:
                            # https://www.wineenthusiast.com/ratings/best-hefeweizen-beer/
                            new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em;"><div style="flex:1; min-width:256px;">'
                            el = extra.find(class_='affiliate__img')
                            if el:
                                if el.a:
                                    new_html += '<a href="' + el.a['href'] + '">'
                                img_src = get_img_src(el, site_json, base_url, wp_media_url)
                                new_html += '<img src="' + img_src + '" style="width:100%;"/>'
                                if el.a:
                                    new_html += '</a>'
                            new_html += '</div><div style="flex:1; min-width:256px;">'
                            el = extra.find(class_='affiliate__name')
                            if el:
                                new_html += '<div style="font-size:1.1em; font-weight:bold;"><a href="' + el['href'] + '">' + el.get_text() + '</a></div>'
                            el = extra.find(class_='affiliate__desc')
                            if el:
                                new_html += el.decode_contents()
                            new_html += '</div></div>'
                            el = extra.find(class_='affiliate__button')
                            if el:
                                new_html += utils.add_button(el['href'], el.get_text())
                        elif 'wp-block-price-comparison' in extra['class']:
                            for el in extra.find_all('a', class_='price-comparison__view-button'):
                                caption = ''
                                if el.get('data-vars-product-vendor'):
                                    caption += 'View at ' + el['data-vars-product-vendor']
                                if el.get('data-vars-product-price'):
                                    caption += ' ' + el['data-vars-product-price']
                                new_html += utils.add_button(el['data-vars-outbound-link'], caption)
                        elif 'su-row' in extra['class']:
                            new_html += '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:1em 0;">'
                            for el in extra.select('.su-column > .su-column-inner'):
                                new_html += '<div style="flex:1; min-width:240px;">' + el.decode_contents() + '</div>'
                            new_html += '</div>'
                        elif 'su-spoiler' in extra['class']:
                            for el in extra.find_all(class_='su-spoiler-icon'):
                                el.decompose()
                            new_html = '<details>'
                            el = extra.find(class_='su-spoiler-title')
                            if el:
                                new_html += '<summary>' + el.decode_contents() + '</summary>'
                            el = extra.find(class_='su-spoiler-content')
                            if el:
                                new_html += el.decode_contents()
                            new_html += '</details>'
                        elif 'pros-cons' in extra['class'] and 'block-two-column-boxes' in extra['class']:
                            # https://www.the-ambient.com/reviews/reolink-duo-3-wifi-review/
                            for el in extra.find_all('i'):
                                el.decompose()
                            new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em; margin-top:1em;">'
                            for el in extra.find_all(class_='col'):
                                new_html += '<div style="flex:1; min-width:256px;">'
                                it = el.find(class_='col-header')
                                if it:
                                    caption = it.get_text(strip=True)
                                    new_html += '<div style="font-weight:bold;'
                                    if 'pro' in caption.lower():
                                        new_html += ' color:ForestGreen;'
                                    elif 'con' in caption.lower():
                                        new_html += ' color:Maroon;'
                                    new_html += '">' + caption + '</div>'
                                else:
                                    caption = ''
                                it = el.select('div.col-content > ul')
                                if it:
                                    if 'pro' in caption.lower():
                                        new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + it[0].decode_contents() + '</ul>'
                                    elif 'con' in caption.lower():
                                        new_html += '<ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>' + it[0].decode_contents() + '</ul>'
                                    else:
                                        new_html += '<ul>' + it[0].ul.decode_contents() + '</ul>'
                                new_html += '</div>'
                            new_html += '</div>'
                        elif 'pros-and-cons' in extra['class']:
                            # https://spy.com/articles/grooming/hair/nutrafol-for-men-review-1202925779/
                            new_html = '<hr style="margin:2em 0;"><div style="display:flex; flex-wrap:wrap; gap:1em;">'
                            for el in extra.find_all(class_='pros-and-cons__inner'):
                                new_html += '<div style="flex:1; min-width:256px;">'
                                if el.h2:
                                    new_html += '<div style="font-weight:bold;">' + el.h2.get_text(strip=True) + '</div>'
                                if el.ul:
                                    if 'is-style-pros' in el.ul['class']:
                                        new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + el.ul.decode_contents() + '</ul>'
                                    elif 'is-style-cons' in el.ul['class']:
                                        new_html += '<ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>' + el.ul.decode_contents() + '</ul>'
                                    else:
                                        new_html += '<ul>' + el.ul.decode_contents() + '</ul>'
                                new_html += '</div>'
                            new_html += '</div>'
                        elif 'article-pros-cons' in extra['class']:
                            new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em; border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:1em; margin:1em 0;">'
                            for el in extra.find_all(class_='pros-cons-container'):
                                new_html += '<div style="flex:1; min-width:256px;"><div style="font-weight:bold;">' + el.p.get_text(strip=True) + '</div>'
                                if 'pros' in el.p.get_text().lower():
                                    new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + el.ul.decode_contents() + '</ul>'
                                else:
                                    new_html += '<ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>' + el.ul.decode_contents() + '</ul>'
                                new_html += '</div>'
                            new_html += '</div>'
                        elif 'c-review-details' in extra['class']:
                            new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:0 1em 1em 1em; margin:1em 0;">'
                            el = extra.find(class_='score')
                            if el:
                                n = el.get_text(strip=True)
                                new_html += utils.add_score_gauge(int(n), n)
                            new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                            el = extra.select('.c-review-details__opinions-good > .c-review-details__opinions-info')
                            if el:
                                if el[0].h3:
                                    caption = el[0].h3.get_text(strip=True).upper()
                                else:
                                    caption = 'THE GOOD'
                                if el[0].ul:
                                    new_html += '<div style="margin:1em 0; flex:1; min-width:256px;"><div style="font-weight:bold;">' + caption + '</div><ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + el[0].ul.decode_contents() + '</ul></div>'
                            el = extra.select('.c-review-details__opinions-bad > .c-review-details__opinions-info')
                            if el:
                                if el[0].h3:
                                    caption = el[0].h3.get_text(strip=True).upper()
                                else:
                                    caption = 'THE BAD'
                                if el[0].ul:
                                    new_html += '<div style="margin:1em 0; flex:1; min-width:256px;"><div style="font-weight:bold;">' + caption + '</div><ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>' + el[0].ul.decode_contents() + '</ul></div>'
                            new_html += '</div></div>'
                        elif 'faq' in extra['class']:
                            # https://spy.com/articles/health-wellness/fitness/best-yoga-mats-1203009086/
                            el = extra.select('div.faq-title > h3')
                            if el:
                                el[0].attrs = {}
                                new_html += str(el[0])
                            for el in extra.find_all(class_='o-faq-item'):
                                new_html += '<details><summary style="margin:1em 0;"><strong>' + el.h3.get_text() + '</strong></summary><p style="margin-left:1.1em;">' + el.p.decode_contents() + '</p></details>'
                        elif 'wp-block-gearpatrol-product' in extra['class']:
                            el = extra.find(class_='wp-block-gearpatrol-product-description__text')
                            if el and el.get_text(strip=True):
                                new_html = '<div style="width:100%; min-width:320px; max-width:540px; margin:1em auto; padding:0; border:1px solid light-dark(#333, #ccc); border-radius:10px;">'
                                el = extra.find('figure', class_='wp-block-post-featured-image')
                                if el:
                                    new_html += '<img src="' + el.img['src'] + '" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" />'
                                el = extra.find(class_='wp-block-image__credit')
                                if el:
                                    new_html += '<div style="padding:0 8px;"><small>' + el.get_text(strip=True) + '</small></div>'
                                new_html += '<div style="padding:1em;">'
                                el = extra.find(class_='wp-block-post-title')
                                if el:
                                    el.attrs = {}
                                    new_html += str(el)
                                el = extra.find(class_='wp-block-gearpatrol-product-description__text')
                                if el:
                                    el.attrs = {}
                                    el.name = 'p'
                                    new_html += str(el)
                                for el in extra.find_all('li', class_='wp-block-gearpatrol-product-retailer-links__retailer'):
                                    caption = ''
                                    it = el.find(class_='wp-block-gearpatrol-product-retailer-links__savings-original-price')
                                    if it:
                                        caption += '<s>' + it.get_text(strip=True) + '</s>'
                                    it = el.find(class_='wp-block-gearpatrol-product-retailer-links__savings-discount')
                                    if it:
                                        caption += ' ' + it.get_text(strip=True)
                                    it = el.find('a', class_='wp-block-gearpatrol-product-retailer-links__retailer__link')
                                    if it:
                                        caption += ' <b>' + it.get_text(strip=True) + '</b>'
                                        new_html += utils.add_button(it['data-destinationlink'], caption.strip())
                                new_html += '</div></div>'
                            else:
                                el = extra.find('figure', class_='wp-block-post-featured-image')
                                if el:
                                    card_image = '<div style="width:100%; height:100%; background:url(\'' + el.img['src'] + '\'); background-position:center; background-size:cover; border-radius:10px 0 0 10px;"></div>'
                                card_content = ''
                                el = extra.find(class_='wp-block-post-title')
                                if el:
                                    card_content += '<div style="font-weight:bold; text-align:center;">' + el.get_text(strip=True) + '</div>'
                                for el in extra.find_all('li', class_='wp-block-gearpatrol-product-retailer-links__retailer'):
                                    caption = ''
                                    it = el.find(class_='wp-block-gearpatrol-product-retailer-links__savings-original-price')
                                    if it:
                                        caption += '<s>' + it.get_text(strip=True) + '</s>'
                                    it = el.find(class_='wp-block-gearpatrol-product-retailer-links__savings-discount')
                                    if it:
                                        caption += ' ' + it.get_text(strip=True)
                                    it = el.find('a', class_='wp-block-gearpatrol-product-retailer-links__retailer__link')
                                    if it:
                                        caption += ' <b>' + it.get_text(strip=True) + '</b>'
                                        card_content += utils.add_button(it['data-destinationlink'], caption.strip())
                                new_html += utils.format_small_card(card_image, card_content, '', content_style='padding:8px;', align_items='start') + '<div>&nbsp;</div>'
                        elif 'product-card' in extra['class']:
                            # https://spy.com/articles/health-wellness/fitness/best-yoga-mats-1203009086/
                            new_html = '<hr style="margin:2em 0;"><div style="display:flex; flex-wrap:wrap; gap:1em;">'
                            el = extra.find(class_='product-card-image-wrapper')
                            if el:
                                link = el.find(class_='c-lazy-image__link')
                                img_src = get_img_src(link, site_json, base_url, wp_media_url)
                                captions = []
                                if el.figcaption and el.figcaption.cite and el.figcaption.cite.get_text(strip=True):
                                    captions.append(el.figcaption.cite.get_text())
                                    el.figcaption.cite.decompose()
                                if el.figcaption and el.figcaption.get_text(strip=True):
                                    captions.insert(0, el.figcaption.get_text())
                                new_html += '<div style="flex:1; min-width:256px;">' + utils.add_image(img_src, ' | '.join(captions), link=link['href']) + '</div>'
                            new_html += '<div style="flex:1; min-width:256px;">'
                            el = extra.find(class_='article-kicker')
                            if el:
                                new_html += '<div style="margin-top:0.5em; margin-bottom:0.5em; text-align:center;"><span style="padding:0.4em; font-weight:bold; color:white; background-color:#153969;">' + el.get_text(strip=True) + '</span></div>'
                            el = extra.find(class_='c-title')
                            if el:
                                new_html += '<div style="font-size:1.2em; font-weight:bold; text-align:center;">' + el.get_text(strip=True) + '</div>'
                            for el in extra.select('div.buy-now-buttons > div'):
                                captions = []
                                link = el.find(class_='c-button')
                                captions.append(link.get_text(strip=True))
                                if el.p and el.p.span and el.p.span.get_text(strip=True):
                                    captions.append(el.p.span.get_text(strip=True))
                                new_html += utils.add_button(link['href'], ' '.join(captions))
                            new_html += '</div></div>'
                            el = extra.find(class_='c-dek')
                            if el:
                                el.attrs = {}
                                new_html += str(el)
                        elif 'multiple-products' in extra['class']:
                            # https://spy.com/articles/health-wellness/fitness/best-yoga-mats-1203009086/
                            el = extra.select('div.faq-title > h3')
                            if el:
                                el[0].attrs = {}
                                new_html += str(el[0])
                            for el in extra.find_all(class_='o-multiple-products-item'):
                                link = el.find('a', class_='c-lazy-image__link')
                                img_src = get_img_src(link, site_json, base_url, wp_media_url, 300)
                                card_image = '<a href="' + link['href'] + '" target="_blank"><div style="width:100%; height:100%; background:url(\'' + img_src + '\'); background-position:center; background-size:cover; border-radius:10px 0 0 10px;"></div></a>'
                                card_content = ''
                                if el.find(class_='article-kicker'):
                                    card_content += '<div style="margin-top:0.5em; margin-bottom:0.5em; text-align:center; font-size:0.8em;"><span style="padding:0.4em; font-weight:bold; color:white; background-color:#153969;">' + el.find(class_='article-kicker').get_text(strip=True) + '</span></div>'
                                card_content += '<div style="font-weight:bold; text-align:center;">' + el.find(class_='c-title').get_text(strip=True) + '</div>'
                                link = el.find('a', class_='c-button')
                                card_content += utils.add_button(link['href'], link.get_text(strip=True))
                                new_html += utils.format_small_card(card_image, card_content, '', content_style='padding:8px;', align_items='start') + '<div>&nbsp;</div>'
                        elif 'qabox-outer' in extra['class']:
                            # https://shinesparkers.net/interviews/jacobo-luengo/
                            el = extra.select('div.qabox-header > div.qabox-q > div.qabox-prompt')
                            if el:
                                new_html += '<div><strong>' + el[0].decode_contents() + '</strong></div>'
                            el = extra.select('div.qabox-header > div.qabox-q > div.qabox-text')
                            if el:
                                new_html += '<div style="margin-left:2em;">'
                                if el[0].p:
                                    new_html += el[0].decode_contents()
                                else:
                                    new_html += '<p>' + el[0].decode_contents() + '</p>'
                                new_html += '</div>'
                            el = extra.select('div.qabox-body > div.qabox-q > div.qabox-prompt')
                            if el:
                                new_html += '<div><strong>' + el[0].decode_contents() + '</strong></div>'
                            el = extra.select('div.qabox-body > div.qabox-q > div.qabox-text')
                            if el:
                                new_html += '<div style="margin-left:2em;">'
                                if el[0].p:
                                    new_html += el[0].decode_contents()
                                else:
                                    new_html += '<p>' + el[0].decode_contents() + '</p>'
                                new_html += '</div>'
                        elif 'article-boxout' in extra['class']:
                            new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:1em; margin:1em 0;">'
                            el = extra.find(class_='article-boxout__headline')
                            if el:
                                new_html += '<h3 style="margin-top:0;">' + el.get_text() + '</h3>'
                            new_html += '<div style="column-count:2;">'
                            el = extra.find(class_='article-boxout__content-img')
                            if el:
                                if el.img:
                                    new_html += '<img src="' + el.img['src'] + '" style="width:100%;">'
                                el.decompose()
                            el = extra.find(class_='article__content--intro')
                            if el:
                                new_html += '<p style="font-weight:bold;">' + el.decode_contents() + '</p>'
                                el.decompose()
                            el = extra.find(class_='article-boxout__content')
                            if el:
                                if el.div:
                                    el.div.unwrap()
                                new_html += el.decode_contents()
                            new_html += '</div></div>'
                        elif 'should-you-columns' in extra['class']:
                            new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em; margin-top:1em;">'
                            for el in extra.find_all(class_='should-you-column'):
                                new_html += '<div style="flex:1; min-width:256px;">'
                                new_html += '<div style=\'display:grid; grid-template-areas:"icon header" "content content"; grid-template-columns: min-content 1fr; grid-template-rows:auto 1fr; border:1px solid light-dark(#333,#ccc); border-radius:10px;\'>'
                                it = el.find(class_='should-you-heading')
                                if it:
                                    new_html += '<div style="grid-area:icon; font-size:3em; background-color:light-dark(#333,#ccc); border-radius:10px 0 0 0;">'
                                    if it.find(class_='fa-thumbs-up'):
                                        new_html += '👍'
                                    elif it.find(class_='fa-thumbs-down'):
                                        new_html += '👎'
                                    new_html += '</div><div style="grid-area:header; padding:8px; font-weight:bold; color:color-mix(in srgb, CanvasText, Canvas 85%); background-color:light-dark(#333,#ccc); border-radius:0 10px 0 0;">' + it.get_text() + '</div>'
                                it = el.find(class_='should-you-bottom')
                                if it:
                                    new_html += '<div style="grid-area:content; padding:0 8px;">' + it.p.decode_contents() + '</div>'
                                new_html += '</div></div>'
                            new_html += '</div>'
                        elif 'gb-button' in extra['class']:
                            new_html = utils.add_button(extra['href'], extra.string)
                        elif 'nascompares-review-box' in extra['class']:
                            for el in extra.find_all('br'):
                                el.replace_with('\n')
                            new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:0 1em;">'
                            el = extra.find('span', string=re.compile(r'^[\d\.]+$'))
                            if el:
                                n = int(el.string.replace('.', ''))
                                new_html += utils.add_score_gauge(n, el.string, '0.5em auto')
                            el = extra.select('div > div:-soup-contains("PERFORMANCE")')
                            if el:
                                for it in el[0].get_text(strip=True).split('\n'):
                                    m = re.search(r'(.+) - (\d+)/(\d+)', it)
                                    if m:
                                        new_html += utils.add_bar(m.group(1), int(m.group(2)), int(m.group(3)), False)
                            new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                            el = extra.select('div:-soup-contains(\"PROS\") + div')
                            if el:
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px;"><div style="font-weight:bold;">PROS</div><ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>'
                                for it in el[0].get_text(strip=True).split('\n'):
                                    new_html += '<li>' + it.replace('👍🏻', '').strip() + '</li>'
                                new_html += '</ul></div>'
                            el = extra.select('div:-soup-contains(\"CONS\") + div')
                            if el:
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px;"><div style="font-weight:bold;">PROS</div><ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>'
                                for it in el[0].get_text(strip=True).split('\n'):
                                    new_html += '<li>' + it.replace('👎🏻', '').strip() + '</li>'
                                new_html += '</ul></div>'
                            new_html += '</div></div>'
                        elif 'buying-guide' in extra['class']:
                            el = extra.find(class_='header-image')
                            if el:
                                new_html += utils.add_image(get_img_src(el, site_json, '', ''))
                            el = extra.select('.heading-text > h2')
                            if el:
                                new_html += '<h2 style="margin-bottom:0;">' + el[0].get_text() + '</h2>'
                            el = extra.select('.heading-text > p')
                            if el:
                                new_html += '<p style="margin-top:0;">' + el[0].get_text() + '</p>'
                            el = extra.select('.heading-text > .rating-bg:has(> img)')
                            if el:
                                m = re.search(r'/reviews/(\d+)\.svg', el[0].img['src'])
                                if m:
                                    new_html += utils.add_score_gauge(10 * int(m.group(1)), m.group(1), margin="0.5em auto")
                            el = extra.select('.deals > .subheading')
                            if el:
                                new_html += '<p><strong>' + el[0].get_text() + '</strong></p>'
                            for el in extra.select('.deals > .buttons > .starwidget'):
                                if el.get('data-geo') and 'US' in el['data-geo'].split(',') and el.get('data-afflink'):
                                    if el.get('data-affctatext'):
                                        caption = el['data-affctatext']
                                    else:
                                        caption = ''
                                        if el.get('data-affprice'):
                                            caption += el['data-affprice'] + ' '
                                        else:
                                            caption += 'Check prices '
                                        if el.get('data-affmerchant'):
                                            caption += 'at ' + el['data-affmerchant']
                                    new_html += utils.add_button(el['data-afflink'], caption)
                            el = extra.select('.spec-list > .heading')
                            if el:
                                new_html += '<p><strong>' + el[0].get_text() + '</strong></p>'
                            el = extra.select('.spec-list table')
                            if el:
                                new_html += str(el[0])
                            if extra.find(class_='reasons'):
                                new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em; margin-top:1em;"><div style="flex:1; min-width:256px;">'
                                el = extra.select('.reasons > .to-buy > span')
                                if el:
                                    new_html += '<div style="font-weight:bold;">' + el[0].get_text(strip=True) + '</div>'
                                else:
                                    new_html += '<div style="font-weight:bold;">Pros</div>'
                                el = extra.select('.reasons > .to-buy > ul')
                                if el:
                                    new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + el[0].decode_contents() + '</ul>'
                                new_html += '</div><div style="flex:1; min-width:256px;">'
                                el = extra.select('.reasons > .to-avoid > span')
                                if el:
                                    new_html += '<div style="font-weight:bold;">' + el[0].get_text(strip=True) + '</div>'
                                else:
                                    new_html += '<div style="font-weight:bold;">Cons</div>'
                                el = extra.select('.reasons > .to-avoid > ul')
                                if el:
                                    new_html += '<ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>' + el[0].decode_contents() + '</ul>'
                                new_html += '</div></div>'
                            el = extra.find(class_='guide-content')
                            if el:
                                new_html += el.decode_contents()
                        elif 'starwidget' in extra['class']:
                            if extra.get('data-geo') and 'US' in extra['data-geo'].split(','):
                                new_html += '<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:1em; margin-top:1em;">'
                                if extra.get('data-logo'):
                                    new_html += '<div style="flex:1; min-width:160px;"><img src="' + extra['data-logo'] + '" style="width:100%;"></div>'
                                new_html += '<div style="flex:2; min-width:240px;">'
                                if extra.get('data-custom-content'):
                                    new_html += html.unescape(extra['data-custom-content']) + '</div></div>'
                                if extra.get('data-afflink'):
                                    if extra.get('data-affctatext'):
                                        caption = extra['data-affctatext']
                                    else:
                                        caption = ''
                                        if extra.get('data-affprice'):
                                            caption += extra['data-affprice'] + ' '
                                        else:
                                            caption += 'See price '
                                        if extra.get('data-affmerchant'):
                                            caption += 'at ' + extra['data-affmerchant']
                                    new_html += utils.add_button(extra['data-afflink'], caption)
                                if not extra.get('data-custom-content'):
                                    new_html += '</div></div>'
                            else:
                                extra.decompose()
                        elif 'device-comparision' in extra['class']:
                            new_html = '<table><tr>'
                            for el in extra.select('.view-desktop > .device-list > div'):
                                new_html += '<th>' 
                                it = el.find(class_='device-thumb')
                                if it:
                                    m = re.search(r'background-image:\s?url\(([^\)]+)', it['style'])
                                    if m:
                                        new_html += '<img src="' + m.group(1) + '" style="width:100%; max-height:160px; object-fit:contain;">'
                                new_html += el.get_text() + '</th>'
                            new_html += '</tr>'
                            for el in extra.select('.view-desktop > .spec-list > .row'):
                                new_html += '<tr>'
                                it = el.find(class_='spec-list-name')
                                if it:
                                    new_html += '<td><strong>' + it.get_text() + '</strong></td>'
                                for it in el.find_all(class_='specs'):
                                    new_html += '<td>' + it.get_text() + '</td>'
                                new_html += '</tr>'
                            new_html += '</table>'
                        elif 'perf_test' in extra['class']:
                            el = extra.find(class_='perf_desc')
                            if el:
                                new_html += '<h3>' + el.get_text() + '</h3>'
                            for el in extra.find_all(class_='pref-row'):
                                it = el.find(class_='perf-meter')
                                if it:
                                    caption = it.get_text(strip=True)
                                else:
                                    caption = ''
                                it = el.find(class_='perf-num')
                                if it:
                                    n = it.get_text(strip=True)
                                else:
                                    n = ''
                                it = el.find(class_='perf-val')
                                if it:
                                    val = it.get_text(strip=True)
                                else:
                                    val = ''
                                it = el.find(class_='pref_meterbar')
                                if it and it.get('style'):
                                    m = re.search(r'width:\s?(\d+)', it['style'])
                                    if m:
                                        if el.find(class_='thisphone'):
                                            new_html += utils.add_bar(caption, int(m.group(1)), 100, False, sublabel=val, display_value=n, bar_color='SteelBlue')
                                        else:
                                            new_html += utils.add_bar(caption, int(m.group(1)), 100, False, sublabel=val, display_value=n, bar_color='LightSteelBlue')
                        elif 'bootstrap-yop' in extra['class']:
                            new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb; padding:0 1em 1em 1em;">'
                            el = extra.find(class_='basic-message')
                            if el:
                                new_html += '<p><em>' + el.get_text() + '</em></p>'
                            el = extra.find(class_='basic-question-title')
                            if el:
                                new_html += '<p><strong>' + el.get_text() + '</strong></p>'
                            n = 0
                            for el in extra.find_all('li', class_='basic-answer'):
                                n += int(el['data-vn'])
                            for el in extra.find_all('li', class_='basic-answer'):
                                it = el.find(class_='basic-text')
                                new_html += utils.add_bar(it.get_text(), int(el['data-vn']), n)
                            new_html += '</div>'
                        elif 'lyte-wrapper' in extra['class']:
                            el = extra.find('meta', attrs={"itemprop": "embedURL"})
                            if el:
                                new_html += utils.add_embed(el['content'])
                        elif 'ig-postimg-gallery' in extra['class']:
                            gallery_images = []
                            for el in extra.contents:
                                if el.name == None and isinstance(el, str):
                                    if el.strip():
                                        new_html += '<p>' + el.strip() + '</p>'
                                elif el.name == 'a' or el.name == 'img':
                                    if el.name == 'a':
                                        link = el['href']
                                        img_src = el.img['src']
                                    else:
                                        link = 'https://postimg.cc/' + el['src'].split('/')[3]
                                        img_src = el['src']
                                    postimg_html = utils.get_url_html(link)
                                    if postimg_html:
                                        postimg_soup = BeautifulSoup(postimg_html, 'lxml')
                                        it = postimg_soup.find('img', id='main-image')
                                        if it:
                                            img_src = it['src']
                                        else:
                                            it = postimg_soup.find('meta', attrs={"property": "og:image"})
                                            if it:
                                                img_src = it['content']
                                    gallery_images.append({"src": img_src, "caption": "", "thumb": img_src, "link": link})
                                elif el.name == 'br':
                                    if len(gallery_images) == 0:
                                        continue
                                    elif len(gallery_images) == 1:
                                        new_html += utils.add_image(gallery_images[0]['thumb'], link=gallery_images[0]['src'], object_fit='cover')
                                    else:
                                        gallery_html = ''
                                        n = len(gallery_images)
                                        for i, image in enumerate(gallery_images):
                                            if i == 0:
                                                if n % 2 == 1:
                                                    # start with full width image if odd number of images
                                                    gallery_html += utils.add_image(image['thumb'], image['caption'], link=image['link'], object_fit='cover')
                                                else:
                                                    gallery_html += '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:1em 0;"><div style="flex:1; min-width:360px;">' + utils.add_image(image['thumb'], image['caption'], link=image['link']) + '</div>'
                                            elif i == 1:
                                                if n % 2 == 1:
                                                    gallery_html += '<div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; margin:1em 0;">'
                                                gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(image['thumb'], image['caption'], link=image['link'], object_fit='cover') + '</div>'
                                            else:
                                                gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(image['thumb'], image['caption'], link=image['link'], object_fit='cover') + '</div>'
                                            del image['link']
                                        gallery_html += '</div>'
                                        if n > 4:
                                            gallery_url = config.server + '/gallery?images=' + quote_plus(json.dumps(gallery_images))
                                            new_html += '<h3><a href="' + gallery_url + '" target="_blank">View photo gallery</a></h3>' + gallery_html
                                        else:
                                            new_html += gallery_html
                                    gallery_images = []
                                else:
                                    print(el)
                        elif 'fwp-stock-chart-container' in extra['class']:
                            # https://247wallst.com/investing/2025/10/20/is-starbucks-ai-push-proof-were-in-an-ai-bubble/
                            caption = '<a href="https://finance.yahoo.com/quote/{0}/" target="_blank">{0}</a>'.format(extra['data-symbol'])
                            new_html = utils.add_image(config.server + '/stock_chart?symbol=' + extra['data-symbol'], caption)
                        elif '_3d-flip-book' in extra['class']:
                            el = soup.find('script', string=re.compile(r'FB3D_CLIENT_DATA'))
                            if el:
                                i = el.string.find("'")
                                j = el.string.rfind("'") + 1
                                fb3d_data = json.loads(base64.b64decode(el.string[i:j]).decode('utf-8'))
                                new_html = '<div style="display:flex; align-items:center; margin:1em 0;"><span style="font-size:3em;">📄</span><a href="' + fb3d_data['posts'][extra['data-id']]['data']['guid'] + '" target="_blank"><strong>Download</strong></a></div>'
                        elif 'cpp-crypto-chart' in extra['class']:
                            new_html = utils.add_image(config.server + '/stock_chart?symbol=' + extra['data-coin-symbol'] + '-usd')
                        elif 'alternative-links' in extra['class']:
                            if 'alternative-links-minimal' in extra['class']:
                                el = extra.find(class_='link-product-name')
                                if el:
                                    new_html += '<div style="text-align:center; font-weight:bold;">' + el.get_text(strip=True) + '</div>'
                                for el in extra.select('.link-price > a.btn'):
                                    new_html += utils.add_button(el['href'], el.get_text(strip=True))
                            else:
                                for el in extra.find_all(class_='alternative-links-inner'):
                                    it = el.select('.alternative-links-thumb > img')
                                    if it:
                                        card_image = '<div style="width:100%; height:100%; background:url(\'' + it[0]['src'] + '\'); background-position:center; background-size:cover; border-radius:10px 0 0 10px;"></div>'
                                    else:
                                        card_image = ''
                                    card_content = ''
                                    it = el.find('header')
                                    if it:
                                        card_content += '<div style="font-weight:bold; text-align:center;">' + it.get_text(strip=True) + '</div>'
                                    for it in el.select('.link-price > a.btn'):
                                        card_content += utils.add_button(it['href'], it.get_text(strip=True))
                                    new_html += utils.format_small_card(card_image, card_content, '', content_style='padding:8px;', align_items='start') + '<div>&nbsp;</div>'
                                if not new_html:
                                    extra.decompose()
                                    continue
                        elif 'wp-block-columns' in extra['class'] and extra.find(class_='wp-block-jetpack-rating-star'):
                            new_html += '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; margin:1em 0; padding:1em;">'
                            new_html += '<div style="display:flex; flex-wrap:wrap; gap:8px;">'
                            el = extra.find(class_='wp-block-image')
                            if el:
                                img_src = get_img_src(el, site_json, '', '')
                                new_html += '<div style="flex:1; min-width:240px;"><img src="' + img_src + '" style="width:100%;"/></div>'
                            el = extra.find('p')
                            if el:
                                new_html += '<div style="flex:1; min-width:240px;">' + str(el) + '</div>'
                            new_html += '</div>'
                            el = extra.find(class_='screen-reader-text', attrs={"itemprop": "ratingValue"})
                            if el:
                                new_html += utils.add_stars(float(el['content']))
                            new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                            el = extra.select('h5:-soup-contains("Pros:") + ul')
                            if el:
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px; color:ForestGreen;"><div style="font-weight:bold;">Pros:</div><ul style=\'list-style-type:"✓&nbsp;"\'>' + el[0].decode_contents() + '</ul></div>'
                            el = extra.select('h5:-soup-contains("Cons:") + ul')
                            if el:
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px; color:Maroon;"><div style="font-weight:bold;">Cons:</div><ul style=\'list-style-type:"✗&nbsp;"\'>' + el[0].decode_contents() + '</ul></div>'
                            new_html += '</div></div>'
                    if new_html:
                        new_el = BeautifulSoup(new_html, 'html.parser')
                        extra.replace_with(new_el)

    # for el in soup.find_all(recursive=False):
    for el in soup.contents:
        # print(type(el))
        new_html = ''
        if isinstance(el, NavigableString):
            if el.strip() and 'markdown_text' in site_json and site_json['markdown_text'] == True:
                new_html = markdown(str(el))
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            continue

        if el.name == 'iframe':
            if el.get('data-src'):
                new_html = utils.add_embed(el['data-src'])
            elif el.get('src'):
                new_html = utils.add_embed(el['src'])
            elif el.get('srcdoc'):
                it = BeautifulSoup(html.unescape(el['srcdoc']), 'html.parser')
                if it.a and it.a.get('href'):
                    new_html = utils.add_embed(it.a['href'])
            if not new_html:
                logger.warning('unhandled iframe ' + str(el))
        elif el.name == 'table':
            if 'format_table' not in args or args['format_table'] == True:
                utils.format_table(el)
            continue
        elif el.name == 'blockquote':
            if not el.get('class'):
                el.attrs = {}
                el['style'] = config.blockquote_style
                continue
            elif 'instagram-media' in el['class']:
                new_html += utils.add_embed(el['data-instgrm-permalink'])
            elif 'twitter-tweet' in el['class']:
                links = el.find_all('a')
                if links:
                    new_html = utils.add_embed(links[-1]['href'])
            elif 'tiktok-embed' in el['class']:
                new_html += utils.add_embed(el['cite'])
            elif 'bluesky-embed' in el['class']:
                new_html += utils.add_embed(el['data-bluesky-uri'].replace('at://', 'https://bsky.app/profile/').replace('app.bsky.feed.post', 'post'))
            elif 'reddit-embed-bq' in el['class']:
                links = el.find_all('a')
                if links:
                    new_html = utils.add_embed(links[0]['href'])
            elif 'pullquote' in el['class'] or el.get('data-shortcode-type') == 'pullquote':
                it = el.find('cite')
                if it:
                    cite = it.decode_contents()
                    it.decompose()
                else:
                    cite = ''
                new_html += utils.add_pullquote(el.decode_contents(), cite)
            elif 'wp-block-quote' in el['class']:
                if 'blockquote_default' in site_json:
                    if site_json['blockquote_default'] == 'pullquote':
                        it = el.find('cite')
                        if it:
                            cite = re.sub(r'^—\s*', '', it.decode_contents().strip())
                            it.decompose()
                        else:
                            cite = ''
                        new_html += utils.add_pullquote(el.decode_contents(), cite)
                    elif site_json['blockquote_default'] == 'blockquote':
                        el.attrs = {}
                        el['style'] = config.blockquote_style
                elif el.cite:
                    it = el.find('cite')
                    cite = re.sub(r'^—\s*', '', it.decode_contents().strip())
                    it.decompose()
                    new_html += utils.add_pullquote(el.decode_contents(), cite)
                else:
                    el.attrs = {}
                    el['style'] = config.blockquote_style
                    continue
            elif el.cite:
                cite = el.cite.decode_contents()
                el.cite.decompose()
                new_html += utils.add_pullquote(el.decode_contents(), cite)
            else:
                logger.warning('unhandled blockquote class {} in {}'.format(el['class'], url))
        elif el.name == 'pre':
            el.attrs = {}
            el['style'] = 'padding:0.5em; white-space:pre; overflow-x:scroll; background-color:light-dark(#ccc,#333);'
            continue
        elif el.name == 'video':
            it = el.find('source')
            if it:
                new_html = utils.add_video(it['src'], it['type'], el.get('poster'), el.get('title'), use_videojs=True)
            elif el.get('src'):
                new_html = utils.add_video(el['src'], 'video/mp4', '', '', use_videojs=True)
        elif el.name == 'video-js' and el.get('data-video-id'):
            new_html = utils.add_embed('https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(el['data-account'], el['data-player'], el['data-video-id']))
        elif el.name == 'script' and el.get('src') and 'jwplayer.com' in el['src']:
            new_html = utils.add_embed(el['src'])
        elif el.name == 'audio':
            it = el.find('source')
            if it:
                new_html = utils.add_audio_v2(it['src'], '', 'Listen', '', '', '', '', '', it['type'], show_poster=False, border=False, margin='')
        elif el.name == 'div' and el.get('data-react-component') and el['data-react-component'] == 'VideoPlaylist' and el.get('data-props'):
            data_props = json.loads(el['data-props'])
            if data_props['videos'][0].get('isLivestream') and data_props['videos'][0]['isLivestream'] == '1':
                continue
            elif data_props['videos'][0].get('mp4Url'):
                new_html += utils.add_video(data_props['videos'][0]['mp4Url'], 'video/mp4', data_props['videos'][0]['poster'], data_props['videos'][0]['title'], use_videojs=True)
            elif data_props['videos'][0].get('m3u8Url'):
                new_html += utils.add_video(data_props['videos'][0]['m3u8Url'], 'video/mp4', data_props['videos'][0]['poster'], data_props['videos'][0]['title'])
            else:
                new_html = add_nbc_video(data_props['videos'][0]['videoContentId'], wpjson_path)
        elif el.get('class'):
            if 'wp-block-image' in el['class']:
                img_src = get_img_src(el, site_json, base_url, wp_media_url)
                if img_src:
                    captions = []
                    it = el.find('cite')
                    if it:
                        if it.get_text(strip=True):
                            if it.p:
                                captions.append(it.p.decode_contents())
                            else:
                                captions.append(it.decode_contents())
                        it.decompose()
                    it = el.find('figcaption')
                    if it and it.get_text(strip=True):
                        caption = it.decode_contents().strip()
                        caption = re.sub(r'<br/?>$', '', caption)
                        caption = re.sub(r'^<em>(.*)</em>$', r'\1', caption)
                        captions.insert(0, caption)
                    it = el.select('a:has(> img)')
                    if it:
                        link = it[0]['href']
                    else:
                        link = ''
                    new_html = utils.add_image(img_src, ' | '.join(captions), link=link)
            elif 'wp-caption' in el['class']:
                img_src = get_img_src(el, site_json, base_url, wp_media_url)
                if img_src:
                    captions = []
                    it = el.find('cite')
                    if it:
                        if it.get_text(strip=True):
                            captions.append(it.decode_contents())
                        it.decompose()
                    it = el.find(class_='wp-caption-text')
                    if it and it.get_text(strip=True):
                        captions.insert(0, re.sub(r'<br/?>$', '', it.decode_contents()).strip())
                    else:
                        it = el.find('figcaption')
                        if it and it.get_text(strip=True):
                            captions.insert(0, re.sub(r'<br/?>$', '', it.decode_contents()).strip())
                    it = el.select('a:has(> img)')
                    if it:
                        link = it[0]['href']
                    else:
                        link = ''
                    new_html = utils.add_image(img_src, ' | '.join(captions), link=link)
            elif 'wp-block-gallery' in el['class'] and el.name == 'figure':
                tag = {
                    "attrs": {
                        "class": "wp-block-gallery"
                    },
                    "image": {
                        "attrs": {
                            "class": "wp-block-image"
                        },
                        "caption": {
                            "tag": "figcaption"
                        },
                        "tag": "figure"
                    },
                    "tag": "figure"
                }
                new_html += add_gallery(el, tag, site_json, base_url, wp_media_url)
            elif 'wp-block-embed' in el['class']:
                if 'wp-block-embed-youtube' in el['class']:
                    it = el.find('iframe')
                    if it:
                        if it.get('data-src'):
                            new_html = utils.add_embed(it['data-src'])
                        else:
                            new_html = utils.add_embed(it['src'])
                    elif el.find(class_='__youtube_prefs__', attrs={"data-facadesrc": True}):
                        it = el.find(class_='__youtube_prefs__')
                        new_html = utils.add_embed(it['data-facadesrc'])
                    elif el.find(class_='lyte-wrapper') and el.find('meta', attrs={"itemprop": "embedURL"}):
                        # https://hometheaterextra.com/formovie-theater-ust-4k-projector-review/
                        it = el.find('meta', attrs={"itemprop": "embedURL"})
                        new_html = utils.add_embed(it['content'])
                    elif el.find(attrs={"data-videoid": True}):
                        # https://nerdist.com/article/teenage-mutant-ninja-turtles-original-film-theaters-35th-anniversary/
                        it = el.find(attrs={"data-videoid": True})
                        new_html = utils.add_embed('https://www.youtube.com/watch?v=' + it['data-videoid'])
                    elif el.find(attrs={"videoid": True}):
                        it = el.find(attrs={"videoid": True})
                        new_html = utils.add_embed('https://www.youtube.com/watch?v=' + it['videoid'])
                    elif el.find(attrs={"data-plyr-embed-id": True}):
                        it = el.find(attrs={"data-plyr-embed-id": True})
                        new_html = utils.add_embed('https://www.youtube.com/watch?v=' + it['data-plyr-embed-id'])
                    elif el.find('a', href=re.compile(r'youtube\.com/watch')):
                        it = el.find('a', href=re.compile(r'youtube\.com/watch'))
                        new_html = utils.add_embed(it['href'])
                elif 'wp-block-embed-twitter' in el['class']:
                    link = el.find_all('a')
                    if link:
                        new_html = utils.add_embed(link[-1]['href'])
                    else:
                        it = el.find(class_='wp-block-embed__wrapper')
                        if it:
                            link = it.get_text(strip=True)
                            if link.startswith('https://twitter.com') or link.startswith('https://x.com'):
                                new_html = utils.add_embed(link)
                elif 'wp-block-embed-instagram' in el['class']:
                    it = el.find('blockquote')
                    if it:
                        new_html = utils.add_embed(it['data-instgrm-permalink'])
                    else:
                        m = re.search(r'https://www\.instagram\.com/p/[^/]+/', str(el))
                        if m:
                            new_html = utils.add_embed(m.group(0))
                elif 'wp-block-embed-tiktok' in el['class']:
                    it = el.find('blockquote')
                    if it:
                        new_html = utils.add_embed(it['cite'])
                elif 'wp-block-embed-facebook' in el['class']:
                    links = el.find_all('a')
                    new_html = utils.add_embed(links[-1]['href'])
                elif 'wp-block-embed-bluesky-social' in el['class']:
                    it = el.find('blockquote', attrs={"data-bluesky-uri": True})
                    if it:
                        new_html = utils.add_embed(it['data-bluesky-uri'].replace('at://', 'https://bsky.app/profile/').replace('app.bsky.feed.post', 'post'))
                elif 'wp-block-embed-reddit' in el['class']:
                    it = el.select('blockquote > a')
                    if it:
                        new_html = utils.add_embed(it[0]['href'])
                elif el.find(class_='fb-post'):
                    it = el.find(class_='fb-post')
                    new_html = utils.add_embed(it['href'])
                elif el.find('video'):
                    it = el.find('source')
                    if it:
                        new_html = utils.add_video(it['src'], it['type'], '', '', use_videojs=True)
                elif el.find('iframe'):
                    it = el.find('iframe')
                    if it:
                        if it.get('data-src'):
                            new_html = utils.add_embed(it['data-src'])
                        else:
                            new_html = utils.add_embed(it['src'])
            elif ('wp-block-video' in el['class'] or 'wp-video' in el['class']) and el.video:
                it = el.find(class_='wp-element-caption')
                if it:
                    caption = it.decode_contents()
                else:
                    it = el.find('figcaption')
                    if it:
                        caption = it.decode_contents()
                    else:
                        caption = ''
                if el.video.source:
                    if not caption and el.video.get('title'):
                        caption = el.video['title']
                    new_html = utils.add_video(el.video.source['src'], el.video.source['type'], el.video.get('poster'), caption, use_videojs=True)
                elif el.video.get('src'):
                    new_html = utils.add_video(el.video['src'], 'video/mp4', el.video.get('poster'), caption, use_videojs=True)
            elif 'youtube' in el['class'] and el.get('data-embed'):
                new_html = utils.add_embed('https://www.youtube.com/watch?v=' + el['data-embed'])
            elif 'jetpack-video-wrapper' in el['class'] and el.iframe:
                new_html = utils.add_embed(el.iframe['src'])
            elif 'wp-block-jetpack-videopress' in el['class'] and el.find('iframe'):
                # https://theintercept.com/2025/07/21/israel-gaza-famine-food-aid-starvation/
                it = el.find('iframe')
                video_id = list(filter(None, urlsplit(it['src']).path.split('/')))[-1]
                video_json = utils.get_url_json('https://public-api.wordpress.com/rest/v1.1/videos/' + video_id)
                if video_json:
                    if video_json.get('description'):
                        caption = video_json['description']
                    else:
                        caption = ''
                    if video_json.get('adaptive_streaming'):
                        new_html = utils.add_video(video_json['adaptive_streaming'], 'application/x-mpegURL', video_json['poster'], caption, use_videojs=True)
                    elif '.mp4' in video_json['original']:
                        new_html = utils.add_video(video_json['original'], 'video/mp4', video_json['poster'], caption, use_videojs=True)
                    else:
                        new_html = utils.add_video(video_json['original'], 'application/x-mpegURL', video_json['poster'], caption, use_videojs=True)
            elif 'wp-block-jw-player-video' in el['class'] and el.get('data-wp-block'):
                video_json = json.loads(el['data-wp-block'])
                if video_json.get('embed_url'):
                    new_html += utils.add_embed(video_json['embed_url'])
                elif video_json.get('videoSrc'):
                    new_html += utils.add_video(video_json['videoSrc'], 'video/mp4' if '.mp4' in video_json['videoSrc'] else 'application/x-mpegURL', 'https://assets-jpcust.jwpsrv.com/thumbs/' + video_json['platform_id'] + '-720.jpg', video_json.get('video_title'), use_videojs=True)
            elif 'brightcove-video-container' in el['class'] and el.find('video'):
                it = el.find('video')
                if it.get('data-video-id'):
                    new_html = utils.add_embed('https://players.brightcove.net/' + it['data-account'] + '/' + it['data-player'] + '_default/index.html?videoId=' + it['data-video-id'])
                elif it.get('data-playlist-id'):
                    new_html = utils.add_embed('https://players.brightcove.net/' + it['data-account'] + '/' + it['data-player'] + '_default/index.html?playlistId=' + it['data-playlist-id'])
            elif 'video-player' in el['class']:
                it = el.find('video', class_='video-js')
                if it and it.get('data-opts'):
                    data_props = json.loads(html.unescape(it['data-opts']))
                    if data_props['plugins']['sources'].get('iOSRenditions'):
                        new_html += utils.add_video(data_props['plugins']['sources']['iOSRenditions'][-1]['url'], 'application/x-mpegURL', data_props['poster'], data_props['title'])
                    elif data_props['plugins']['sources'].get('renditions'):
                        new_html += utils.add_video(data_props['plugins']['sources']['renditions'][0]['url'], 'video/mp4', data_props['poster'], data_props['title'])
                if video_json:
                    if video_json.get('description'):
                        caption = video_json['description']
                    else:
                        caption = ''
                    if video_json.get('adaptive_streaming'):
                        new_html = utils.add_video(video_json['adaptive_streaming'], 'application/x-mpegURL', video_json['poster'], caption, use_videojs=True)
                    elif '.mp4' in video_json['original']:
                        new_html = utils.add_video(video_json['original'], 'video/mp4', video_json['poster'], caption, use_videojs=True)
                    else:
                        new_html = utils.add_video(video_json['original'], 'application/x-mpegURL', video_json['poster'], caption, use_videojs=True)    
            elif 'adthrive-video-player' in el['class'] and el.get('data-video-id'):
                new_html = utils.add_embed('https://content.jwplatform.com/players/' + el['data-video-id'] + '.html')
            elif 'hearstLumierePlayer' in el['class']:
                new_html = hearsttv.add_lumiere_player(el['data-player-id'])
            elif 'wp-block-audio' in el['class'] and el.audio:
                if el.audio.get('src'):
                    # new_html = utils.add_audio_v2(el.audio['src'], '', 'Listen', '', '', '', '', '', 'audio/mpeg', show_poster=False, border=False, margin='')
                    new_html += utils.format_audio_track({
                        "src": el.audio['src'],
                        "mime_type": "audio/mpeg",
                        "title": 'Listen'
                    }, full_width=False)
                else:
                    it = el.find('source')
                    if it:
                        new_html = utils.add_audio_v2(it['src'], '', 'Listen', '', '', '', '', '', it['type'], show_poster=False, border=False, margin='')
            elif 'audio-module' in el['class'] and el.find(class_='audio-module-controls-wrap', attrs={"data-audio": True}):
                # npr.org
                it = el.find(class_='audio-module-controls-wrap', attrs={"data-audio": True})
                audio_json = json.loads(it['data-audio'])
                new_html += utils.format_audio_track({
                    "src": audio_json['audioUrl'],
                    "mime_type": "audio/mpeg",
                    "title": audio_json['title'],
                    "url": audio_json['storyUrl'],
                    "artist": utils.calc_duration(audio_json['duration'], time_format=':')
                }, full_width=False)
            elif 'audioplayer-tobe' in el['class'] and el.get('data-source'):
                # northcountrypublicradio.org
                new_html += utils.format_audio_track({
                    "src": el['data-source'],
                    "mime_type": "audio/mpeg",
                    "title": el['data-videotitle'] if el.get('data-videotitle') else 'Listen'
                }, full_width=False)
            elif 'playlistitem' in el['class'] and el.name == 'a':
                # whyy.org
                m = re.search(r'[\d:]+', el.get_text(strip=True))
                new_html += utils.format_audio_track({
                    "src": el['href'],
                    "mime_type": "audio/mpeg",
                    "title": el['title'] if el.get('title') else 'Listen',
                    "artist": m.group(0) if m else ''
                }, full_width=False)
            elif 'infogram-embed' in el['class'] and el.get('data-id'):
                new_html = utils.add_embed('https://e.infogram.com/' + el['data-id'] + '?src=embed')
            elif 'flourish-embed' in el['class'] and el.get('data-src'):
                new_html = utils.add_embed('https://public.flourish.studio/' + el['data-src'])
            elif 'tableauPlaceholder' in el['class'] and el.object:
                it = el.find(attrs={"name": "static_image"})
                if it:
                    img_src = it['value']
                    it = el.find(attrs={"name": "host_url"})
                    if it:
                        link = unquote_plus(it['name'])
                        it = el.find(attrs={"name": "name"})
                        if it:
                            link += unquote_plus(it['name'])
                            new_html = utils.add_image(img_src, link=link)
            elif 'nxs-player-wrapper' in el['class']:
                new_html = add_nxs_player_video(el)
            elif 'ns-block-custom-html' in el['class']:
                it = el.find('iframe')
                if it:
                    new_html = utils.add_embed(it['src'])
                else:
                    it = el.find(id=re.compile(r'datawrapper'))
                    if it:
                        new_html = utils.add_embed('https://datawrapper.dwcdn.net/' + it['id'].split('-')[-1])
            elif 'wp-block-table' in el['class']:
                utils.format_table(el.table)
                it = el.find('figcaption')
                if it:
                    it.attrs = {}
                    it.name = 'div'
                    it['style'] = 'font-size:smaller; padding:4px 0 1em 0;'
                el.unwrap()
                continue
            elif 'wp-block-pullquote' in el['class'] or 'pullquote' in el['class'] or 'pull-quote' in el['class']:
                it = el.find('cite')
                if it:
                    cite = it.decode_contents()
                    it.decompose()
                else:
                    cite = ''
                if el.blockquote:
                    new_html = utils.add_pullquote(el.blockquote.decode_contents(), cite)
                else:
                    new_html = utils.add_pullquote(el.decode_contents(), cite)
            elif 'wp-block-buttons' in el['class'] or 'wp-block-button' in el['class']:
                for it in el.find_all('a', class_='wp-block-button__link'):
                    caption = it.get_text(strip=True)
                    if caption:
                        new_html += utils.add_button(it['href'], caption)
                    elif it.img:
                        new_html += utils.add_button(it['href'], caption, it.img['src'])
            elif ('button' in el['class'] or 'comp-button' in el['class'] or 'small-button' in el['class']) and el.name == 'a':
                new_html += utils.add_button(el['href'], el.get_text(strip=True))
            elif 'wp-block-prc-block-subtitle' in el['class']:
                new_html = '<p><em>' + el.get_text(strip=True) + '</em></p>'
            elif 'wp-block-group' in el['class'] and 'is-style-callout' in el['class']:
                # https://www.pewresearch.org/global/2025/06/11/us-image-declines-in-many-nations-amid-low-confidence-in-trump/
                el.attrs = {}
                el.name = 'details'
                el['style'] = 'margin:1em 0; padding:8px; border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb;'
                it = el.find('h4')
                if it:
                    it.attrs = {}
                    it.name = 'summary'
                    it['style'] = 'font-weight:bold;'
                continue
            elif 'wp-block-code' in el['class'] and el.name == 'pre':
                el.attrs = {}
                el['style'] = 'padding:0.5em; white-space:pre; overflow-x:scroll; background-color:#e5e7eb;'
                continue
            elif 'wp-block-syntaxhighlighter-code' in el['class'] and el.pre:
                el.pre.attrs = {}
                el.pre['style'] = 'padding:0.5em; white-space:pre; overflow-x:scroll; background-color:#e5e7eb;'
                el.unwrap()
                continue
            elif 'wp-block-spacer' in el['class']:
                el.attrs = {}
                el['style'] = 'height:1em;'
            elif 'wp-block-separator' in el['class']:
                el.attrs = {}
                el['style'] = 'margin:1em 0;'
            elif 'wp-block-file':
                link = ''
                if el.object:
                    link = el.object['data']
                    caption = el.object['aria-label']
                else:
                    it = el.find('a', class_='wp-block-file__button')
                    if it:
                        link = it['href']
                        caption = it.get_text()
                if link:
                    if not caption:
                        caption = 'Download'
                    new_html = '<div style=\'display:grid; grid-template-areas:"icon link"; grid-template-columns:auto 1fr; gap:4px; margin:1em 0; align-items:center;\'><div style="grid-area:icon; font-size:3em;"><a href="' + link + '" style="text-decoration:none;" target="_blank">🗎</a></div><div style="grid-area:link;"><a href="' + link + '" target="_blank">' + caption + '</a></div></div>'
            elif 'star-rating' in el['class']:
                # https://www.the-ambient.com/reviews/reolink-duo-3-wifi-review/
                n = len(el.select('div.full-stars > i.fa-star')) + 0.5 * len(el.select('div.full-stars > i.fa-star-half'))
                new_html += utils.add_stars(n)
            elif 'schema-faq' in el['class'] or 'wp-block-yoast-faq-block' in el['class']:
                # https://www.the-ambient.com/reviews/reolink-duo-3-wifi-review/
                for it in el.find_all(class_='schema-faq-section'):
                    q = it.find(class_='schema-faq-question')
                    a = it.find(class_='schema-faq-answer')
                    new_html += '<details><summary style="margin:1em 0;"><strong>' + q.decode_contents() + '</strong></summary><p style="margin-left:1.1em;">' + a.decode_contents() + '</p></details>'
            elif 'story-chart-wrapper' in el['class']:
                # https://wccftech.com/review/crucial-t710-gen5-2-tb-nvme-ssd-review-fastest-storage-again/
                new_html = ''
                it = el.select('header.chart-header > h5')
                if it:
                    new_html += '<h3>' + it[0].string + '</h3>'
                for i, it in enumerate(el.select('header.chart-header > div.chart-legend > div.legend-item > span')):
                    new_html += '<p><span style="background:hsl({}deg 100 50 / 1); width:5em;">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span>&nbsp;<strong>{}</strong></p>'.format(60 * i, it.string)
                for it in el.select('div.chart-data > div'):
                    new_html += '<div><strong>' + it.span.string + '</strong></div>'
                    for i, val in enumerate(it.find_all('div', attrs={"data-value": True})):
                        new_html += utils.add_bar('', int(val['data-value']), 100, bar_color='hsl({}deg 100 50 / 1)'.format(60 * i), display_value=val.string)
            elif 'wp-block-book-blurb-block-main' in el['class']:
                # https://bookriot.com/the-space-between-worlds-by-micaiah-johnson/
                new_html += '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:8px; margin:8px;">'
                it = el.find('a', class_='bookblurb__coverlink')
                if it:
                    new_html += '<div style="flex:1; min-width:160px; max-width:160px;"><a href="' + it['href'] + '"><img src="' + it.img['src'] + '" style="width:100%;"/></a></div>'
                new_html += '<div style="flex:2; min-width:320px;">'
                it = el.find('h3', class_='bookblurb__booktitle')
                if it:
                    new_html += '<div style="font-size:1.1em; font-weight:bold;">' + it.decode_contents() + '</div>'
                it = el.find(class_='bookblurb__description')
                if it:
                    new_html += it.decode_contents()
                new_html += '</div>'
            elif 'podigee-podcast-player' in el['class']:
                # https://federalnewsnetwork.com/federal-newscast/2025/07/ice-is-offering-up-to-50000-signing-bonus-for-retired-employees-to-return-to-the-job/
                it = soup.find('script', string=re.compile(r'{}'.format(el['data-configuration'])))
                if it:
                    i = it.string.find('{')
                    j = it.string.rfind('}') + 1
                    player_config = json.loads(it.string[i:j])
                    new_html = utils.add_audio_v2(player_config['episode']['media']['mp3'], player_config['episode']['coverUrl'], player_config['episode']['title'], '', '', '', '', '', small_poster=True)
            elif 'has-drop-cap' in el['class']:
                # handle below
                continue
            else:
                logger.warning('unhandled element class ' + str(el['class']))
        elif el.get('id'):
            if el['id'].startswith('rumble_'):
                video_id = el['id'].replace('rumble_', '')
                it = soup.find('script', string=re.compile(r'rumble\.com/embedJS'))
                if it:
                    m = re.search(r'src="([^"]+)', it.string)
                    rumble_js = utils.get_url_html(m.group(1) + '.' + video_id)
                    if rumble_js:
                        m = re.search(r'f\["([^"]+)"]=(\{.*?\});if\(', rumble_js)
                        if m and m.group(1) == video_id:
                            rumble_json = json.loads(m.group(2).replace(',loaded:u()', ''))
                            new_html = utils.add_video(rumble_json['u']['hls']['url'], 'application/x-mpegURL', rumble_json['i'], rumble_json['title'])
            elif el['id'].startswith('datawrapper-vis-'):
                # https://calmatters.org/health/mental-health/2025/07/mental-health-treatment-insurance-reviews/
                new_html += utils.add_embed('https://datawrapper.dwcdn.net/' + el['id'].split('-')[-1])

        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

    for el in soup.find_all(['aside', 'ins', 'link', 'meta', 'noscript', 'script', 'style']):
        el.decompose()

    if site_json and 'clear_attrs' in site_json and isinstance(site_json['clear_attrs'], bool) and site_json['clear_attrs'] == True:
        for el in soup.find_all(id=True):
            del el['id']
        for el in soup.find_all(class_=True):
            del el['class']

    for el in soup.find_all(class_=['dropcap', 'dropcaps', 'drop-cap', 'add-drop-cap', 'has-drop-cap', 'big-cap', 'big-letter', 'firstcharacter']):
        if el.name == 'p':
            el.attrs = {}
            utils.add_paragraph_dropcap(el)
        else:
            it = el.find_parent('p')
            if it:
                el.unwrap()
                it.attrs = {}
                utils.add_paragraph_dropcap(it)
    if 'first_paragraph_dropcap' in args:
        el = soup.find('p', recursive=False)
        if el:
            utils.add_paragraph_dropcap(el)
        
    for el in soup.find_all(class_=["wp-block-heading", "wp-block-list", "wp-block-separator"]):
        el.attrs = {}

    for el in soup.find_all(attrs={"data-start": True, "data-end": True}):
        del el['data-start']
        del el['data-end']

    for el in soup.find_all('span', attrs={"style": "font-weight: 400;"}):
        el.unwrap()

    for el in soup.find_all('span', attrs=False):
        el.unwrap()

    content = str(soup)

    if site_json and 'use_mathjax' in site_json and site_json['use_mathjax'] == True:
        content += '<script defer src="https://cdn.jsdelivr.net/npm/mathjax@4/tex-svg.js"></script>'
    return content


def get_feed(url, args, site_json, save_debug=False):
    if 'rss' in url or '/feed' in url:
        return rss.get_feed(url, args, site_json, save_debug, get_content)
    return None
