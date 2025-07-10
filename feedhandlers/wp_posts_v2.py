import base64, html, json, math, re
import curl_cffi
from bs4 import BeautifulSoup, Comment
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, unquote_plus, urlsplit

import config, utils
from feedhandlers import cnn, rss, wp

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


def get_img_src(el, site_json, image_netloc, width=1200, height=800):
    img_src = ''
    if el.name == 'img':
        img = el
    elif el.img:
        img = el.img
    else:
        logger.warning('unknown img in ' + str(el))
        return ''

    if img.get('data-lazy-srcset') and not img['data-lazy-srcset'].startswith('data:image/gif;base64'):
        img_src = utils.image_from_srcset(img['data-lazy-srcset'], width)

    elif img.get('data-lazy-load-srcset') and not img['data-lazy-load-srcset'].startswith('data:image/gif;base64'):
        img_src = utils.image_from_srcset(img['data-lazy-load-srcset'], width)

    elif img.get('data-srcset') and not img['data-srcset'].startswith('data:image/gif;base64'):
        img_src = utils.image_from_srcset(img['data-srcset'], width)

    elif img.get('srcset') and not img['srcset'].startswith('data:image/gif;base64'):
        img_src = utils.image_from_srcset(img['srcset'], width)

    elif img.get('class') and site_json and site_json['module'] == 'wp_posts_v2' and ('args' not in site_json or 'skip_wp_media' not in site_json['args']):
        m = re.search(r'wp-image-(\d+)', ' '.join(img['class']))
        if m:
            media_json = utils.get_url_json(site_json['wpjson_path'] + '/wp/v2/media/' + m.group(1), site_json=site_json)
            if media_json and media_json['media_type'] == 'image':
                if media_json.get('media_details') and media_json['media_details'].get('width') and media_json['media_details']['width'] <= width:
                    img_src = media_json['source_url']
                elif media_json.get('description') and media_json['description'].get('rendered') and 'srcset' in media_json['description']['rendered']:
                    el = BeautifulSoup(media_json['description']['rendered'], 'html.parser')
                    img_src = utils.image_from_srcset(el.img['srcset'], width)
                elif media_json.get('media_details') and media_json['media_details'].get('sizes'):
                    media = utils.closest_dict(list(media_json['media_details']['sizes'].values()), 'width', width)
                    img_src = media['source_url']
                else:
                    img_src = media_json['source_url']

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
    if img_src and 'image_proxy' in site_json and site_json['image_proxy'] == True:
        img_src = 'https://wsrv.nl/?url=' + quote_plus(img_src)

    return img_src


def add_wp_media(link_href, site_json, media_json=None, width=1200, caption_is_desc=False):
    if not media_json:
        if site_json.get('replace_links_path'):
            link_href = link_href.replace(site_json['replace_links_path'][0], site_json['replace_links_path'][1])
        media_json = utils.get_url_json(link_href, site_json=site_json)
        if not media_json:
            return ''
    if media_json.get('media_details') and media_json['media_details'].get('width') and media_json['media_details']['width'] <= width:
        img_src = media_json['source_url']
    elif media_json.get('description') and media_json['description'].get('rendered') and 'srcset' in media_json['description']['rendered']:
        el = BeautifulSoup(media_json['description']['rendered'], 'html.parser')
        img_src = utils.image_from_srcset(el.img['srcset'], width)
    elif media_json.get('media_details') and media_json['media_details'].get('sizes'):
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
    captions = []
    desc = ''
    if media_json.get('caption') and media_json['caption'].get('rendered'):
        if caption_is_desc:
            desc = media_json['caption']['rendered']
        else:
            captions.append(re.sub(r'^<p>|</p>$', '', media_json['caption']['rendered'].strip()))
    if media_json.get('meta') and media_json['meta'].get('credit'):
        captions.append(media_json['meta']['credit'])
    elif media_json.get('meta') and media_json['meta'].get('_image_credit'):
        captions.append(media_json['meta']['_image_credit'])
    return utils.add_image(img_src, ' | '.join(captions), link=media_json.get('link'), desc=desc)


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


def find_post_id(page_soup):
    post_id = ''
    post_url = ''
    # Find the direct wp-json link
    el = page_soup.find('link', attrs={"rel": "alternate", "type": "application/json", "href": re.compile(r'wp-json')})
    if el:
        # post_url = el['href']
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
    if not post_url:
        # Sometimes the post id is sometimes in the id/class of the article/content section
        el = page_soup.find(id=re.compile(r'post-\d+'))
        if el:
            m = re.search(r'post-(\d+)', el['id'])
            if m:
                post_id = m.group(1)
        else:
            el = page_soup.find(class_=re.compile(r'postid-\d+'))
            if el:
                m = re.search(r'postid-(\d+)', ' '.join(el['class']))
                if m:
                    post_id = m.group(1)
            else:
                m = re.search(r'"articleId","(\d+)"', str(page_soup))
                if m:
                    if m:
                        post_id = m.group(1)
    return post_id


def get_page_soup(url, site_json, save_debug=False):
    # page_html = utils.get_url_html(url, site_json=site_json)
    # if not page_html:
    #     return None
    # if save_debug:
    #     utils.write_file(page_html, './debug/page.html')
    # page_soup = BeautifulSoup(page_html, 'lxml')
    r = curl_cffi.get(url, impersonate=config.impersonate, proxies=config.proxies)
    if r.status_code != 200:
        return None
    if save_debug:
        utils.write_file(r.text, './debug/page.html')
    page_soup = BeautifulSoup(r.text, 'lxml')
    return page_soup


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
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) > 0 and paths[-1] == 'embed':
        del paths[-1]
        args['embed'] = True

    post_id = ''
    page_soup = None
    if 'load_page' in args:
        page_soup = get_page_soup(url, site_json, save_debug)
        if page_soup:
            post_id = find_post_id(page_soup)

    posts_path = ''
    if isinstance(site_json['posts_path'], str):
        posts_path = site_json['posts_path']
    elif isinstance(site_json['posts_path'], dict):
        for key, val in site_json['posts_path'].items():
            if key in paths:
                posts_path = val
                break
        if not posts_path:
            if 'default' in site_json['posts_path']:
                posts_path = site_json['posts_path']['default']
            else:
                logger.warning('unknown posts_path for ' + url)
                return None

    wpjson_path = ''
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
            if 'default' in wpjson_path:
                wpjson_path = site_json['wpjson_path']['default']
            else:
                logger.warning('unknown wpjson_path for ' + url)
                return None

    wp_post = None
    post_url = ''
    if post_id:
        post_url = wpjson_path + posts_path + '/' + post_id

    if not post_url and len(paths) == 0:
        query = parse_qs(split_url.query)
        if query.get('p'):
            post_id = query['p'][0]
            post_url = wpjson_path + posts_path + '/' + query['p'][0]

    if not post_url and 'slug' in site_json:
        if site_json['slug'] and isinstance(site_json['slug'], int):
            if paths[site_json['slug']].isnumeric():
                post_id = paths[site_json['slug']]
                post_url = wpjson_path + posts_path + '/' + post_id
            else:
                post_url = wpjson_path + posts_path + '?slug=' + paths[site_json['slug']]

    if not post_url:
        # look for post id in the path
        m = re.findall(r'\d{4,}', split_url.path)
        if m:
            for it in m:
                # Check for date
                if (len(it) == 4 and int(it[:4]) <= datetime.now().year) or (len(it) == 8 and int(it[:4]) <= datetime.now().year and int(it[4:6]) <= 12 and int(it[6:8]) <= 31):
                    continue
                elif split_url.netloc == 'www.thedailymash.co.uk':
                    post_id = it[8:]
                else:
                    post_id = it
                wp_post = utils.get_url_json(wpjson_path + posts_path + '/' + post_id, site_json=site_json)
                if wp_post:
                    post_id = it
                    post_url = wpjson_path + posts_path + '/' + post_id
                    break

    if not post_url:
        # try slugs
        for it in reversed(paths):
            if ('exclude_slugs' in site_json and it in site_json['exclude_slugs']) or it.isnumeric():
                continue
            wp_post = utils.get_url_json(wpjson_path + posts_path + '?slug=' + it, site_json=site_json)
            if wp_post:
                post_url = wpjson_path + posts_path + '?slug=' + it
                break

    if not post_url and not post_id and not wp_post and not page_soup:
        page_soup = get_page_soup(url, site_json, save_debug)
        if page_soup:
            post_id = find_post_id(page_soup)
            if post_id:
                post_url = wpjson_path + posts_path + '/' + post_id

    if not post_url:
        logger.warning('unable to determine wp-json post url for ' + url)
        return None

    if post_url and not wp_post:
        wp_post = utils.get_url_json(post_url, site_json=site_json)

    if not wp_post:
        return None

    post_data = {}
    if isinstance(wp_post, dict):
        post_data['post'] = wp_post
    elif isinstance(wp_post, list):
        post_data['post'] = wp_post[0]

    yoast_schema_graph = []
    if page_soup:
        # el = page_soup.find('script', class_='yoast-schema-graph')
        # if el:
        #     el_json = json.loads(el.string)
        #     if el_json.get('@graph'):
        #         yoast_schema_graph = el_json['@graph']
        # else:
        for el in page_soup.find_all('script', attrs={"type": "application/ld+json"}):
            el_json = json.loads(el.string)
            if isinstance(el_json, dict):
                if el_json.get('@graph'):
                    yoast_schema_graph += el_json['@graph']
                else:
                    yoast_schema_graph.append(el_json)
            elif isinstance(el_json, list):
                yoast_schema_graph += el_json
    elif post_data['post'].get('yoast_head_json') and post_data['post']['yoast_head_json'].get('schema') and post_data['post']['yoast_head_json']['schema'].get('@graph'):
        yoast_schema_graph = post_data['post']['yoast_head_json']['schema']['@graph']

    if yoast_schema_graph:
        for it in yoast_schema_graph:
            if isinstance(it, dict):
                if isinstance(it['@type'], str):
                    if it['@type'] not in post_data:
                        post_data[it['@type']] = it
                    elif isinstance(post_data[it['@type']], list):
                        post_data[it['@type']].append(it)
                    else:
                        post_data[it['@type']] = [post_data[it['@type']]]
                        post_data[it['@type']].append(it)

    if page_soup:
        post_data['meta'] = {}
        for el in page_soup.find_all('meta'):
            if el.get('content'):
                if el.get('name'):
                    if el['name'] not in post_data['meta']:
                        post_data['meta'][el['name']] = el['content']
                    elif isinstance(post_data['meta'][el['name']], str) and post_data['meta'][el['name']] != el['content']:
                        post_data['meta'][el['name']] = [post_data['meta'][el['name']]]
                        post_data['meta'][el['name']].append(el['content'])
                    elif isinstance(post_data['meta'][el['name']], list) and el['content'] not in post_data['meta'][el['name']]:
                        post_data['meta'][el['name']].append(el['content'])
                elif el.get('property'):
                    if el['property'] not in post_data['meta']:
                        post_data['meta'][el['property']] = el['content']
                    elif isinstance(post_data['meta'][el['property']], str) and post_data['meta'][el['property']] != el['content']:
                        post_data['meta'][el['property']] = [post_data['meta'][el['property']]]
                        post_data['meta'][el['property']].append(el['content'])
                    elif isinstance(post_data['meta'][el['property']], list) and el['content'] not in post_data['meta'][el['property']]:
                        post_data['meta'][el['property']].append(el['content'])

    if save_debug:
        utils.write_file(post_data, './debug/debug.json')

    item = {}
    if 'id' in site_json:
        val = get_data_value(post_data, site_json['id'])
        if val:
            item['id'] = val
    if 'id' not in item:
        if 'id' in post_data['post']:
            item['id'] = post_data['post']['id']
        elif 'guid' in post_data['post'] and isinstance(post_data['post']['guid'], str):
            item['id'] = post_data['post']['guid']
        elif 'guid' in post_data['post'] and isinstance(post_data['post']['guid'], dict):
            item['id'] = post_data['post']['guid']['rendered']

    if 'url' in site_json:
        val = get_data_value(post_data, site_json['url'])
        if val:
            item['url'] = val
    if 'url' not in item:
        if 'link' in post_data['post']:
            item['url'] = post_data['post']['link']
        elif 'yoast_head_json' in post_data['post'] and 'canonical' in post_data['post']['yoast_head_json']:
            item['url'] = post_data['post']['yoast_head_json']['canonical']
        elif 'yoast_head_json' in post_data['post'] and 'og_url' in post_data['post']['yoast_head_json']:
            item['url'] = post_data['post']['yoast_head_json']['og_url']
    if 'replace_netloc' in site_json:
        item['url'] = item['url'].replace(site_json['replace_netloc'][0], site_json['replace_netloc'][1])
    if item['url'].startswith('/'):
        item['url'] = split_url.scheme + '//' + split_url.netloc + item['url']

    if 'title' in site_json:
        if isinstance(site_json['title'], list):
            val = get_data_value(post_data, site_json['title'])
            if val:
                item['title'] = val
        elif isinstance(site_json['title'], dict):
            for el in utils.get_soup_elements(site_json['title'], page_soup):
                item['title'] = el.get_text().strip()
                break
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
    if re.search(r'&#\d+', item['title']):
        item['title'] = html.unescape(item['title'])

    dt = None
    if 'date_published' in site_json:
        val = get_data_value(post_data, site_json['date_published'])
        if val:
            dt = datetime.fromisoformat(val)
    if not dt:
        if 'date_gmt' in post_data['post']:
            dt = datetime.fromisoformat(post_data['post']['date_gmt']).replace(tzinfo=timezone.utc)
        elif 'yoast_head_json' in post_data['post'] and 'article_published_time' in post_data['post']['yoast_head_json']:
            dt = datetime.fromisoformat(post_data['post']['yoast_head_json']['article_published_time'])
    if dt:
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    dt = None
    if 'date_modified' in site_json:
        val = get_data_value(post_data, site_json['date_modified'])
        if val:
            dt = datetime.fromisoformat(val)
    if not dt:
        if 'modified_gmt' in post_data['post']:
            dt = datetime.fromisoformat(post_data['post']['modified_gmt']).replace(tzinfo=timezone.utc)
        elif 'yoast_head_json' in post_data['post'] and 'article_modified_time' in post_data['post']['yoast_head_json']:
            dt = datetime.fromisoformat(post_data['post']['yoast_head_json']['article_modified_time'])
    if dt:
        item['date_modified'] = dt.isoformat()

    authors = []
    if 'author' in site_json:
        if isinstance(site_json['author'], list):
            val = get_data_value(post_data, site_json['author'])
            if val:
                if isinstance(val, str):
                    if 'author_split' in site_json:
                        authors += [x.strip() for x in val.split(site_json['author_split'])]
                    else:
                        authors.append(val.replace(',', '&#44;'))
                elif isinstance(val, dict) and 'author_key' in site_json:
                    if 'author_split' in site_json:
                        authors += [x.strip() for x in val[site_json['author_key']].split(site_json['author_split'])]
                    else:
                        authors.append(val[site_json['author_key']].replace(',', '&#44;'))
                elif isinstance(val, list):
                    for author in val:
                        if isinstance(author, str):
                            if 'author_split' in site_json:
                                authors += [x.strip() for x in author.split(site_json['author_split'])]
                            else:
                                authors.append(author.replace(',', '&#44;'))
                        elif isinstance(author, dict) and 'author_key' in site_json:
                            if 'author_split' in site_json:
                                authors += [x.strip() for x in author[site_json['author_key']].split(site_json['author_split'])]
                            else:
                                authors.append(author[site_json['author_key']].replace(',', '&#44;'))
        elif isinstance(site_json['author'], dict):
            for el in utils.get_soup_elements(site_json['author'], page_soup):
                author = ''
                if el.name == 'meta':
                    author = el['content'].replace(',', '&#44;')
                elif el.name == 'a':
                    author = el.get_text().strip().replace(',', '&#44;')
                else:
                    for it in el.find_all('a', href=re.compile(r'author|correspondents|staff')):
                        author = it.get_text().strip().replace(',', '&#44;')
                        if author not in authors:
                            authors.append(author)
                if not author and 'author_regex' in site_json['author']:
                    m = re.search(site_json['author']['author_regex'], el.get_text().strip())
                    if m:
                        author = m.group(site_json['author']['author_regex_group']).strip().replace(',', '&#44;')
                if not author and el.get_text().strip():
                    author = re.sub(r'^By:?\s*(.*?)[\s\W]*$', r'\1', el.get_text().strip(), flags=re.I)
                if author:
                    author = re.sub(r'(.*?),\s?Associated Press$', r'\1 (Associated Press)', author)
                    if author not in authors:
                        authors.append(author)
                if authors and not site_json['author'].get('multi'):
                    break
    if not authors and 'author' in post_data['post']['_links']:
        for link in  post_data['post']['_links']['author']:
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
                    author = link_json['name']
            if author:
                authors.append(author.replace(',', '&#44;'))
    if not authors and 'ns:byline' in post_data['post']['_links']:
        for link in  post_data['post']['_links']['ns:byline']:
            author = ''
            if site_json.get('replace_links_path'):
                link_href = link['href'].replace(site_json['replace_links_path'][0], site_json['replace_links_path'][1])
            else:
                link_href = link['href']
            if 'skip_wp_byline' not in args:
                link_json = utils.get_url_json(link_href, site_json=site_json)
                if link_json and link_json.get('title') and link_json['title'].get('rendered'):
                    author = link_json['title']['rendered']
            if author:
                authors.append(author.replace(',', '&#44;'))
    if not authors:
        if 'yoast_head_json' in post_data['post'] and 'author' in post_data['post']['yoast_head_json']:
            authors.append(post_data['post']['yoast_head_json']['author'].replace(',', '&#44;'))
        elif 'yoast_head_json' in post_data['post'] and 'twitter_misc' in post_data['post']['yoast_head_json'] and post_data['post']['yoast_head_json']['twitter_misc'].get('Written by'):
            authors.append(post_data['post']['yoast_head_json']['twitter_misc']['Written by'].replace(',', '&#44;'))
        elif 'meta' in post_data and 'og:site_name' in post_data['meta']:
            authors.append(post_data['meta']['og:site_name'])
    if authors:
        item['authors'] = [{"name": x.replace('&#44;', ',')} for x in authors]
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)).replace('&#44;', ',')
        }
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
        elif isinstance(site_json['author'], dict):
            for el in utils.get_soup_elements(site_json['tags'], page_soup):
                if el.name == 'a' or ('no_link' in site_json['tags'] and site_json['tags']['no_link'] == True):
                    item['tags'].append(el.get_text().strip())
                else:
                    for it in el.find_all('a'):
                        item['tags'].append(it.get_text().strip())
    if not item['tags'] and 'wp:term' in post_data['post']['_links'] and 'skip_wp_terms' not in args:
        for link in post_data['post']['_links']['wp:term']:
            if 'taxonomy' in link and link['taxonomy'] != 'author' and link['taxonomy'] != 'channel' and link['taxonomy'] != 'contributor' and link['taxonomy'] != 'site-layouts' and link['taxonomy'] != 'lineup' and link['taxonomy'] != 'content_type' and not link['taxonomy'].startswith('tc_'):
                if site_json.get('replace_links_path'):
                    link_href = link['href'].replace(site_json['replace_links_path'][0], site_json['replace_links_path'][1])
                else:
                    link_href = link['href']
                link_json = utils.get_url_json(link['href'], site_json=site_json)
                if link_json:
                    for it in link_json:
                        if it.get('name'):
                            item['tags'].append(it['name'])
    if len(item['tags']) == 0:
        if post_data['post'].get('class_list'):
            for val in post_data['post']['class_list']:
                it = val.split('-')
                if it[0] != 'post' and it[0] != 'type' and it[0] != 'has' and it[0] != 'status' and it[0] != 'format' and it[0] != 'hentry':
                    item['tags'].append(' '.join(it[1:]))
    if len(item['tags']) == 0:
        del item['tags']

    if 'summary' in site_json:
        if isinstance(site_json['summary'], list):
            val = get_data_value(post_data, site_json['title'])
            if val:
                item['summary'] = val
    if 'summary' not in item:
        if 'excerpt' in post_data['post'] and isinstance(post_data['post']['excerpt'], str):
            item['summary'] = post_data['post']['excerpt']
        elif 'excerpt' in post_data['post'] and isinstance(post_data['post']['excerpt'], dict):
            item['summary'] = re.sub(r'^<p>|</p>$', '', post_data['post']['excerpt']['rendered'].strip())
        elif 'yoast_head_json' in post_data['post'] and 'description' in post_data['post']['yoast_head_json']:
            item['summary'] = post_data['post']['yoast_head_json']['description']
        elif 'yoast_head_json' in post_data['post'] and 'og_description' in post_data['post']['yoast_head_json']:
            item['summary'] = post_data['post']['yoast_head_json']['og_description']

    item['content_html'] = ''

    subtitle = ''
    if 'subtitle' in site_json:
        if isinstance(site_json['subtitle'], list):
            val = get_data_value(post_data, site_json['subtitle'])
            if val:
                subtitle = re.sub(r'^<p>|</p>$', '', val.strip())
        elif isinstance(site_json['subtitle'], dict):
            for el in utils.get_soup_elements(site_json['subtitle'], page_soup):
                subtitle = el.get_text().strip()
                break
    if subtitle and not subtitle.endswith('[&hellip;]'):
        item['content_html'] += '<p><em>' + subtitle + '</em></p>'

    lede_html = ''
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

    elif split_url.netloc == 'www.stereogum.com':
        if 'hero' in post_data['post']['acf'] and post_data['post']['acf']['hero'].get('image'):
            lede_html = utils.add_image(post_data['post']['acf']['hero']['image'], post_data['post']['acf']['hero'].get('caption'))
            if 'image' not in item:
                item['image'] = post_data['post']['acf']['hero']['image']
        elif 'post_hero' in post_data['post']['acf'] and post_data['post']['acf']['post_hero'].get('image'):
            lede_html = utils.add_image(post_data['post']['acf']['post_hero']['image'], post_data['post']['acf']['post_hero'].get('caption'))
            if 'image' not in item:
                item['image'] = post_data['post']['acf']['post_hero']['image']

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
                el = page_soup.find(attrs={"data-video_id": post_data['post']['lead_media']['id'], "data-video_params": True})
                if el:
                    params = json.loads(el['data-video_params'].replace("'/", '"'))
                    # utils.write_file(params, './debug/video.json')
                    # Get higher quality image
                    lura_rest = utils.get_url_html('https://tkx.mp.lura.live/rest/v2/mcp/video/' + params['video'] + '?anvack=' + params['accessKey'])
                    if lura_rest:
                        i = lura_rest.find('{')
                        j = lura_rest.rfind('}') + 1
                        video_json = json.loads(lura_rest[i:j])
                        poster = video_json['src_image_url']
                        caption = video_json['def_title']
                    if params.get('accessKey') and params.get('token'):
                        key_json = {
                            "v": params['video'],
                            "token": params['token'],
                            "accessKey": params['accessKey']
                        }
                        key = base64.b64encode(json.dumps(key_json, separators=(',', ':')).encode()).decode()
                        lura_url = 'https://w3.mp.lura.live/player/prod/v3/anvload.html?key=' + key
                        video_url = config.server + '/video?url=' + quote_plus(lura_url)
                        lede_html = utils.add_image(poster, caption, link=video_url, overlay=config.video_button_overlay)
                    elif 'nxs' in params and 'mp4Url' in params['nxs']:
                        lede_html = utils.add_video(params['nxs']['mp4Url'], 'video/mp4', poster, caption, use_videojs=True)
                    elif video_json and video_json.get('published_urls') and video_json['published_urls'][0].get('embed_url'):
                        # embed_url looks like it will expire
                        lede_html = utils.add_video(video_json['published_urls'][0]['embed_url'], 'application/x-mpegURL', poster, caption, use_videojs=True)
                    if 'image' not in item:
                        item['image'] = poster

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

    if not lede_html and 'lede_image' in site_json and isinstance(site_json['lede_image'], list):
        val = get_data_value(post_data, site_json['lede_image'])
        if val:
            img_src = val
            caption = ''
            if 'lede_caption' in site_json and isinstance(site_json['lede_caption'], list):
                val = get_data_value(post_data, site_json['lede_caption'])
                if val:
                    caption = val
            lede_html = utils.add_image(img_src, caption)
            if 'image' not in item:
                item['image'] = img_src

    if not lede_html and post_data['post']['_links'].get('wp:featuredmedia') and 'skip_wp_media' not in args:
        for link in  post_data['post']['_links']['wp:featuredmedia']:
            lede_html = add_wp_media(link['href'], site_json)
            if lede_html and 'image' not in item:
                m = re.search(r'src="([^"]+)', lede_html)
                item['image'] = m.group(1)

    if not lede_html and 'jetpack_featured_media_url' in post_data['post']:
        lede_html = utils.add_image(post_data['post']['jetpack_featured_media_url'])
        if 'image' not in item:
            item['image'] = post_data['post']['jetpack_featured_media_url']

    if lede_html and lede_html != 'SKIP' and 'skip_lede_img' not in args:
        item['content_html'] += lede_html

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if split_url.netloc == 'www.rollingstone.com' and post_data['post']['meta'].get('pmc-review-rating'):
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
            val = []
            for it in post_data['post']['acf']['game_genre_tax']:
                link_json = utils.get_url_json(site_json['wpjson_path'] + '/wp/v2/game-genre/' + str(it), site_json=site_json)
                if link_json:
                    val.append('<a href="{}" target="_blank">{}</a>'.format(link_json['link'], link_json['name']))
            if val:
                item['content_html'] += '<li>Genre: ' + ', '.join(val) + '</li>'
            val = []
            for it in post_data['post']['acf']['esrb_rating']:
                link_json = utils.get_url_json(site_json['wpjson_path'] + '/wp/v2/esrb-rating/' + str(it), site_json=site_json)
                if link_json:
                    val.append('<a href="{}" target="_blank">{}</a>'.format(link_json['link'], link_json['name']))
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
    else:
        content_html = post_data['post']['content']['rendered']

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

    item['content_html'] += format_content(content_html, item['url'], args, site_json, page_soup, wpjson_path)

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
    return item


def format_content(content_html, url, args, site_json=None, page_soup=None, wpjson_path='', module_format_content=None):
    utils.write_file(content_html, './debug/debug.html')

    split_url = urlsplit(url)
    base_url = split_url.scheme + '://' + split_url.netloc

    soup = BeautifulSoup(content_html, 'html.parser')

    # remove comments
    for el in soup.find_all(text=lambda text: isinstance(text, Comment)):
        el.extract()

    if site_json:
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
                            del el[key]
                        for key, val in it['new']['attrs'].items():
                            el[key] = val
        if 'replace' in site_json:
            for it in site_json['replace']:
                for el in utils.get_soup_elements(it, soup):
                    el.replace_with(BeautifulSoup(it['new_html'], 'html.parser'))
        if 'decompose' in site_json:
            for it in site_json['decompose']:
                for el in utils.get_soup_elements(it, soup):
                    el.decompose()
        if 'unwrap' in site_json:
            for it in site_json['unwrap']:
                for el in utils.get_soup_elements(it, soup):
                    el.unwrap()
        if 'clear_attrs' in site_json and isinstance(site_json['clear_attrs'], list):
            for it in site_json['clear_attrs']:
                for el in utils.get_soup_elements(it, soup):
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

    if site_json.get('gallery'):
        for tag in site_json['gallery']:
            galleries = utils.get_soup_elements(tag, soup)
            for gallery in galleries:
                new_html = ''
                images = utils.get_soup_elements(tag['image'], gallery)
                if images:
                    gallery_images = []
                    new_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                    for image in images:
                        img_src = get_img_src(image, site_json, base_url, 2000)
                        if not img_src:
                            continue
                        thumb = get_img_src(image, site_json, base_url, 800)
                        captions = []
                        if tag['image'].get('credit'):
                            it = utils.get_soup_elements(tag['image']['credit'], image)
                            if it:
                                captions.append(it[0].decode_contents())
                                it[0].decompose()
                        if tag['image'].get('caption'):
                            it = utils.get_soup_elements(tag['image']['caption'], image)
                            if it:
                                captions.insert(0, it[0].decode_contents())
                                it[0].decompose()
                        caption = ' | '.join(captions)
                        new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src) + '</div>'
                        gallery_images.append({"src": img_src, "caption": caption, "thumb": thumb})
                    new_html += '</div>'
                    captions = []
                    if tag.get('credit'):
                        it = utils.get_soup_elements(tag['credit'], gallery)
                        if it:
                            captions.append(it[0].decode_contents())
                            it[0].decompose()
                    if tag.get('caption'):
                        it = utils.get_soup_elements(tag['caption'], gallery)
                        if it:
                            captions.insert(0, it[0].decode_contents())
                            it[0].decompose()
                    if captions:
                        new_html += '<div><small>' + ' | '.join(captions) + '</small></div>'
                    if len(images) > 2:
                        gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
                        new_html = '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + new_html
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
                    img_src = get_img_src(image, site_json, base_url)
                    if not img_src:
                        continue
                    captions = []
                    if tag.get('credit'):
                        it = utils.get_soup_elements(tag['credit'], image)
                        if it and it[0].get_text().strip():
                            captions.append(it[0].decode_contents())
                            it[0].decompose()
                    if tag.get('caption'):
                        it = utils.get_soup_elements(tag['caption'], image)
                        if it and it[0].get_text().strip():
                            captions.insert(0, it[0].decode_contents())
                            it[0].decompose()
                    caption = ' | '.join(captions)
                    if image.name == 'a':
                        link = image['href']
                    else:
                        it = image.select('a:has(> img)')
                        if it:
                            link = it[0]['href']
                        elif image.name == 'a':
                            link = image['href']
                        else:
                            link = ''
                    new_html = utils.add_image(img_src, caption, link=link)
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    if 'unwrap_figure' in tag:
                        new_el.figure.unwrap()
                    image.replace_with(new_el)

    if site_json.get('extras'):
        for tag in site_json['extras']:
            extras = utils.get_soup_elements(tag, soup)
            if extras:
                for extra in extras:
                    if extra.get('id') and extra['id'] == 'gp-review-results':
                        for el in extra.find_all('i', class_='fa'):
                            el.decompose()
                        new_html = '<div style="display:flex; flex-wrap:wrap; gap:8px; padding:8px; margin:1em 0; border:1px solid light-dark(#333,#ccc); border-radius:10px;">'
                        el = extra.find(id='gp-good-points')
                        if el:
                            new_html += '<div style="flex12; min-width:240px; color:ForestGreen;">'
                            it = el.find(id='gp-good-title')
                            if it:
                                new_html += '<div style="text-align:center; font-weight:bold;">' + it.get_text().strip() + '</div>'
                            else:
                                new_html += '<div style="text-align:center; font-weight:bold;">Good</div>'
                            it = el.find('ul')
                            if it:
                                it.attrs = {}
                                new_html += str(it).replace('<ul>', '<ul style=\'list-style-type:"✓&nbsp;"\'>')
                            new_html += '</div>'
                        el = extra.find(id='gp-bad-points')
                        if el:
                            new_html += '<div style="flex:1; min-width:240px; color:FireBrick;">'
                            it = el.find(id='gp-bad-title')
                            if it:
                                new_html += '<div style="text-align:center; font-weight:bold;">' + it.get_text().strip() + '</div>'
                            else:
                                new_html += '<div style="text-align:center; font-weight:bold;">Bad</div>'
                            it = el.find('ul')
                            if it:
                                it.attrs = {}
                                new_html += str(it).replace('<ul>', '<ul style=\'list-style-type:"✗&nbsp;"\'>')
                            new_html += '</div>'
                        el = extra.find(id='gp-review-results-rating')
                        if el:
                            new_html += '<div style="flex:1; text-align:center; color:GoldenRod;">'
                            it = el.find(class_='gp-rating-score')
                            if it:
                                new_html +=  '<div style="font-size:3em; font-weight:bold;">' + str(it.get_text().strip()) + '</div>'
                            it = el.find(class_='gp-rating-text')
                            if it:
                                new_html +=  '<div>' + str(it.get_text().strip()) + '</div>'
                            if page_soup:
                                it = page_soup.select('header.gp-entry-header > div.gameinfo > img')
                                if it:
                                    img_src = it[0]['src']
                                    if img_src.startswith('/'):
                                        img_src = base_url + img_src
                                    new_html += '<img src="' + img_src + '" style="width:100% max-width:160px;">'
                            new_html += '</div>'
                        new_el = BeautifulSoup(new_html, 'html.parser')
                        extra.replace_with(new_el)
                    elif extra.get('id') and extra['id'] == 'review':
                        new_html = ''
                        el = extra.select('div.review-total-box > div')
                        if el and el[0].string.replace('.', '').isnumeric():
                            n = 20 * float(el[0].string)
                            new_html += utils.add_score_gauge(n, el[0].string)
                        el = extra.find(class_='review-desc')
                        if el:
                            for it in el.find_all('p'):
                                it.attrs = {}
                            new_html += el.decode_contents()
                        if extra.find(class_='review-pros-cons'):
                            new_html += '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:1em 0;">'
                            new_html += '<div style="flex:1; min-width:240px; color:ForestGreen;"><div style="font-weight:bold;">Pros</div>'
                            el = extra.select('div.review-pros > ul')
                            if el:
                                new_html += str(el[0]).replace('<ul>', '<ul style=\'list-style-type:"✓&nbsp;"\'>')
                            new_html += '</div><div style="flex:1; min-width:240px; color:FireBrick;"><div style="font-weight:bold;">Cons</div>'
                            el = extra.select('div.review-cons > ul')
                            if el:
                                new_html += str(el[0]).replace('<ul>', '<ul style=\'list-style-type:"✗&nbsp;"\'>')
                            new_html += '</div></div>'
                        for el in extra.select('ul.review-links > li > a'):
                            new_html += utils.add_button(el['href'], el.string)
                        new_el = BeautifulSoup(new_html, 'html.parser')
                        extra.replace_with(new_el)
                    elif extra.get('class') and 'bgr-product-review-block' in extra['class']:
                        new_html = ''
                        el = extra.select('div.bgr-product-review-info h3')
                        if el:
                            new_html += '<h3 style="margin-bottom:0;">' + el[0].get_text().strip() + '</h3>'
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
                            new_html += '<div style="flex:1; min-width:240px; color:FireBrick;"><div style="text-align:center; font-weight:bold;">Cons</div>'
                            el = extra.find('ul', class_='cons')
                            if el:
                                new_html += str(el).replace('<ul>', '<ul style=\'list-style-type:"✗&nbsp;"\'>')
                            new_html += '</div></div>'
                        if extra.find(class_='bgr-product-review-vendors'):
                            for el in extra.select('div.bgr-product-review-vendors > table tr:has(td > a.see-it)'):
                                caption = ''
                                it = el.find('td', class_='sale-price')
                                if it:
                                    caption += it.get_text().strip()
                                else:
                                    it = el.find('td', class_='vendor-product-info')
                                    if it:
                                        caption += it.get_text().strip()
                                it = el.find('span', class_='vendor-name')
                                if it:
                                    caption += ' at ' + it.get_text().strip()
                                else:
                                    it = el.find('img', class_='vendor-logo')
                                    if it:
                                        caption += ' at ' + it['alt'].replace('logo', '').replace('-', ' ').strip().title()
                                it = el.find('a', class_='see-it')
                                new_html += utils.add_button(it['href'], caption)
                        new_el = BeautifulSoup(new_html, 'html.parser')
                        extra.replace_with(new_el)
                    elif extra.get('class') and 'abr-post-review' in extra['class']:
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
                    elif extra.get('class') and 'tdb_single_review_overall' in extra['class']:
                        # https://www.nme.com/reviews/film-reviews/echo-valley-review-sydney-sweeney-julianne-moore-apple-tv-3869048
                        n = len(extra.find_all('i', class_='td-icon-star'))
                        new_el = BeautifulSoup(utils.add_stars(n), 'html.parser')
                        extra.replace_with(new_el)           
                    elif extra.get('class') and 'review-summary' in extra['class']:
                        # https://www.the-ambient.com/reviews/reolink-duo-3-wifi-review/
                        el = extra.find('div', class_='star-rating')
                        if el:
                            n = len(el.select('div.full-stars > i.fa-star')) + 0.5 * len(el.select('div.full-stars > i.fa-star-half'))
                            new_el = BeautifulSoup(utils.add_stars(n), 'html.parser')
                            el.replace_with(new_el)
                        extra.name = 'div'
                        extra.attrs = {}
                        extra['style'] = 'margin:1em 0; padding:0 1em 1em 1em; background-color:#e5e7eb; border-radius:10px;'
                    elif extra.get('class') and 'review-wu-content' in extra['class']:
                        # https://gadgetsandwearables.com/2025/06/27/xiaomi-smart-band-10-review/
                        new_html = ''
                        el = extra.find(class_='review-wu-grade-content')
                        if el and el.span and el.span.string.replace('.', '').isnumeric():
                            n = int(el.span.string.replace('.', ''))
                            # new_html += '<div style="margin:1em auto; width:8rem; aspect-ratio:1; line-height:8rem; text-align:center; font-size:3rem; font-weight:bold; border:solid 24px #8DC153; border-radius:50%; mask:linear-gradient(red 0 0) padding-box, conic-gradient(red var(--p, {}%), transparent 0%) border-box;">{}</div>'.format(n, el.span.string)
                            new_html += utils.add_score_gauge(n, el.span.string)
                        el = extra.find(class_='review-wu-bars')
                        if el:
                            for it in el.find_all(class_='rev-option'):
                                new_html += utils.add_bar(it.h3.get_text().strip(), int(it['data-value']), 100, False)
                        new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                        for it in extra.find_all(class_=['pros', 'cons']):
                            new_html += '<div style="margin:1em 0; flex:1; min-width:256px;">'
                            if it.h2:
                                new_html += '<div style="font-weight:bold;">' + it.h2.get_text().strip() + '</div>'
                            if it.ul:
                                if 'pros' in it['class']:
                                    new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + it.ul.decode_contents() + '</ul>'
                                elif 'cons' in it['class']:
                                    new_html += '<ul style=\'color:FireBrick; list-style-type:"✗&nbsp;"\'>' + it.ul.decode_contents() + '</ul>'
                            new_html += '</div>'
                        new_html += '</div>'
                        new_el = BeautifulSoup(new_html, 'html.parser')
                        extra.replace_with(new_el)
                    elif extra.get('class') and 'review-rating-container' in extra['class']:
                        # https://wccftech.com/review/gamesir-supernova-controller-review-aesthetics-optimal-wireless-experience-in-one-package/
                        new_html = ''
                        el = extra.select('div.rating-box > span')
                        if el and el[0].string.replace('.', '').isnumeric():
                            n = int(el[0].string.replace('.', ''))
                            new_html += utils.add_score_gauge(n, el[0].string)
                            new_el = BeautifulSoup(new_html, 'html.parser')
                            extra.replace_with(new_el)
                    elif extra.get('class') and 'review-verdict' in extra['class']:
                        # https://wccftech.com/review/gamesir-supernova-controller-review-aesthetics-optimal-wireless-experience-in-one-package/
                        new_html = ''
                        for el in extra.find_all('p', recursive=False):
                            new_html += '<p style="font-style:italic;">' + el.decode_contents() + '</p>'
                        if extra.find(class_='review-pros-cons'):
                            new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                            for el in extra.select('div.review-pros-cons > ul'):
                                new_html += '<div style="margin:1em 0; flex:1; min-width:256px;">'
                                if el.h6:
                                    caption = el.h6.get_text().strip()
                                    new_html += '<div style="font-weight:bold;">' + caption + '</div>'
                                    el.h6.decompose()
                                    if caption.lower() == 'pros':
                                        new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + el.decode_contents() + '</ul>'
                                    elif caption.lower() == 'cons':
                                        new_html += '<ul style=\'color:FireBrick; list-style-type:"✗&nbsp;"\'>' + el.decode_contents() + '</ul>'
                                else:
                                    new_html += str(el)
                                new_html += '</div>'
                            new_html += '</div>'
                        new_el = BeautifulSoup(new_html, 'html.parser')
                        extra.replace_with(new_el)
                    elif extra.get('class') and 'wp-block-group' in extra['class'] and extra.find(class_='ratingBlock'):
                        new_html = ''
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
                                    caption = el.h4.get_text().strip()
                                    new_html += '<div style="font-weight:bold;">' + caption + '</div>'
                                    if caption.lower() == 'pros':
                                        new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + el.ul.decode_contents() + '</ul>'
                                    elif caption.lower() == 'cons':
                                        new_html += '<ul style=\'color:FireBrick; list-style-type:"✗&nbsp;"\'>' + el.ul.decode_contents() + '</ul>'
                                else:
                                    new_html += str(el)
                                new_html += '</div>'
                            new_html += '</div>'
                        new_el = BeautifulSoup(new_html, 'html.parser')
                        extra.replace_with(new_el)
                    elif extra.get('class') and 'wp-block-jetpack-videopress' in extra['class'] and extra.iframe:
                        video_id = list(filter(None, urlsplit(extra.iframe['src']).path.split('/')))[-1]
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
                            new_el = BeautifulSoup(new_html, 'html.parser')
                            extra.replace_with(new_el)

    for el in soup.find_all(recursive=False):
        # print(el.name)
        new_html = ''
        if el.name == 'iframe':
            if el.get('data-src'):
                new_html = utils.add_embed(el['data-src'])
            else:
                new_html = utils.add_embed(el['src'])
        elif el.name == 'table':
            el.attrs = {}
            el['style'] = 'width:100%; border-collapse:collapse; border-top:1px solid light-dark(#333,#ccc);'
            for i, it in enumerate(el.find_all('tr')):
                it.attrs = {}
                it['style'] = 'border-bottom:1px solid light-dark(#333,#ccc);'
                if i % 2 == 0:
                    it['style'] += ' background-color:#e5e7eb;'
            for it in el.find_all(['td', 'th']):
                it.attrs = {}
                it['style'] = 'padding:8px;'
            continue
        elif el.name == 'blockquote':
            if not el.get('class'):
                el.attrs = {}
                el['style'] = config.blockquote_style
                continue
            elif 'pullquote' in el['class']:
                # TODO: author
                new_html += utils.add_pullquote(el.decode_contents())
            elif el.cite:
                cite = el.cite.decode_contents()
                el.cite.decompose()
                new_html += utils.add_pullquote(el.decode_contents(), cite)
            elif el.get('data-shortcode-type') == 'pullquote':
                new_html += utils.add_pullquote(el.decode_contents())
            elif 'instagram-media' in el['class']:
                new_html += utils.add_embed(el['data-instgrm-permalink'])
            elif 'twitter-tweet' in el['class']:
                links = el.find_all('a')
                if links:
                    new_html = utils.add_embed(links[-1]['href'])
            elif 'bluesky-embed' in el['class']:
                new_html += utils.add_embed(el['data-bluesky-uri'].replace('at://', 'https://bsky.app/profile/').replace('app.bsky.feed.post', 'post'))
            elif 'wp-block-quote' in el['class']:
                el.attrs = {}
                el['style'] = config.blockquote_style
                continue
            else:
                logger.warning('unhandled blockquote class {} in {}'.format(el['class'], url))
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
            if 'wp-block-embed' in el['class']:
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
                        it = el.find(attrs={"data-videoid": True})
                        new_html = utils.add_embed('https://www.youtube.com/watch?v=' + it['videoid'])
                elif 'wp-block-embed-twitter' in el['class']:
                    link = el.find_all('a')
                    if link:
                        new_html = utils.add_embed(link[-1]['href'])
                    else:
                        it = el.find(class_='wp-block-embed__wrapper')
                        if it:
                            link = it.get_text().strip()
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
            elif 'jetpack-video-wrapper' in el['class'] and el.iframe:
                new_html = utils.add_embed(el.iframe['src'])
            elif 'video-player' in el['class']:
                it = el.find('video', class_='video-js')
                if it and it.get('data-opts'):
                    data_props = json.loads(html.unescape(it['data-opts']))
                    if data_props['plugins']['sources'].get('iOSRenditions'):
                        new_html += utils.add_video(data_props['plugins']['sources']['iOSRenditions'][-1]['url'], 'application/x-mpegURL', data_props['poster'], data_props['title'])
                    elif data_props['plugins']['sources'].get('renditions'):
                        new_html += utils.add_video(data_props['plugins']['sources']['renditions'][0]['url'], 'video/mp4', data_props['poster'], data_props['title'])
            elif 'wp-block-jetpack-videopress' in el['class'] and el.iframe:
                video_id = list(filter(None, urlsplit(el.iframe['src']).path.split('/')))[-1]
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
            elif 'ns-block-custom-html' in el['class'] and el.iframe:
                new_html = utils.add_embed(el.iframe['src'])
            elif 'wp-block-pullquote' in el['class']:
                it = el.find('cite')
                if it:
                    cite = it.decode_contents()
                    it.decompose()
                else:
                    cite = ''
                new_html = utils.add_pullquote(el.blockquote.decode_contents(), cite)
            elif 'wp-block-buttons' in el['class'] or 'wp-block-button' in el['class']:
                for it in el.find_all('a', class_='wp-block-button__link'):
                    new_html += utils.add_button(it['href'], it.get_text().strip())
            elif 'button' in el['class'] and el.name == 'a':
                new_html += utils.add_button(el['href'], el.get_text().strip())
            elif 'wp-block-prc-block-subtitle' in el['class']:
                new_html = '<p><em>' + el.get_text().strip() + '</em></p>'
            elif 'wp-block-details' in el['class']:
                # https://www.pewresearch.org/politics/2025/06/17/americans-have-mixed-to-negative-views-of-trump-administration-immigration-actions/
                el.attrs = {}
                el['style'] = 'margin:1em 0; padding:8px; border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#e5e7eb;'
                it = el.find('summary')
                if it:
                    it.attrs = {}
                    it['style'] = 'font-weight:bold;'
                continue
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
            elif 'star-rating' in el['class']:
                # https://www.the-ambient.com/reviews/reolink-duo-3-wifi-review/
                n = len(el.select('div.full-stars > i.fa-star')) + 0.5 * len(el.select('div.full-stars > i.fa-star-half'))
                new_html += utils.add_stars(n)
            elif 'product-card' in el['class']:
                # https://spy.com/articles/health-wellness/fitness/best-yoga-mats-1203009086/
                new_html = '<hr style="margin:2em 0;"><div style="display:flex; flex-wrap:wrap; gap:1em;">'
                it = el.find(class_='product-card-image-wrapper')
                if it:
                    link = it.find(class_='c-lazy-image__link')
                    img_src = get_img_src(link, site_json, base_url)
                    captions = []
                    if it.figcaption and it.figcaption.cite and it.figcaption.cite.get_text().strip():
                        captions.append(it.figcaption.cite.get_text())
                        it.figcaption.cite.decompose()
                    if it.figcaption and it.figcaption.get_text().strip():
                        captions.insert(0, it.figcaption.get_text())
                    new_html += '<div style="flex:1; min-width:256px;">' + utils.add_image(img_src, ' | '.join(captions), link=link['href']) + '</div>'
                new_html += '<div style="flex:1; min-width:256px;">'
                it = el.find(class_='article-kicker')
                if it:
                    new_html += '<div style="margin-top:0.5em; margin-bottom:0.5em; text-align:center;"><span style="padding:0.4em; font-weight:bold; color:white; background-color:#153969;">' + it.get_text().strip() + '</span></div>'
                it = el.find(class_='c-title')
                if it:
                    new_html += '<div style="font-size:1.2em; font-weight:bold; text-align:center;">' + it.get_text().strip() + '</div>'
                for it in el.select('div.buy-now-buttons > div'):
                    captions = []
                    link = it.find(class_='c-button')
                    captions.append(link.get_text().strip())
                    if it.p and it.p.span and it.p.span.get_text().strip():
                        captions.append(it.p.span.get_text().strip())
                    new_html += utils.add_button(link['href'], ' '.join(captions))
                new_html += '</div></div>'
                it = el.find(class_='c-dek')
                if it:
                    it.attrs = {}
                    new_html += str(it)
            elif 'multiple-products' in el['class']:
                # https://spy.com/articles/health-wellness/fitness/best-yoga-mats-1203009086/
                it = el.select('div.faq-title > h3')
                if it:
                    it[0].attrs = {}
                    new_html += str(it[0])
                for it in el.find_all(class_='o-multiple-products-item'):
                    link = it.find('a', class_='c-lazy-image__link')
                    img_src = get_img_src(link, site_json, base_url, 300)
                    card_image = '<a href="' + link['href'] + '" target="_blank"><div style="width:100%; height:100%; background:url(\'' + img_src + '\'); background-position:center; background-size:cover; border-radius:10px 0 0 10px;"></div></a>'
                    card_content = ''
                    if it.find(class_='article-kicker'):
                        card_content += '<div style="margin-top:0.5em; margin-bottom:0.5em; text-align:center; font-size:0.8em;"><span style="padding:0.4em; font-weight:bold; color:white; background-color:#153969;">' + it.find(class_='article-kicker').get_text().strip() + '</span></div>'
                    card_content += '<div style="font-weight:bold; text-align:center;">' + it.find(class_='c-title').get_text().strip() + '</div>'
                    link = it.find('a', class_='c-button')
                    card_content += utils.add_button(link['href'], link.get_text().strip())
                    new_html += utils.format_small_card(card_image, card_content, '', content_style='padding:8px;', align_items='start') + '<div>&nbsp;</div>'
            elif 'pros-and-cons' in el['class']:
                # https://spy.com/articles/grooming/hair/nutrafol-for-men-review-1202925779/
                new_html = '<hr style="margin:2em 0;"><div style="display:flex; flex-wrap:wrap; gap:1em;">'
                for it in el.find_all(class_='pros-and-cons__inner'):
                    new_html += '<div style="flex:1; min-width:256px;">'
                    if it.h2:
                        new_html += '<div style="font-weight:bold;">' + it.h2.get_text().strip() + '</div>'
                    if it.ul:
                        if 'is-style-pros' in it.ul['class']:
                            new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + it.ul.decode_contents() + '</ul>'
                        elif 'is-style-cons' in it.ul['class']:
                            new_html += '<ul style=\'color:FireBrick; list-style-type:"✗&nbsp;"\'>' + it.ul.decode_contents() + '</ul>'
                        else:
                            new_html += '<ul>' + it.ul.decode_contents() + '</ul>'
                    new_html += '</div>'
                new_html += '</div>'
            elif 'pros-cons' in el['class'] and 'block-two-column-boxes' in el['class']:
                # https://www.the-ambient.com/reviews/reolink-duo-3-wifi-review/
                for it in el.find_all('i'):
                    it.decompose()
                new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em; margin-top:1em;">'
                for col in el.find_all(class_='col'):
                    new_html += '<div style="flex:1; min-width:256px;">'
                    it = col.find(class_='col-header')
                    if it:
                        caption = it.get_text().strip()
                        new_html += '<div style="font-weight:bold;">' + caption + '</div>'
                    else:
                        caption = ''
                    it = col.select('div.col-content > ul')
                    if it:
                        if 'pro' in caption.lower():
                            new_html += '<ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + it[0].decode_contents() + '</ul>'
                        elif 'con' in caption.lower():
                            new_html += '<ul style=\'color:FireBrick; list-style-type:"✗&nbsp;"\'>' + it[0].decode_contents() + '</ul>'
                        else:
                            new_html += '<ul>' + it[0].ul.decode_contents() + '</ul>'
                    new_html += '</div>'
                new_html += '</div>'
            elif 'phoenix-review-score-block-heading__container' in el['class'] and el.find(class_='star-rating'):
                n = len(el.select('div.full-stars > i.fa-star')) + 0.5 * len(el.select('div.full-stars > i.fa-star-half'))
                new_html += utils.add_stars(n)
            elif 'faq' in el['class']:
                # https://spy.com/articles/health-wellness/fitness/best-yoga-mats-1203009086/
                it = el.select('div.faq-title > h3')
                if it:
                    it[0].attrs = {}
                    new_html += str(it[0])
                for it in el.find_all(class_='o-faq-item'):
                    new_html += '<details><summary style="margin:1em 0;"><strong>' + it.h3.get_text() + '</strong></summary><p style="margin-left:1.1em;">' + it.p.decode_contents() + '</p></details>'
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
            else:
                logger.warning('unhandled element class ' + str(el['class']))

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

    has_dropcap = False
    for el in soup.find_all(class_=['dropcap', 'dropcaps', 'drop-cap', 'add-drop-cap', 'has-drop-cap', 'big-cap', 'big-letter', 'firstcharacter']):
        if el.name == 'p':
            el.attrs = {}
            el['class'] = 'dropcap'
            if has_dropcap == False:
                new_html = '<style>' + config.dropcap_style + '</style>'
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                has_dropcap = True
        else:
            it = el.find_parent('p')
            if it:
                it.attrs = {}
                it['class'] = 'dropcap'
                if has_dropcap == False:
                    new_html = '<style>' + config.dropcap_style + '</style>'
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    it.insert_after(new_el)
                    has_dropcap = True
                el.unwrap()
    if 'first_paragraph_dropcap' in args:
        el = soup.find('p')
        el['class'] = 'dropcap'
        if has_dropcap == False:
            new_html = '<style>' + config.dropcap_style + '</style>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            has_dropcap = True

    content = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', str(soup))
    return content


def get_feed(url, args, site_json, save_debug=False):
    if 'rss' in url or '/feed' in url:
        return rss.get_feed(url, args, site_json, save_debug, get_content)
    return None
