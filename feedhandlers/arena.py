import html, json, re
import curl_cffi
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wp_posts_v2

import logging
logger = logging.getLogger(__name__)


def resize_img_src(img_src, width=1200):
    split_url = urlsplit(img_src)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[0] == '.image':
        return 'https://' + split_url.netloc + '/.image/w_' + str(width) + ',q_auto:good,c_limit/' + paths[-2] + '/' + paths[-1]


def get_next_data(url, save_debug):
    split_url = urlsplit(url)
    state_tree = [
        "",
        {
            "children": [
                "(rest)",
                {
                    "children":[
                        [
                            "path",
                            split_url.path[1:],
                            "c"
                        ],
                        {
                            "children": [
                                "__PAGE__",
                                {},
                                split_url.path,
                                "refresh"
                            ]
                        },
                        None,
                        "refetch"
                    ]
                }
            ]
        }
    ]
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "cache-control": "no-cache",
        "next-router-state-tree": quote_plus(json.dumps(state_tree, separators=(',', ':'))),
        "pragma": "no-cache",
        "priority": "u=1, i",
        "rsc": "1",
        "sec-ch-ua": "\"Chromium\";v=\"140\", \"Not=A?Brand\";v=\"24\", \"Microsoft Edge\";v=\"140\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }
    return utils.get_url_html(url, headers=headers)


def get_next_json(url, save_debug):
    next_data = get_next_data(url, save_debug)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/next.txt')

    next_json = {}
    x = 0
    m = re.search(r'^\s*([0-9a-f]{1,2}):(.*)', next_data)
    while m:
        key = m.group(1)
        x += len(key) + 1
        val = m.group(2)
        if val.startswith('I'):
            val = val[1:]
            x += 1
        elif val.startswith('HL'):
            val = val[2:]
            x += 2
        elif val.startswith('T'):
            t = re.search(r'T([0-9a-f]+),(.*)', val)
            if t:
                n = int(t.group(1), 16)
                x += len(t.group(1)) + 2
                val = next_data[x:x + n]
                # print(n, val)
                # if not val.isascii():
                #     i = n
                #     n = 0
                #     for c in val:
                #         n += 1
                #         i -= len(c.encode('utf-8'))
                #         if i == 0:
                #             break
                #     val = next_data[x:x + n]
                #     print(n, val)
        if val:
            # print(key, val)
            if (val.startswith('{') and val.endswith('}')) or (val.startswith('[') and val.endswith(']')):
                next_json[key] = json.loads(val)
            elif val.startswith('"') and val.endswith('"'):
                next_json[key] = val[1:-1]
            else:
                next_json[key] = val
            x += len(val)
            if next_data[x:].startswith('\n'):
                x += 1
            m = re.search(r'^\s*([0-9a-f]{1,2}):(.*)', next_data[x:])
        else:
            break
    return next_json


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    if 'rsc' in site_json:
        next_json = get_next_json(url + '?_rsc=' + site_json['rsc'], save_debug)
        if not next_json:
            return None
        if save_debug:
            utils.write_file(next_json, './debug/next.json')

        post_json = None
        def find_post(child):
            nonlocal post_json
            if not isinstance(child, list):
                return
            if isinstance(child[0], str) and child[0] == '$':
                if child[3].get('post'):
                    post_json = child[3]['post']
                elif child[3].get('data-testid') and child[3]['data-testid'] == 'ad-container':
                    return
                elif child[3].get('children'):
                    iter_children(child[3]['children'])
            else:
                iter_children(child)
        def iter_children(children):
            nonlocal post_json
            if isinstance(children, list):
                if isinstance(children[0], str) and children[0] == '$':
                    find_post(children)
                else:
                    for child in children:
                        find_post(child)
                        if post_json:
                            break
        iter_children(next_json['2'])
        if not post_json:
            logger.warning('unable to find post')
            return None
        if save_debug:
            utils.write_file(post_json, './debug/debug.json')

        item = {}
        item['id'] = post_json['id']
        item['url'] = post_json['link']
        item['title'] = post_json['title']['rendered']

        dt = datetime.fromisoformat(post_json['date_gmt']).replace(tzinfo=timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        if post_json.get('modified_gmt'):
            dt = datetime.fromisoformat(post_json['modified_gmt']).replace(tzinfo=timezone.utc)
            item['date_modified'] = dt.isoformat()

        if post_json.get('authors'):
            item['authors'] = [{"name": x['name']} for x in post_json['authors']]
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }

        item['tags'] = []
        if post_json.get('categories'):
            item['tags'] += [x['name'] for x in post_json['categories']]
        if post_json.get('tags'):
            item['tags'] += [x['name'] for x in post_json['tags']]

        if post_json['meta'].get('meta_description'):
            item['summary'] = post_json['meta']['meta_description']

        item['content_html'] = ''
        if post_json.get('excerpt') and post_json['excerpt'].get('rendered'):
            item['content_html'] += '<p><em>' + post_json['excerpt']['rendered'] + '</em></p>'

        if post_json.get('featured_media'):
            if post_json['featured_media']['source_url'].startswith('/'):
                item['image'] = 'https://' + split_url.netloc + post_json['featured_media']['source_url']
            else:
                item['image'] = post_json['featured_media']['source_url']
            if post_json['featured_media'].get('caption') and post_json['featured_media']['caption'].get('rendered'):
                caption = re.sub(r'^<p>|</p>$', '', post_json['featured_media']['caption']['rendered'].strip())
            elif post_json['meta'].get('featured_image_caption'):
                caption = post_json['meta']['featured_image_caption']
            else:
                caption = ''
            item['content_html'] += utils.add_image(item['image'], caption)

        if post_json.get('content') and post_json['content'].get('rendered'):
            m = re.search(r'^\$([a-f0-9]+)', post_json['content']['rendered'])
            if m:
                content_html = next_json[m.group(1)]
            else:
                content_html = post_json['content']['rendered']
            site_copy = site_json.copy()
            site_copy['decompose'] = [
                {
                    "attrs": {
                        "data-smart-slot": True
                    }
                },
                {
                    "attrs": {
                        "class": [
                            "rufous-sandbox",
                            "variation-content-card",
                            "wp-block-the-arena-group-toc"
                        ]
                    }
                },
                {
                    "selector": "iframe[src*=\"platform.twitter.com/widgets/widget_iframe\"]"
                },
                {
                    "selector": "p:has(> strong:-soup-contains(\"Related:\"))"
                },
                {
                    "selector": "p:has(> strong:-soup-contains(\"Up Next:\"))"
                },
                {
                    "selector": "p:has(> strong > a[href*=\"/newsletters\"])"
                },
                {
                    "selector": "p:has(> strong > strong > a[href*=\"/newsletters\"])"
                }
            ]
            site_copy['rename'] = [
                {
                    "old": {
                        "attrs": {
                            "data-wp-block": "{\"dropCap\":true}"
                        },
                        "tag": "p"
                    },
                    "new": {
                        "attrs": {
                            "class": "dropcap"
                        }
                    }
                }
            ]
            site_copy['clear_attrs'] = [
                {
                    "attrs": {
                        "data-wp-block": "{\"dropCap\":false}"
                    },
                    "tag": "p"
                },
                {
                    "attrs": {
                        "class": [
                            "wp-block-heading",
                            "wp-block-list"
                        ]
                    }
                },
                {
                    "attrs": {
                        "data-wp-block-name": "core/list-item"
                    }
                }
            ]
            # unwrap twice because a case where they were nested
            site_copy['unwrap'] = [
                {
                    "selector": "div.wp-block-group:has(> .wp-block-embed)"
                },
                {
                    "selector": "div.wp-block-group:has(> .wp-block-embed)"
                }

            ]
            item['content_html'] += wp_posts_v2.format_content(content_html, item['url'], args, site_json=site_copy)
    else:
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "priority": "u=0, i",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1"
        }
        r = curl_cffi.get(url, impersonate='chrome', headers=headers, proxies=config.proxies)
        if r.status_code != 200:
            logger.warning('status code {} getting {}'.format(r.status_code, url))
            return None
        page_html = r.text
        if save_debug:
            utils.write_file(page_html, './debug/debug.html')

        page_soup = BeautifulSoup(page_html, 'lxml')
        el = page_soup.find('script', id='pageItemData')
        if not el:
            logger.warning('unable to find pageItemData in ' + url)
            return None

        page_data = json.loads(el.string)
        if save_debug:
            utils.write_file(page_data, './debug/debug.json')

        item = {}
        item['id'] = page_data['id']
        item['url'] = 'https://' + split_url.netloc + page_data['path']
        item['title'] = page_data['title']

        # TODO: difference between publicationTimestamp and originalPublicationTimestamp
        dt = datetime.fromisoformat(page_data['publicationTimestamp'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

        item['author'] = {
            "name": page_data['viewProperties']['analyticsModel']['authorName']
        }
        item['authors'] = []
        item['authors'].append(item['author'])
        if page_data['viewProperties']['analyticsModel'].get('creditedContributors'):
            for el in page_soup.find_all(class_='m-detail--author-byline'):
                if el.a and el.a.get_text().strip() == page_data['viewProperties']['analyticsModel']['creditedContributors']:
                    item['author']['name'] += ' and ' + el.get_text().strip()
                    item['authors'].append({"name": el.get_text().strip()})

        if page_data.get('associatedRichTerms'):
            item['tags'] = [x['title'] for x in page_data['associatedRichTerms']]

        if page_data.get('primaryImage'):
            item['image'] = 'https://' + split_url.netloc + '/.image/c_limit%2Ccs_srgb%2Cfl_progressive%2Cq_auto:good%2Cw_1200/' + page_data['primaryImage']['publicId'] + '/' + page_data['primaryImage']['title'] + '.' + page_data['primaryImage']['format']

        if page_data.get('metaDescription'):
            item['summary'] = page_data['metaDescription']
        elif page_data.get('teaser'):
            item['summary'] = page_data['teaser']
        elif page_data.get('dek'):
            item['summary'] = page_data['dek']

        item['content_html'] = ''
        if page_data.get('dek'):
            item['content_html'] += '<p><em>' + page_data['dek'] + '</em></p>'

        body = page_soup.find(class_='m-detail--body')
        if body:
            el = page_soup.find(class_=['m-detail-header--media', 'm-detail--feature-container'])
            if el:
                el['class'].append('m-detail--body-item')
                body.insert(0, el)

            for el in body.find_all(['phoenix-super-link', 'script']):
                el.decompose()

            for el in body.find_all(id='action_button_container'):
                el.decompose()

            for el in body.find_all('a', attrs={"onclick": True}):
                del el['onclick']

            for el in body.find_all(recursive=False):
                new_html = ''
                if el.name == 'aside' and ('m-in-content-ad' in el['class'] or 'm-in-content-ad-row' in el['class']):
                    el.decompose()
                    continue
                elif el.name == 'p':
                    if el.find('strong') and re.search(r'^(Next:|Related:|Sign up)', el.strong.get_text().strip(), flags=re.I):
                        el.decompose()
                    continue
                elif (el.name == 'h2' or el.name == 'h3') and el.get('id'):
                    el.attrs = {}
                    continue
                elif el.name == 'phoenix-flat-gallery':
                    gallery_images = []
                    gallery_html = ''
                    images = el.find_all('phoenix-flat-gallery-slide')
                    n = len(images)
                    for i, image in enumerate(images):
                        img_src = ''
                        it = image.find('img', attrs={"data-src": True})
                        if it:
                            paths = list(filter(None, urlsplit(it['data-src']).path[1:].split('/')))
                            img_src = 'https://' + split_url.netloc + '/.image/c_limit%2Ccs_srgb%2Cfl_progressive%2Cq_auto:good%2Cw_1800/' + paths[-2] + '/' + paths[-1]
                            thumb = 'https://' + split_url.netloc + '/.image/c_limit%2Ccs_srgb%2Cfl_progressive%2Cq_auto:good%2Cw_700/' + paths[-2] + '/' + paths[-1]
                        else:
                            it = el.find('source', attrs={"data-srcset": True})
                            if it:
                                img_src = utils.image_from_srcset(it['data-srcset'], 1200)
                                paths = list(filter(None, urlsplit(img_src).path[1:].split('/')))
                                img_src = 'https://' + split_url.netloc + '/.image/c_limit%2Ccs_srgb%2Cfl_progressive%2Cq_auto:good%2Cw_1800/' + paths[-2] + '/' + paths[-1]
                                thumb = 'https://' + split_url.netloc + '/.image/c_limit%2Ccs_srgb%2Cfl_progressive%2Cq_auto:good%2Cw_700/' + paths[-2] + '/' + paths[-1]
                        captions = []
                        it = image.find(class_='tml-image--caption')
                        if it:
                            captions.append(it.decode_contents())
                        it = image.find(class_='tml-image--attribution')
                        if it:
                            captions.append(it.decode_contents())
                        caption = ' | '.join(captions)
                        gallery_images.append({"src": img_src, "caption": caption, "thumb": thumb})
                        if i == 0:
                            if n % 2 == 1:
                                gallery_html += utils.add_image(thumb, caption, link=img_src, fig_style='margin:1em 0 8px 0; padding:0;')
                            else:
                                gallery_html += '<div style="display:flex; flex-wrap:wrap; gap:8px;"><div style="flex:1; min-width:360px;">'
                                gallery_html += utils.add_image(thumb, caption, link=img_src, fig_style='margin:0; padding:0;')
                                gallery_html += '</div>'
                        elif i == 1:
                            if n % 2 == 1:
                                gallery_html += '<div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:8px;">'
                            gallery_html += '<div style="flex:1; min-width:360px;">'
                            gallery_html += utils.add_image(thumb, caption, link=img_src, fig_style='margin:0; padding:0;')
                            gallery_html += '</div>'
                        else:
                            gallery_html += '<div style="flex:1; min-width:360px;">'
                            gallery_html += utils.add_image(thumb, caption, link=img_src, fig_style='margin:0; padding:0;')
                            gallery_html += '</div>'
                    gallery_html += '</div>'
                    if n > 2:
                        gallery_url = config.server + '/gallery?images=' + quote_plus(json.dumps(gallery_images))
                        new_html = '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + gallery_html
                    else:
                        new_html = gallery_html
                elif el.name == 'blockquote' and 'm-blockquote' in el['class']:
                    new_html = utils.add_blockquote(el.decode_contents())
                elif el.name == 'div' and 'm-detail--body-item' in el['class']:
                    if el.find('phoenix-picture'):
                        img_src = ''
                        it = el.find('img', attrs={"data-src": True})
                        if it:
                            paths = list(filter(None, urlsplit(it['data-src']).path[1:].split('/')))
                            img_src = 'https://' + split_url.netloc + '/.image/c_limit%2Ccs_srgb%2Cfl_progressive%2Cq_auto:good%2Cw_1200/' + paths[-2] + '/' + paths[-1]
                        else:
                            it = el.find('source', attrs={"data-srcset": True})
                            if it:
                                img_src = utils.image_from_srcset(it['data-srcset'], 1200)
                        if img_src:
                            captions = []
                            it = el.find(class_='tml-image--caption')
                            if it:
                                captions.append(it.decode_contents())
                            it = el.find(class_='tml-image--attribution')
                            if it:
                                captions.append(it.decode_contents())
                            new_html = utils.add_image(img_src, ' | '.join(captions))
                    elif el.find('phx-gallery-image'):
                        if '_gallery' in item:
                            logger.warning('multiple galleries in ' + item['url'])
                        item['_gallery'] = []
                        new_html += '<h3><a href="{}/gallery?url={}" target="_blank">View photo gallery</a></h3>'.format(config.server, quote_plus(item['url']))
                        new_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                        for it in el.find_all('phx-gallery-image'):
                            img_src = it['data-full-src']
                            paths = list(filter(None, urlsplit(img_src).path[1:].split('/')))
                            thumb = 'https://' + split_url.netloc + '/.image/c_limit%2Ccs_srgb%2Cfl_progressive%2Cq_auto:good%2Cw_640/' + paths[-2] + '/' + paths[-1]
                            if it.get('data-caption-html'):
                                caption = BeautifulSoup(html.unescape(it['data-caption-html']), 'html.parser').get_text()
                            else:
                                caption = ''
                            new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src) + '</div>'
                            item['_gallery'].append({"src": img_src, "caption": caption, "thumb": thumb})
                        new_html += '</div>'
                    elif el.find('phoenix-video'):
                        it = el.find('phoenix-video')
                        new_html += utils.add_embed('https://cdn.jwplayer.com/v2/media/' + it['video-id'])
                    # elif el.find('phoenix-exco-player'):
                    #     player_url = 'https://player.ex.co/player/' + player_id
                    #     player = utils.get_url_html(player_url)
                    #     if not player:
                    #         return None
                    #     m = re.search(r'window\.STREAM_CONFIGS\[\'{}\'\] = (.*?);\n'.format(player_id), player)
                    #     if not m:
                    #         logger.warning('unable to find STREAM_CONFIGS in ' + player_url)
                    #         return None
                    #     stream_config = json.loads(m.group(1))
                    #     utils.write_file(stream_config, './debug/video.json')
                    #     new_html = utils.add_video(stream_config['contents'][0]['video']['mp4']['src'], 'video/mp4', stream_config['contents'][0]['poster'], stream_config['contents'][0]['title'])
                    elif el.find('phoenix-twitter-embed'):
                        new_html = utils.add_embed(el.find('phoenix-twitter-embed')['tweet-url'])
                    elif el.find('phoenix-instagram-embed'):
                        new_html = utils.add_embed(el.find('phoenix-instagram-embed')['src'])
                    elif el.find('phoenix-tiktok-embed'):
                        new_html = utils.add_embed(el.find('phoenix-tiktok-embed')['src'])
                elif el.name == 'ul' or el.name == 'ol':
                    continue
                if new_html:
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.replace_with(new_el)
                else:
                    logger.warning('unhandled body item in ' + item['url'])
                    print(str(el))

            item['content_html'] += body.decode_contents()
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
